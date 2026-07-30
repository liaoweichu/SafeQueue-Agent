#!/usr/bin/env python3
"""Audit the dual verifier score cache before the G3 replay may consume it."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.g3_replay import (
    expected_score_cache_counts,
    read_jsonl,
    validate_score_cache,
    write_json,
)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-manifest", type=Path, default=Path("data/g2-event-selection.json"))
    parser.add_argument(
        "--profiling-selection",
        type=Path,
        default=Path("data/processed/g2-profiling-selection.v3.json"),
    )
    parser.add_argument(
        "--light-cache", type=Path, default=Path("artifact/cloud-gpu/g3-scores-light.jsonl")
    )
    parser.add_argument(
        "--strong-cache", type=Path, default=Path("artifact/cloud-gpu/g3-scores-strong.jsonl")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("artifact/cloud-gpu/g3-score-cache-audit.json")
    )
    args = parser.parse_args()
    try:
        manifest = load_json(args.event_manifest)
        selection = load_json(args.profiling_selection)
        boundaries = selection["token_tercile_boundaries"]
        light_rows = read_jsonl(args.light_cache)
        strong_rows = read_jsonl(args.strong_cache)
        selection_sha256 = selection["selection_sha256"]
        light_errors, light_by_id = validate_score_cache(
            light_rows, manifest, "light", boundaries, selection_sha256
        )
        strong_errors, strong_by_id = validate_score_cache(
            strong_rows, manifest, "strong", boundaries, selection_sha256
        )
        cross_tier_errors: list[str] = []
        for event_id in sorted(set(light_by_id) & set(strong_by_id)):
            light = light_by_id[event_id]
            strong = strong_by_id[event_id]
            for field in ("verifier_prompt_sha256", "input_tokens", "input_length_tercile"):
                if light.get(field) != strong.get(field):
                    cross_tier_errors.append(f"{event_id}: cross-tier {field} mismatch")
            if light.get("policy_sha256") != strong.get("policy_sha256"):
                cross_tier_errors.append(f"{event_id}: cross-tier policy hash mismatch")
            if light.get("template_sha256") != strong.get("template_sha256"):
                cross_tier_errors.append(f"{event_id}: cross-tier template hash mismatch")
        checks = {
            "expected_counts": expected_score_cache_counts(manifest),
            "light_cache_rows": len(light_rows),
            "strong_cache_rows": len(strong_rows),
            "light_validation_errors": light_errors,
            "strong_validation_errors": strong_errors,
            "cross_tier_errors": cross_tier_errors,
            "agentdojo_rows": sum(
                row.get("source") == "agentdojo" for row in [*light_rows, *strong_rows]
            ),
        }
        passed = not light_errors and not strong_errors and not cross_tier_errors and checks["agentdojo_rows"] == 0
        artifact = {
            "schema_version": "0.1",
            "audit": "g3-score-cache",
            "status": "passed" if passed else "failed",
            "checks": checks,
            "semantics": {
                "cache_scope": "700 materialized tau2/SafeToolBench inputs per tier",
                "agentdojo": "excluded; no pre-execution action prompt exists",
                "risk_score": "must already be in [0,1]; replay clamps again defensively",
                "oracle_fields": "forbidden in score cache",
            },
        }
        write_json(args.output, artifact)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {args.output}: {artifact['status']}")
    if not passed:
        for message in [*light_errors, *strong_errors, *cross_tier_errors]:
            print(f"FAIL: {message}", file=sys.stderr)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
