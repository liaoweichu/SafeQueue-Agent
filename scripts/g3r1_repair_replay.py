#!/usr/bin/env python3
"""Run the signed G3-R1 serial Light-abstain-to-Strong replay diagnostic."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.g3_replay import read_jsonl, sha256_file, write_json
from src.g3r1_replay import REPLAY_CONTRACT_VERSION, run_repair_replay


def git_revision() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, check=True, text=True
        )
    except Exception:
        return ""
    return completed.stdout.strip()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def normalized(path: Path) -> str:
    return str(path).replace("\\", "/")


def assert_frozen_inputs(config: dict[str, Any], manifest: dict[str, Any], selection: dict[str, Any]) -> None:
    if config.get("status") != "owner_signed_service_profile_frozen":
        raise ValueError("G3-R1 replay requires an owner-signed, profile-frozen run config")
    frozen = config["frozen_inputs"]
    event_input = frozen["event_manifest"]
    if manifest.get("selection_sha256") != event_input.get("selection_sha256"):
        raise ValueError("event manifest selection SHA does not match signed config")
    if manifest.get("status") != "owner_signed":
        raise ValueError("event manifest is not owner_signed")
    profile = frozen["g3r1_profile_selection"]
    if selection.get("selection_contract_version") != profile.get("selection_contract_version"):
        raise ValueError("G3-R1 profiling selection contract differs from signed config")
    if selection.get("selection_sha256") != profile.get("selection_sha256"):
        raise ValueError("G3-R1 profiling selection SHA differs from signed config")
    if selection.get("event_manifest_sha256") != event_input.get("selection_sha256"):
        raise ValueError("G3-R1 profiling selection differs from the signed event manifest")
    if selection.get("token_tercile_boundaries") != profile.get("token_tercile_boundaries"):
        raise ValueError("G3-R1 profile token-tercile boundaries differ from signed config")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path,
        default=Path("experiments/configs/g3r1-serial-abstain-escalation.owner-signed.profile-frozen.json"),
    )
    parser.add_argument("--event-manifest", type=Path)
    parser.add_argument("--profiling-selection", type=Path)
    parser.add_argument("--light-cache", type=Path)
    parser.add_argument("--strong-cache", type=Path)
    parser.add_argument("--light-profile", type=Path)
    parser.add_argument("--strong-profile", type=Path)
    parser.add_argument(
        "--cache-audit", type=Path, default=Path("artifact/cloud-gpu/g3r1-score-cache-audit.json")
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("experiments/results/g3r1-serial-abstain-escalation-replay.json"),
    )
    args = parser.parse_args()
    try:
        config = load_json(args.config)
        frozen = config["frozen_inputs"]
        manifest_path = args.event_manifest or Path(frozen["event_manifest"]["path"])
        selection_path = args.profiling_selection or Path(frozen["g3r1_profile_selection"]["path"])
        light_cache_path = args.light_cache or Path(frozen["light_score_cache"])
        strong_cache_path = args.strong_cache or Path(frozen["strong_score_cache"])
        light_profile_path = args.light_profile or Path(frozen["light_profile"])
        strong_profile_path = args.strong_profile or Path(frozen["strong_profile"])
        required_paths = [
            args.config,
            manifest_path,
            selection_path,
            light_cache_path,
            strong_cache_path,
            light_profile_path,
            strong_profile_path,
            args.cache_audit,
        ]
        missing = [str(path) for path in required_paths if not path.exists()]
        if missing:
            raise ValueError("missing required input(s): " + ", ".join(missing))
        manifest = load_json(manifest_path)
        selection = load_json(selection_path)
        cache_audit = load_json(args.cache_audit)
        assert_frozen_inputs(config, manifest, selection)
        profile_freeze = config.get("service_profile_freeze", {})
        for tier, path in (("light", light_profile_path), ("strong", strong_profile_path)):
            expected_sha = profile_freeze.get("profiles", {}).get(tier, {}).get("sha256")
            if not expected_sha or sha256_file(path) != expected_sha:
                raise ValueError(f"{tier} service profile does not match the frozen profile artifact")
        configured_profile_audit = frozen.get("g3r1_profile_audit", {})
        if configured_profile_audit.get("status") != "passed" or not configured_profile_audit.get("sha256"):
            raise ValueError("run config lacks a passed frozen G3-R1 profile audit")
        if cache_audit.get("status") != "passed":
            raise ValueError("G3-R1 score-cache audit is not passed")
        audited_cache_files = cache_audit.get("files", {})
        for path in (light_cache_path, strong_cache_path):
            if audited_cache_files.get(normalized(path)) != sha256_file(path):
                raise ValueError(f"score-cache audit does not attest to current file: {path}")
        provenance = {
            "runner_git_revision": git_revision(),
            "cache_audit": {
                "path": normalized(args.cache_audit),
                "sha256": sha256_file(args.cache_audit),
                "status": cache_audit.get("status"),
            },
            "files": {
                normalized(path): sha256_file(path)
                for path in required_paths
                if path not in {args.config, args.cache_audit}
            },
        }
        result = run_repair_replay(
            manifest=manifest,
            light_cache=read_jsonl(light_cache_path),
            strong_cache=read_jsonl(strong_cache_path),
            light_profile=read_jsonl(light_profile_path),
            strong_profile=read_jsonl(strong_profile_path),
            config=config,
            provenance=provenance,
        )
        write_json(args.output, result)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {args.output}")
    print(f"Gate status: {result['gate']['status']}")
    print("F0 abstain containment:", result["gate"]["F0_light_abstain_containment"]["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
