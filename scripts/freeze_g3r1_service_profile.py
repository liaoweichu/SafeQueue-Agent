#!/usr/bin/env python3
"""Freeze a passed same-cloud G3-R1 128 x 3 service profile into a run config."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_g3r1_profiling_selection import SELECTION_CONTRACT_VERSION
from src.g3_replay import MODEL_SPECS, sha256_file


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def normalize(path: Path) -> str:
    return str(path).replace("\\", "/")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path,
        default=Path("experiments/configs/g3r1-serial-abstain-escalation.owner-signed.json"),
    )
    parser.add_argument("--selection", type=Path, default=Path("data/processed/g3r1-profiling-selection.v1.json"))
    parser.add_argument("--light-profile", type=Path, default=Path("artifact/cloud-gpu/profiling-light.g3r1.jsonl"))
    parser.add_argument("--strong-profile", type=Path, default=Path("artifact/cloud-gpu/profiling-strong.g3r1.jsonl"))
    parser.add_argument("--profile-audit", type=Path, default=Path("artifact/cloud-gpu/g3r1-profiling-audit.json"))
    parser.add_argument(
        "--output", type=Path,
        default=Path("experiments/configs/g3r1-serial-abstain-escalation.owner-signed.profile-frozen.json"),
    )
    args = parser.parse_args()
    try:
        required = [args.config, args.selection, args.light_profile, args.strong_profile, args.profile_audit]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise ValueError("missing required input(s): " + ", ".join(missing))
        config = load_json(args.config)
        selection = load_json(args.selection)
        profile_audit = load_json(args.profile_audit)
        if config.get("status") != "owner_signed_pending_service_profile":
            raise ValueError("input config is not owner-signed and awaiting a service profile")
        if selection.get("selection_contract_version") != SELECTION_CONTRACT_VERSION:
            raise ValueError("unexpected G3-R1 service-profile selection contract")
        if selection.get("event_manifest_sha256") != config["frozen_inputs"]["event_manifest"].get("selection_sha256"):
            raise ValueError("profile selection was not built from the signed event manifest")
        if profile_audit.get("status") != "passed":
            raise ValueError("G3-R1 service-profile audit is not passed")
        if profile_audit.get("selection_sha256") != selection.get("selection_sha256"):
            raise ValueError("profile audit selection SHA differs from profile selection")
        audited_files = profile_audit.get("files", {})
        audit_inputs = [args.selection, args.light_profile, args.strong_profile]
        audit_inputs.extend([args.light_profile.with_suffix(".summary.json"), args.strong_profile.with_suffix(".summary.json")])
        for path in audit_inputs:
            if audited_files.get(normalize(path)) != sha256_file(path):
                raise ValueError(f"profile audit does not attest to current file: {path}")
        summaries: dict[str, dict[str, Any]] = {}
        for tier, profile_path in (("light", args.light_profile), ("strong", args.strong_profile)):
            summary_path = profile_path.with_suffix(".summary.json")
            if not summary_path.exists():
                raise ValueError(f"missing {tier} profiling summary: {summary_path}")
            summary = load_json(summary_path)
            if summary.get("passed") is not True:
                raise ValueError(f"{tier} profiling summary is not passed")
            if summary.get("selection_sha256") != selection.get("selection_sha256"):
                raise ValueError(f"{tier} profile selection SHA mismatch")
            if summary.get("model_id") != MODEL_SPECS[tier]["model_id"] or summary.get("revision") != MODEL_SPECS[tier]["revision"]:
                raise ValueError(f"{tier} profile model provenance mismatch")
            summaries[tier] = summary
        frozen = dict(config["frozen_inputs"])
        frozen.pop("g2_v3_profile_selection", None)
        frozen["g3r1_profile_selection"] = {
            "path": normalize(args.selection),
            "selection_contract_version": selection["selection_contract_version"],
            "selection_sha256": selection["selection_sha256"],
            "event_manifest_sha256": selection["event_manifest_sha256"],
            "token_tercile_boundaries": selection["token_tercile_boundaries"],
            "profile_scope": selection.get("profile_scope"),
        }
        frozen["light_profile"] = normalize(args.light_profile)
        frozen["strong_profile"] = normalize(args.strong_profile)
        frozen["g3r1_profile_audit"] = {
            "path": normalize(args.profile_audit),
            "sha256": sha256_file(args.profile_audit),
            "status": "passed",
        }
        frozen_config = dict(config)
        frozen_config["status"] = "owner_signed_service_profile_frozen"
        frozen_config["frozen_inputs"] = frozen
        frozen_config["service_profile_freeze"] = {
            "selection_sha256": selection["selection_sha256"],
            "profile_audit_sha256": sha256_file(args.profile_audit),
            "profiles": {
                tier: {
                    "path": normalize(path),
                    "sha256": sha256_file(path),
                    "summary_sha256": sha256_file(path.with_suffix(".summary.json")),
                }
                for tier, path in (("light", args.light_profile), ("strong", args.strong_profile))
            },
            "model_provenance": {
                tier: {"model_id": summaries[tier]["model_id"], "revision": summaries[tier]["revision"]}
                for tier in ("light", "strong")
            },
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(frozen_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote profile-frozen config: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
