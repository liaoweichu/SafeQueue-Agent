#!/usr/bin/env python3
"""Audit both signed G3-R1 verifier caches before serial replay can consume them."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.g3_replay import read_jsonl, sha256_file, write_json
from src.g3r1_replay import (
    expected_counts,
    validate_manifest_readiness,
    validate_score_cache,
)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path,
        default=Path("experiments/configs/g3r1-serial-abstain-escalation.owner-signed.profile-frozen.json"),
    )
    parser.add_argument("--event-manifest", type=Path)
    parser.add_argument(
        "--profiling-selection", type=Path,
        default=Path("data/processed/g3r1-profiling-selection.v1.json"),
    )
    parser.add_argument(
        "--light-cache", type=Path, default=Path("artifact/cloud-gpu/g3r1-scores-light.jsonl")
    )
    parser.add_argument(
        "--strong-cache", type=Path, default=Path("artifact/cloud-gpu/g3r1-scores-strong.jsonl")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("artifact/cloud-gpu/g3r1-score-cache-audit.json")
    )
    args = parser.parse_args()
    try:
        config = load_json(args.config)
        manifest_path = args.event_manifest or Path(config["frozen_inputs"]["event_manifest"]["path"])
        manifest = load_json(manifest_path)
        selection = load_json(args.profiling_selection)
        profile_selection = config["frozen_inputs"]["g3r1_profile_selection"]
        boundaries = profile_selection["token_tercile_boundaries"]
        if config.get("status") != "owner_signed_service_profile_frozen":
            readiness_errors = ["run config is not owner-signed and service-profile-frozen"]
        else:
            readiness_errors = validate_manifest_readiness(manifest)
        if manifest.get("selection_sha256") != config["frozen_inputs"]["event_manifest"]["selection_sha256"]:
            readiness_errors.append("event manifest hash does not match signed config")
        if selection.get("selection_contract_version") != profile_selection["selection_contract_version"]:
            readiness_errors.append("G3-R1 profile selection contract does not match signed config")
        if selection.get("selection_sha256") != profile_selection["selection_sha256"]:
            readiness_errors.append("G3-R1 profile selection hash does not match signed config")
        if selection.get("event_manifest_sha256") != manifest.get("selection_sha256"):
            readiness_errors.append("G3-R1 profile selection does not match signed event manifest")
        if selection.get("token_tercile_boundaries") != boundaries:
            readiness_errors.append("G3-R1 profile token boundaries do not match signed config")
        light_rows = read_jsonl(args.light_cache)
        strong_rows = read_jsonl(args.strong_cache)
        light_errors, light_by_id = validate_score_cache(light_rows, manifest, "light", boundaries)
        strong_errors, strong_by_id = validate_score_cache(strong_rows, manifest, "strong", boundaries)
        profile_hash = profile_selection["selection_sha256"]
        provenance_errors: list[str] = []
        for tier, rows in (("light", light_rows), ("strong", strong_rows)):
            for row in rows:
                event_id = str(row.get("event_id", "<unknown>"))
                if row.get("service_profile_selection_sha256") != profile_hash:
                    provenance_errors.append(f"{tier}/{event_id}: service profile selection SHA mismatch")
                if row.get("event_manifest_sha256") != manifest.get("selection_sha256"):
                    provenance_errors.append(f"{tier}/{event_id}: event manifest SHA mismatch")
                if "ground_truth_safety" in row or "oracle" in row:
                    provenance_errors.append(f"{tier}/{event_id}: forbidden oracle field")
        cross_tier_errors: list[str] = []
        for event_id in sorted(set(light_by_id) | set(strong_by_id)):
            light = light_by_id.get(event_id)
            strong = strong_by_id.get(event_id)
            if light is None or strong is None:
                cross_tier_errors.append(f"{event_id}: missing one verifier tier")
                continue
            for field in ("verifier_prompt_sha256", "input_tokens", "input_length_tercile"):
                if light.get(field) != strong.get(field):
                    cross_tier_errors.append(f"{event_id}: cross-tier {field} mismatch")
            for field in ("policy_sha256", "template_sha256", "event_manifest_sha256"):
                if light.get(field) != strong.get(field):
                    cross_tier_errors.append(f"{event_id}: cross-tier {field} mismatch")
        expected = expected_counts(manifest)
        passed = not any(
            (readiness_errors, light_errors, strong_errors, provenance_errors, cross_tier_errors)
        ) and len(light_rows) == expected["total_per_tier"] and len(strong_rows) == expected["total_per_tier"]
        artifact = {
            "schema_version": "0.1",
            "audit": "g3r1-score-cache",
            "status": "passed" if passed else "failed",
            "scope": expected,
            "files": {
                str(args.light_cache).replace("\\", "/"): sha256_file(args.light_cache),
                str(args.strong_cache).replace("\\", "/"): sha256_file(args.strong_cache),
            },
            "checks": {
                "light_cache_rows": len(light_rows),
                "strong_cache_rows": len(strong_rows),
                "manifest_readiness_errors": readiness_errors,
                "light_validation_errors": light_errors,
                "strong_validation_errors": strong_errors,
                "provenance_errors": provenance_errors,
                "cross_tier_errors": cross_tier_errors,
            },
            "semantics": {
                "cache_scope": "1,000 signed materialized tau2/SafeToolBench inputs per tier",
                "routing_oracle": "forbidden; cache contains model outputs/provenance only",
                "dangerous_holdout": "owner-signed SafeToolBench evaluation rows with conservative Strong-only hard envelope",
            },
        }
        write_json(args.output, artifact)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {args.output}: {artifact['status']}")
    if not passed:
        for message in [
            *readiness_errors,
            *light_errors,
            *strong_errors,
            *provenance_errors,
            *cross_tier_errors,
        ]:
            print(f"FAIL: {message}", file=sys.stderr)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
