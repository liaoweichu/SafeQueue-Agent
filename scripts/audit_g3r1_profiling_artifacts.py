#!/usr/bin/env python3
"""Audit the G3-R1 128 x 3 Light/Strong profiling artifacts before freezing them."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_g3r1_profiling_selection import (
    SELECTION_CONTRACT_VERSION,
    canonical_selection_sha,
)
from src.g3_replay import write_json


ALLOWED_LABELS = {"0", "1", "2"}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: JSONL row is not an object")
            rows.append(value)
    return rows


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def add_check(checks: list[dict[str, Any]], name: str, passed: bool, detail: Any) -> None:
    checks.append({"name": name, "passed": passed, "detail": detail})


def validate_selection(selection: dict[str, Any], checks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    records = selection.get("records", [])
    by_id = {str(record.get("event_id")): record for record in records}
    stratification = selection.get("stratification", {})
    source_counts = Counter(record.get("source") for record in records)
    length_counts = Counter(record.get("input_length_tercile") for record in records)
    tau_hard = sum(record.get("source") == "tau2-bench" and bool(record.get("hard_required")) for record in records)
    add_check(checks, "selection_contract", selection.get("selection_contract_version") == SELECTION_CONTRACT_VERSION, selection.get("selection_contract_version"))
    add_check(checks, "selection_event_manifest_provenance", bool(selection.get("event_manifest_sha256")), selection.get("event_manifest_sha256"))
    add_check(checks, "selection_exact_unique_128", len(records) == 128 == selection.get("n_profiling_actions") == len(by_id), {"records": len(records), "unique": len(by_id)})
    add_check(checks, "selection_hash", canonical_selection_sha(records) == selection.get("selection_sha256"), selection.get("selection_sha256"))
    add_check(checks, "selection_length_quotas", dict(length_counts) == stratification.get("length_quotas"), {"actual": dict(length_counts), "target": stratification.get("length_quotas")})
    add_check(checks, "selection_source_quotas", source_counts.get("tau2-bench", 0) == stratification.get("tau2_evaluation_quota") and source_counts.get("safetoolbench", 0) == stratification.get("safetoolbench_dangerous_evaluation_quota"), {"actual": dict(source_counts), "stratification": stratification})
    add_check(checks, "selection_tau_hard_minimum", tau_hard >= int(stratification.get("tau_hard_minimum", 0)), {"actual": tau_hard, "minimum": stratification.get("tau_hard_minimum")})
    add_check(checks, "selection_evaluation_only", all(record.get("selection_role") == "replay_evaluation" and record.get("selection_source_split") == "evaluation" for record in records), "calibration inputs are excluded from the R1 service profile")
    add_check(checks, "selection_unique_prompts", len({record.get("profiling_prompt_sha256") for record in records}) == len(records), "prompt hashes")
    return by_id


def validate_tier(
    tier: str,
    raw: list[dict[str, Any]],
    summary: dict[str, Any],
    selection: dict[str, Any],
    selected: dict[str, dict[str, Any]],
    checks: list[dict[str, Any]],
) -> None:
    expected_ids = set(selected)
    repetitions = Counter(str(row.get("event_id")) for row in raw)
    ok = [row for row in raw if row.get("status") == "ok"]
    add_check(checks, f"{tier}_raw_cardinality", len(raw) == 384 and set(repetitions) == expected_ids and set(repetitions.values()) == {3}, {"rows": len(raw), "unique_events": len(repetitions), "repetition_counts": dict(Counter(repetitions.values()))})
    add_check(checks, f"{tier}_constrained_output", len(ok) == 384 and all(row.get("output_tokens") == 1 and row.get("label") in ALLOWED_LABELS and row.get("raw_output") == row.get("label") for row in ok), {"ok": len(ok), "status_counts": dict(Counter(row.get("status") for row in raw))})
    probability_ok = True
    for row in ok:
        probabilities = row.get("constrained_label_probabilities")
        if not isinstance(probabilities, dict) or set(probabilities) != ALLOWED_LABELS:
            probability_ok = False
            break
        total = sum(float(probabilities[label]) for label in ALLOWED_LABELS)
        risk = float(row.get("risk_score", -1))
        if not math.isclose(total, 1.0, abs_tol=1e-6) or not math.isclose(risk, float(probabilities["1"]) + float(probabilities["2"]), abs_tol=1e-6):
            probability_ok = False
            break
    add_check(checks, f"{tier}_probability_semantics", probability_ok, "risk=P(BLOCK)+P(ABSTAIN)")
    add_check(checks, f"{tier}_selected_prompt_metadata", all(str(row.get("event_id")) in selected and row.get("input_length_tercile") == selected[str(row["event_id"])].get("input_length_tercile") and row.get("selection_role") == "replay_evaluation" and row.get("profiling_prompt_sha256") == selected[str(row["event_id"])].get("profiling_prompt_sha256") and row.get("input_tokens") == selected[str(row["event_id"])].get("profiling_input_tokens") for row in raw), "raw metadata must match signed selection")
    expected_by_length = {length: int(selection["stratification"]["length_quotas"][length]) * 3 for length in ("short", "medium", "long")}
    actual_by_length = Counter(row.get("input_length_tercile") for row in raw)
    add_check(checks, f"{tier}_length_coverage", dict(actual_by_length) == expected_by_length, {"actual": dict(actual_by_length), "expected": expected_by_length})
    profiling = summary.get("profiling", {})
    gpu = summary.get("gpu", {})
    summary_length_counts = {
        length: summary.get("latency_by_input_length_tercile", {}).get(length, {}).get("n_samples")
        for length in ("short", "medium", "long")
    }
    add_check(checks, f"{tier}_summary_gate", summary.get("passed") is True and profiling.get("total_expected") == 384 and profiling.get("total_ok") == 384 and profiling.get("oom_count") == 0 and profiling.get("constraint_error_count") == 0 and profiling.get("runtime_error_count") == 0 and float(profiling.get("gpu_interference_rate", 1.0)) <= 0.05 and summary.get("latency", {}).get("n_samples") == 384 and summary_length_counts == expected_by_length, {"profiling": profiling, "length_counts": summary_length_counts})
    add_check(checks, f"{tier}_provenance", summary.get("selection_contract_version") == SELECTION_CONTRACT_VERSION and summary.get("selection_sha256") == selection.get("selection_sha256") and gpu.get("name") == "NVIDIA GeForce RTX 4090 D" and bool(gpu.get("driver_version")) and bool(summary.get("policy_sha256")) and bool(summary.get("template_sha256")) and bool(summary.get("code", {}).get("git_revision")), gpu)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=Path("data/processed/g3r1-profiling-selection.v1.json"))
    parser.add_argument("--light-profile", type=Path, default=Path("artifact/cloud-gpu/profiling-light.g3r1.jsonl"))
    parser.add_argument("--strong-profile", type=Path, default=Path("artifact/cloud-gpu/profiling-strong.g3r1.jsonl"))
    parser.add_argument("--light-summary", type=Path)
    parser.add_argument("--strong-summary", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifact/cloud-gpu/g3r1-profiling-audit.json"))
    args = parser.parse_args()
    try:
        light_summary_path = args.light_summary or args.light_profile.with_suffix(".summary.json")
        strong_summary_path = args.strong_summary or args.strong_profile.with_suffix(".summary.json")
        selection = load_json(args.selection)
        checks: list[dict[str, Any]] = []
        selected = validate_selection(selection, checks)
        light_raw = load_jsonl(args.light_profile)
        strong_raw = load_jsonl(args.strong_profile)
        light_summary = load_json(light_summary_path)
        strong_summary = load_json(strong_summary_path)
        validate_tier("light", light_raw, light_summary, selection, selected, checks)
        validate_tier("strong", strong_raw, strong_summary, selection, selected, checks)
        passed = all(check["passed"] for check in checks)
        artifact = {
            "schema_version": "0.1", "audit": "g3r1-profiling", "status": "passed" if passed else "failed",
            "selection_sha256": selection.get("selection_sha256"),
            "files": {
                str(args.selection).replace("\\", "/"): file_sha256(args.selection),
                str(args.light_profile).replace("\\", "/"): file_sha256(args.light_profile),
                str(args.strong_profile).replace("\\", "/"): file_sha256(args.strong_profile),
                str(light_summary_path).replace("\\", "/"): file_sha256(light_summary_path),
                str(strong_summary_path).replace("\\", "/"): file_sha256(strong_summary_path),
            },
            "checks": checks,
        }
        write_json(args.output, artifact)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {args.output}: {artifact['status']}")
    if not passed:
        for check in checks:
            if not check["passed"]:
                print(f"FAIL: {check['name']}: {check['detail']}", file=sys.stderr)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
