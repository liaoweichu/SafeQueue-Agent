#!/usr/bin/env python3
"""Verify frozen G2 inputs and cloud GPU readiness without loading any model."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


EXPECTED_FILES = {
    "data/raw/tau2-bench-v1.0.1.zip": (
        "6E4C2E706A82C78EB2846A1E8B5DB6C92B38A3C664EB12FB9FEFE4DBC044E0AE"
    ),
    "data/raw/agentdojo-v0.1.35.zip": (
        "78DA8287D3F496608BBF1C7EAF48A7E4294493AC907CE96DCFB35763B7114D58"
    ),
    "data/raw/safetoolbench-ffdef6e782b0b05f579316003f3b084b549f1366.zip": (
        "0F0BA04880DA6C5DE3C36FE7590D5C17976C54E984E020A2A9C15FC1FB696444"
    ),
    "experiments/prompts/verifier-v1.txt": (
        "BA19ABD9776361BDAC5922D374EDFAA51771374F4C1F8C9BB5B1E674BE8E0F21"
    ),
    "experiments/prompts/policy-v1.txt": (
        "1772EE5994EAA7B81E23585A905D7D400EE01884FE1503CDB48B8599A5B09DAE"
    ),
}
EXPECTED_SELECTION_SHA256 = (
    "8afed1ffe3dcd20e930bd914d74329352308c426aacb99d0ef50ba0879cad3fb"
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def add_check(checks: dict[str, dict], name: str, passed: bool, detail: object) -> None:
    checks[name] = {"passed": passed, "detail": detail}


def load_gpu_info(gpu_index: int) -> tuple[bool, dict]:
    command = [
        "nvidia-smi",
        f"--id={gpu_index}",
        "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(command, check=True, text=True, capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        return False, {"error": str(exc), "command": command}
    columns = [part.strip() for part in completed.stdout.strip().split(",")]
    if len(columns) != 3:
        return False, {"error": "unexpected nvidia-smi output", "stdout": completed.stdout}
    try:
        memory_mib = int(float(columns[1]))
    except ValueError:
        return False, {"error": "unparseable GPU memory", "stdout": completed.stdout}
    return True, {
        "name": columns[0],
        "memory_mib": memory_mib,
        "driver_version": columns[2],
    }


def load_torch_info() -> tuple[bool, dict]:
    try:
        import torch  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        return False, {"error": f"torch import failed: {exc}"}
    cuda_available = torch.cuda.is_available()
    detail: dict[str, object] = {
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "cuda_available": cuda_available,
    }
    if cuda_available:
        detail["torch_device_name"] = torch.cuda.get_device_name(0)
        detail["bf16_supported"] = bool(torch.cuda.is_bf16_supported())
    return cuda_available and bool(detail.get("bf16_supported", False)), detail


def git_revision(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            text=True,
            capture_output=True,
        )
        return completed.stdout.strip()
    except Exception:
        return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifact/cloud-gpu/preflight.json"),
    )
    parser.add_argument("--gpu-index", type=int, default=0)
    parser.add_argument("--expected-gpu-substring", default="RTX 4090")
    parser.add_argument("--minimum-vram-gib", type=float, default=23.5)
    parser.add_argument("--minimum-free-disk-gib", type=float, default=80.0)
    parser.add_argument(
        "--skip-gpu-check",
        action="store_true",
        help="Validate only frozen inputs; intended for local dry-run testing.",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    checks: dict[str, dict] = {}
    for relative, expected in EXPECTED_FILES.items():
        path = repo_root / relative
        actual = file_sha256(path) if path.is_file() else None
        add_check(checks, f"sha256:{relative}", actual == expected, {"expected": expected, "actual": actual})

    manifest_path = repo_root / "data/g2-event-selection.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        canonical_events = json.dumps(
            manifest["events"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        actual_selection = hashlib.sha256(canonical_events).hexdigest()
        add_check(
            checks,
            "event_manifest_sha256",
            actual_selection == EXPECTED_SELECTION_SHA256 == manifest.get("selection_sha256"),
            {"expected": EXPECTED_SELECTION_SHA256, "actual": actual_selection},
        )
    except Exception as exc:  # noqa: BLE001
        add_check(checks, "event_manifest_sha256", False, {"error": str(exc)})

    config = (repo_root / "experiments/configs/g2-minimal-falsification.yaml")
    config_text = config.read_text(encoding="utf-8") if config.is_file() else ""
    add_check(
        checks,
        "confirmed_risk_and_timeout_policy",
        "candidate: 0.02" in config_text
        and "user_confirmed_2026-07-30" in config_text
        and "ceil(max(5000, 4 * measured_strong_p95_ms))" in config_text,
        "epsilon=0.02 and the confirmed timeout formula must remain frozen",
    )

    free_bytes = shutil.disk_usage(repo_root).free
    free_gib = free_bytes / (1024**3)
    add_check(
        checks,
        "free_disk",
        free_gib >= args.minimum_free_disk_gib,
        {"free_gib": round(free_gib, 2), "required_gib": args.minimum_free_disk_gib},
    )

    gpu_info: dict[str, object] = {"skipped": args.skip_gpu_check}
    torch_info: dict[str, object] = {"skipped": args.skip_gpu_check}
    if not args.skip_gpu_check:
        gpu_ok, gpu_info = load_gpu_info(args.gpu_index)
        add_check(checks, "nvidia_smi", gpu_ok, gpu_info)
        if gpu_ok:
            gpu_name = str(gpu_info["name"])
            vram_gib = float(gpu_info["memory_mib"]) / 1024
            add_check(
                checks,
                "frozen_gpu_model",
                args.expected_gpu_substring.lower() in gpu_name.lower(),
                {"expected_substring": args.expected_gpu_substring, "actual": gpu_name},
            )
            add_check(
                checks,
                "gpu_vram",
                vram_gib >= args.minimum_vram_gib,
                {"vram_gib": round(vram_gib, 2), "required_gib": args.minimum_vram_gib},
            )
        torch_ok, torch_info = load_torch_info()
        add_check(checks, "torch_cuda_bf16", torch_ok, torch_info)

    passed = all(item["passed"] for item in checks.values())
    payload = {
        "schema_version": "0.1",
        "purpose": "G2 cloud preflight only; no model is loaded and no experiment is run.",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "host": {"platform": platform.platform(), "python": sys.version},
        "code": {
            "git_revision": git_revision(repo_root),
            "preflight_sha256": file_sha256(Path(__file__)),
        },
        "gpu": gpu_info,
        "torch": torch_info,
        "checks": checks,
        "passed": passed,
    }
    output = args.output if args.output.is_absolute() else repo_root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
