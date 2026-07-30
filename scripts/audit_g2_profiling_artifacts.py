#!/usr/bin/env python3
"""Integrity audit for returned G2 v3 cloud profiling artifacts.

This script intentionally has no torch/transformers dependency.  It verifies
the selection contract, all 128×3 raw measurements, constrained-label
probabilities, summaries, and the 4090D preflight before an orchestrator may
consider upgrading the G2 gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


ALLOWED_LABELS = {"0", "1", "2"}
SELECTION_CONTRACT_VERSION = "g2-profiling-v3"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    index = (len(sorted_values) - 1) * p / 100
    lower = int(index)
    fraction = index - lower
    if lower + 1 < len(sorted_values):
        return sorted_values[lower] + fraction * (sorted_values[lower + 1] - sorted_values[lower])
    return sorted_values[lower]


def canonical_selection_sha(records: list[dict[str, Any]]) -> str:
    canonical = sorted(
        [
            {
                "event_id": record["event_id"],
                "rendered_prompt_sha256": record["rendered_prompt_sha256"],
                "profiling_prompt_sha256": record["profiling_prompt_sha256"],
                "profiling_input_tokens": record["profiling_input_tokens"],
                "input_length_tercile": record["input_length_tercile"],
                "selection_role": record["selection_role"],
            }
            for record in records
        ],
        key=lambda item: item["event_id"],
    )
    return hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def add_check(checks: list[dict[str, Any]], name: str, passed: bool, detail: Any) -> None:
    checks.append({"name": name, "passed": passed, "detail": detail})


def validate_selection(selection: dict[str, Any], checks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    records = selection.get("records", [])
    by_id = {record.get("event_id"): record for record in records}
    stratification = selection.get("stratification", {})
    actual_lengths = Counter(record.get("input_length_tercile") for record in records)
    actual_sources = Counter(record.get("source") for record in records)
    tau_hard = sum(
        record.get("source") == "tau2-bench" and bool(record.get("hard_required"))
        for record in records
    )
    add_check(
        checks,
        "selection_contract",
        selection.get("selection_contract_version") == SELECTION_CONTRACT_VERSION,
        selection.get("selection_contract_version"),
    )
    add_check(
        checks,
        "selection_exact_unique_128",
        len(records) == 128 == selection.get("n_profiling_actions") == len(by_id),
        {"records": len(records), "declared": selection.get("n_profiling_actions"), "unique": len(by_id)},
    )
    add_check(
        checks,
        "selection_hash",
        canonical_selection_sha(records) == selection.get("selection_sha256"),
        selection.get("selection_sha256"),
    )
    add_check(
        checks,
        "selection_length_quotas",
        dict(actual_lengths) == stratification.get("length_quotas"),
        {"actual": dict(actual_lengths), "target": stratification.get("length_quotas")},
    )
    add_check(
        checks,
        "selection_safetoolbench_quota",
        actual_sources.get("safetoolbench", 0) == stratification.get("safetoolbench_quota"),
        {"actual": actual_sources.get("safetoolbench", 0), "target": stratification.get("safetoolbench_quota")},
    )
    add_check(
        checks,
        "selection_tau_hard_minimum",
        tau_hard >= stratification.get("tau_hard_minimum", 0),
        {"actual": tau_hard, "minimum": stratification.get("tau_hard_minimum")},
    )
    add_check(
        checks,
        "selection_eligible_and_metadata",
        all(
            record.get("eligible_for_profiling") is True
            and record.get("input_length_tercile") in {"short", "medium", "long"}
            and record.get("selection_role") in {"evaluation", "calibration_latency_only"}
            and isinstance(record.get("profiling_input_tokens"), int)
            and bool(record.get("profiling_prompt_sha256"))
            for record in records
        ),
        "all records must carry v3 profiling metadata",
    )
    return by_id


def validate_tier(
    tier: str,
    raw: list[dict[str, Any]],
    summary: dict[str, Any],
    selected: dict[str, dict[str, Any]],
    selection: dict[str, Any],
    checks: list[dict[str, Any]],
) -> None:
    expected_ids = set(selected)
    raw_ids = [measurement.get("event_id") for measurement in raw]
    repetitions = Counter(raw_ids)
    ok = [measurement for measurement in raw if measurement.get("status") == "ok"]
    status_counts = Counter(measurement.get("status") for measurement in raw)
    add_check(
        checks,
        f"{tier}_raw_cardinality",
        len(raw) == 384 and set(raw_ids) == expected_ids and set(repetitions.values()) == {3},
        {"rows": len(raw), "unique_events": len(set(raw_ids)), "repetitions": dict(Counter(repetitions.values()))},
    )
    add_check(
        checks,
        f"{tier}_constrained_outputs",
        len(ok) == 384
        and all(
            measurement.get("output_tokens") == 1
            and measurement.get("label") in ALLOWED_LABELS
            and measurement.get("raw_output") == measurement.get("label")
            for measurement in raw
        ),
        dict(status_counts),
    )
    probability_ok = True
    probability_examples: list[Any] = []
    for measurement in raw:
        probabilities = measurement.get("constrained_label_probabilities", {})
        if set(probabilities) != ALLOWED_LABELS:
            probability_ok = False
            probability_examples.append(probabilities)
            continue
        total = sum(float(probabilities[label]) for label in ALLOWED_LABELS)
        risk_score = float(measurement.get("risk_score", -1))
        if not math.isclose(total, 1.0, abs_tol=1e-6) or not math.isclose(
            risk_score,
            float(probabilities["1"]) + float(probabilities["2"]),
            abs_tol=1e-6,
        ):
            probability_ok = False
            probability_examples.append({"probabilities": probabilities, "risk_score": risk_score})
    add_check(checks, f"{tier}_constrained_probabilities", probability_ok, probability_examples[:3])
    add_check(
        checks,
        f"{tier}_selection_metadata_matches_raw",
        all(
            measurement.get("input_length_tercile") == selected[measurement["event_id"]].get("input_length_tercile")
            and measurement.get("selection_role") == selected[measurement["event_id"]].get("selection_role")
            and measurement.get("profiling_prompt_sha256") == selected[measurement["event_id"]].get("profiling_prompt_sha256")
            and measurement.get("input_tokens") == selected[measurement["event_id"]].get("profiling_input_tokens")
            for measurement in raw
            if measurement.get("event_id") in selected
        ),
        "raw metadata must match the frozen selection",
    )
    interference = sum(bool(measurement.get("gpu_interference")) for measurement in ok)
    add_check(
        checks,
        f"{tier}_gpu_interference",
        len(ok) == 384 and interference / len(ok) <= 0.05,
        {"count": interference, "rate": interference / max(len(ok), 1)},
    )
    computed = {
        "wall_p50_ms": round(percentile(sorted(measurement["wall_ms"] for measurement in ok), 50), 2),
        "wall_p95_ms": round(percentile(sorted(measurement["wall_ms"] for measurement in ok), 95), 2),
        "wall_p99_ms": round(percentile(sorted(measurement["wall_ms"] for measurement in ok), 99), 2),
        "cuda_p50_ms": round(percentile(sorted(measurement["cuda_ms"] for measurement in ok), 50), 2),
        "cuda_p95_ms": round(percentile(sorted(measurement["cuda_ms"] for measurement in ok), 95), 2),
        "cuda_p99_ms": round(percentile(sorted(measurement["cuda_ms"] for measurement in ok), 99), 2),
        "n_samples": len(ok),
    }
    add_check(
        checks,
        f"{tier}_summary_statistics",
        all(summary.get("latency", {}).get(name) == value for name, value in computed.items()),
        {"computed": computed, "stored": summary.get("latency")},
    )
    expected_by_length = {
        length: selection["stratification"]["length_quotas"][length] * 3
        for length in ("short", "medium", "long")
    }
    actual_by_length = Counter(measurement.get("input_length_tercile") for measurement in raw)
    add_check(
        checks,
        f"{tier}_per_length_coverage",
        dict(actual_by_length) == expected_by_length
        and all(summary.get("latency_by_input_length_tercile", {}).get(length, {}).get("n_samples") == count for length, count in expected_by_length.items()),
        {"actual": dict(actual_by_length), "expected": expected_by_length},
    )
    profiling = summary.get("profiling", {})
    add_check(
        checks,
        f"{tier}_summary_gate",
        summary.get("passed") is True
        and profiling.get("total_expected") == 384
        and profiling.get("total_ok") == 384
        and profiling.get("oom_count") == 0
        and profiling.get("constraint_error_count") == 0
        and profiling.get("runtime_error_count") == 0,
        profiling,
    )
    gpu = summary.get("gpu", {})
    constraint = summary.get("decoding_constraint", {})
    code = summary.get("code", {})
    constraint_payload = {
        key: constraint.get(key)
        for key in (
            "version",
            "allowed_labels",
            "label_token_ids",
            "max_new_tokens",
            "probability_semantics",
        )
    }
    expected_constraint_sha = hashlib.sha256(
        json.dumps(constraint_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    add_check(
        checks,
        f"{tier}_provenance",
        summary.get("selection_contract_version") == SELECTION_CONTRACT_VERSION
        and summary.get("selection_sha256") == selection.get("selection_sha256")
        and gpu.get("name") == "NVIDIA GeForce RTX 4090 D"
        and bool(gpu.get("driver_version"))
        and bool(gpu.get("transformers_version"))
        and constraint.get("version") == "single_token_label_logits_mask_v1"
        and constraint.get("allowed_labels") == ["0", "1", "2"]
        and constraint.get("max_new_tokens") == 1,
        {"gpu": gpu, "constraint": constraint, "code": code},
    )
    add_check(
        checks,
        f"{tier}_constraint_hash",
        constraint.get("sha256") == expected_constraint_sha,
        {"actual": constraint.get("sha256"), "expected": expected_constraint_sha},
    )
    add_check(
        checks,
        f"{tier}_code_provenance",
        bool(code.get("git_revision")) and bool(code.get("runner_sha256")),
        code,
    )


def validate_smoke(smoke: Any, checks: list[dict[str, Any]]) -> list[str]:
    if not isinstance(smoke, list):
        add_check(checks, "constrained_smoke", False, "smoke artifact is not a JSON list")
        return []
    by_tier = {result.get("tier"): result for result in smoke}
    revisions: list[str] = []
    passed = set(by_tier) == {"light", "strong"}
    details: dict[str, Any] = {}
    for tier in ("light", "strong"):
        result = by_tier.get(tier, {})
        constraint = result.get("decoding_constraint", {})
        cases = result.get("cases", [])
        valid_cases = bool(cases) and all(
            case.get("valid_label") is True
            and case.get("output_tokens") == 1
            and case.get("parsed_label") in ALLOWED_LABELS
            for case in cases
        )
        tier_passed = (
            result.get("passed") is True
            and result.get("gpu", {}).get("name") == "NVIDIA GeForce RTX 4090 D"
            and constraint.get("version") == "single_token_label_logits_mask_v1"
            and constraint.get("max_new_tokens") == 1
            and valid_cases
        )
        passed = passed and tier_passed
        details[tier] = {"passed": tier_passed, "cases": len(cases), "constraint": constraint}
        revision = result.get("code", {}).get("git_revision", "")
        if revision:
            revisions.append(revision)
    add_check(checks, "constrained_smoke", passed, details)
    return revisions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=Path("data/processed/g2-profiling-selection.v3.json"))
    parser.add_argument("--preflight", type=Path, default=Path("artifact/cloud-gpu/preflight.v3.json"))
    parser.add_argument("--smoke", type=Path, default=Path("artifact/cloud-gpu/smoke-test-results.v3.json"))
    parser.add_argument("--light", type=Path, default=Path("artifact/cloud-gpu/profiling-light.v3.jsonl"))
    parser.add_argument("--strong", type=Path, default=Path("artifact/cloud-gpu/profiling-strong.v3.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("artifact/cloud-gpu/g2-v3-audit.json"))
    args = parser.parse_args()

    checks: list[dict[str, Any]] = []
    selection = load_json(args.selection)
    selected = validate_selection(selection, checks)
    preflight = load_json(args.preflight)
    add_check(
        checks,
        "preflight_4090d",
        preflight.get("passed") is True
        and preflight.get("gpu", {}).get("name") == "NVIDIA GeForce RTX 4090 D"
        and preflight.get("torch", {}).get("cuda_available") is True
        and preflight.get("torch", {}).get("bf16_supported") is True,
        preflight.get("gpu"),
    )
    revisions = [selection.get("code", {}).get("git_revision", ""), preflight.get("code", {}).get("git_revision", "")]
    revisions.extend(validate_smoke(load_json(args.smoke), checks))
    summaries: dict[str, dict[str, Any]] = {}
    for tier, raw_path in (("light", args.light), ("strong", args.strong)):
        raw = load_jsonl(raw_path)
        summary_path = raw_path.with_suffix(".summary.json")
        summary = load_json(summary_path)
        summaries[tier] = summary
        validate_tier(tier, raw, summary, selected, selection, checks)
        revisions.append(summary.get("code", {}).get("git_revision", ""))

    nonempty_revisions = [revision for revision in revisions if revision]
    add_check(
        checks,
        "same_git_revision",
        len(nonempty_revisions) == 6 and len(set(nonempty_revisions)) == 1,
        revisions,
    )

    strong_p95 = summaries["strong"].get("latency", {}).get("wall_p95_ms")
    derived_wait = math.ceil(max(5000, 4 * float(strong_p95))) if strong_p95 is not None else None
    add_check(
        checks,
        "maximum_wait_formula",
        derived_wait == 5000,
        {"strong_wall_p95_ms": strong_p95, "derived_maximum_wait_ms": derived_wait},
    )
    passed = all(check["passed"] for check in checks)
    payload = {
        "schema_version": "0.1",
        "audit_type": "g2_v3_cloud_profile_integrity",
        "passed": passed,
        "derived_maximum_wait_ms": derived_wait,
        "checks": checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
