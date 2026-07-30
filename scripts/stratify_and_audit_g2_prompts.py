#!/usr/bin/env python3
"""Build the frozen v3 G2 profiling selection and audit model-visible inputs.

The v2 selection was invalidated because a greedy allocation put 123/128
inputs in one short/non-hard stratum.  This script instead uses the exact
Qwen chat prompt, fixed length quotas (43/43/42), a SafeToolBench
calibration-latency stratum (32 inputs), and a minimum of 32 τ-bench hard
actions.  Safety labels remain selection metadata and are never rendered.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.verifier_prompting import render_chat_prompt, render_verifier_payload, sha256_text
SELECTION_CONTRACT_VERSION = "g2-profiling-v3"
TOKENIZER_ID = "Qwen/Qwen3-1.7B"
TOKENIZER_REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"
LENGTH_ORDER = ("short", "medium", "long")

# These are structural benchmark labels or post-action outcomes.  Their
# appearance in any model-visible field invalidates the selection.
FORBIDDEN_KEYWORDS = (
    "ground_truth_safety",
    "attack_label",
    "injection_label",
    "security_outcome",
    "benchmark_outcome",
    "post_execution",
    "target_function",
    "target_functions",
    "injection_task",
    "injection case",
    "quality_score",
    "risk_category",
    "calibration_label",
    "dangerous_true",
    "benign_expected",
    "hostile_injection",
    "prompt_injection",
    "indirect_prompt_injection",
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        if "event_id" not in record:
            raise ValueError(f"record at {path}:{line_number} has no event_id")
        records.append(record)
    return records


def parse_length_quotas(raw: str, n_profiling: int) -> dict[str, int]:
    try:
        values = [int(value.strip()) for value in raw.split(",")]
    except ValueError as exc:
        raise ValueError("--length-quotas must be three comma-separated integers") from exc
    if len(values) != len(LENGTH_ORDER) or any(value <= 0 for value in values):
        raise ValueError("--length-quotas must contain three positive integers")
    if sum(values) != n_profiling:
        raise ValueError(
            f"length quotas sum to {sum(values)}, but --n-profiling is {n_profiling}"
        )
    return dict(zip(LENGTH_ORDER, values, strict=True))


def compute_terciles(lengths: list[int]) -> tuple[int, int]:
    if len(lengths) < 3:
        raise ValueError("at least three unique eligible prompts are required for terciles")
    sorted_lengths = sorted(lengths)
    return sorted_lengths[len(sorted_lengths) // 3], sorted_lengths[(2 * len(sorted_lengths)) // 3]


def assign_tercile(token_count: int, short_max: int, medium_max: int) -> str:
    if token_count <= short_max:
        return "short"
    if token_count <= medium_max:
        return "medium"
    return "long"


def audit_materialized_record(record: dict[str, Any], template: str, policy: str) -> list[str]:
    """Verify hash provenance and check every model-visible field for leakage."""
    issues: list[str] = []
    event_id = record.get("event_id", "<unknown>")
    rendered = render_verifier_payload(record, template, policy)
    expected_rendered_sha = record.get("rendered_prompt_sha256", "")
    if sha256_text(rendered) != expected_rendered_sha:
        issues.append(f"{event_id}: rendered_prompt_sha256 does not match frozen fields")
    if str(record.get("policy_sha256", "")).lower() != sha256_text(policy):
        issues.append(f"{event_id}: policy_sha256 does not match policy-v1.txt")
    if str(record.get("prompt_template_sha256", "")).lower() != sha256_text(template):
        issues.append(f"{event_id}: prompt_template_sha256 does not match verifier-v1.txt")

    for field in ("state_summary", "user_intent", "tool_name", "tool_arguments"):
        value = str(record.get(field, "")).casefold()
        for keyword in FORBIDDEN_KEYWORDS:
            if keyword in value:
                issues.append(f"{event_id}: forbidden keyword {keyword!r} in {field}")
    return issues


def deduplicate_candidates(candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Stable de-duplication by exact model-ready chat prompt hash."""
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in sorted(candidates, key=lambda item: item["record"]["event_id"]):
        prompt_sha = candidate["profiling_prompt_sha256"]
        if prompt_sha in seen:
            continue
        seen.add(prompt_sha)
        unique.append(candidate)
    return unique, len(candidates) - len(unique)


def bounded_proportional_allocation(total: int, capacities: dict[str, int]) -> dict[str, int]:
    """Allocate exactly ``total`` proportionally, respecting per-bin capacity."""
    if total < 0:
        raise ValueError("allocation total cannot be negative")
    if total > sum(capacities.values()):
        raise ValueError(f"need {total} records but capacities provide only {sum(capacities.values())}")
    if total == 0:
        return {key: 0 for key in capacities}

    capacity_total = sum(capacities.values())
    ideal = {key: total * capacities[key] / capacity_total for key in capacities}
    allocation = {key: min(int(ideal[key]), capacities[key]) for key in capacities}
    remaining = total - sum(allocation.values())
    while remaining:
        eligible = [key for key in capacities if allocation[key] < capacities[key]]
        if not eligible:
            raise AssertionError("bounded allocation ran out of capacity")
        key = max(
            eligible,
            key=lambda item: (ideal[item] - allocation[item], capacities[item] - allocation[item], item),
        )
        allocation[key] += 1
        remaining -= 1
    return allocation


def _sample(rng: random.Random, candidates: list[dict[str, Any]], n: int, description: str) -> list[dict[str, Any]]:
    if n > len(candidates):
        raise ValueError(f"{description}: need {n}, have {len(candidates)}")
    return rng.sample(candidates, n)


def select_with_fixed_quotas(
    candidates: list[dict[str, Any]],
    *,
    length_quotas: dict[str, int],
    safetoolbench_quota: int,
    tau_hard_minimum: int,
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select exactly the declared source, hard-action, and length quotas.

    SafeToolBench entries are calibration-latency-only and always non-hard in
    this frozen manifest.  The remaining inputs are τ-bench evaluation
    actions, including at least ``tau_hard_minimum`` hard actions.
    """
    n_profiling = sum(length_quotas.values())
    if safetoolbench_quota > n_profiling:
        raise ValueError("SafeToolBench quota exceeds profiling total")
    if tau_hard_minimum > n_profiling - safetoolbench_quota:
        raise ValueError("τ-bench hard quota exceeds remaining τ-bench capacity")

    by_length: dict[str, list[dict[str, Any]]] = {length: [] for length in LENGTH_ORDER}
    safetool_by_length: dict[str, list[dict[str, Any]]] = {length: [] for length in LENGTH_ORDER}
    tau_hard_by_length: dict[str, list[dict[str, Any]]] = {length: [] for length in LENGTH_ORDER}
    tau_by_length: dict[str, list[dict[str, Any]]] = {length: [] for length in LENGTH_ORDER}
    for candidate in candidates:
        length = candidate["input_length_tercile"]
        by_length[length].append(candidate)
        source = candidate["record"]["source"]
        if source == "safetoolbench":
            safetool_by_length[length].append(candidate)
        elif source == "tau2-bench":
            tau_by_length[length].append(candidate)
            if candidate["record"].get("hard_required"):
                tau_hard_by_length[length].append(candidate)
        else:
            raise ValueError(f"unsupported profiling source {source!r}")

    for length in LENGTH_ORDER:
        if len(by_length[length]) < length_quotas[length]:
            raise ValueError(
                f"length bin {length} has {len(by_length[length])} unique candidates, "
                f"needs {length_quotas[length]}"
            )

    safetool_capacities = {
        length: min(len(safetool_by_length[length]), length_quotas[length])
        for length in LENGTH_ORDER
    }
    safetool_allocation = bounded_proportional_allocation(
        safetoolbench_quota, safetool_capacities
    )
    hard_capacities = {
        length: min(
            len(tau_hard_by_length[length]),
            length_quotas[length] - safetool_allocation[length],
        )
        for length in LENGTH_ORDER
    }
    hard_allocation = bounded_proportional_allocation(tau_hard_minimum, hard_capacities)

    rng = random.Random(seed)
    selected: list[dict[str, Any]] = []
    for length in LENGTH_ORDER:
        selected_safetool = _sample(
            rng,
            safetool_by_length[length],
            safetool_allocation[length],
            f"SafeToolBench/{length}",
        )
        selected_hard = _sample(
            rng,
            tau_hard_by_length[length],
            hard_allocation[length],
            f"τ-bench hard/{length}",
        )
        selected_ids = {
            item["record"]["event_id"] for item in selected_safetool + selected_hard
        }
        fill_count = length_quotas[length] - len(selected_safetool) - len(selected_hard)
        remaining_tau = [
            item for item in tau_by_length[length] if item["record"]["event_id"] not in selected_ids
        ]
        selected_fill = _sample(rng, remaining_tau, fill_count, f"τ-bench fill/{length}")
        selected.extend(selected_safetool + selected_hard + selected_fill)

    rng.shuffle(selected)
    actual_length = Counter(item["input_length_tercile"] for item in selected)
    actual_source = Counter(item["record"]["source"] for item in selected)
    actual_tau_hard = sum(
        1
        for item in selected
        if item["record"]["source"] == "tau2-bench" and item["record"].get("hard_required")
    )
    if len(selected) != n_profiling:
        raise AssertionError(f"selected {len(selected)}, expected {n_profiling}")
    if dict(actual_length) != length_quotas:
        raise AssertionError(f"length quota violation: actual={actual_length}, target={length_quotas}")
    if actual_source["safetoolbench"] != safetoolbench_quota:
        raise AssertionError("SafeToolBench quota violation")
    if actual_tau_hard < tau_hard_minimum:
        raise AssertionError("τ-bench hard-action minimum violation")
    if len({item["profiling_prompt_sha256"] for item in selected}) != len(selected):
        raise AssertionError("duplicate model-ready prompt selected")

    return selected, {
        "length_quotas": length_quotas,
        "safetoolbench_quota": safetoolbench_quota,
        "tau_bench_quota": n_profiling - safetoolbench_quota,
        "tau_hard_minimum": tau_hard_minimum,
        "actual_length_counts": {length: actual_length[length] for length in LENGTH_ORDER},
        "actual_source_counts": dict(actual_source),
        "actual_tau_hard_count": actual_tau_hard,
        "safetoolbench_allocation_by_length": safetool_allocation,
        "tau_hard_allocation_by_length": hard_allocation,
    }


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


def git_revision() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, check=True, text=True
        ).stdout.strip()
    except Exception:
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, default=Path("data/processed/g2-materialized-records.jsonl"))
    parser.add_argument("--manifest", type=Path, default=Path("data/g2-event-selection.json"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/g2-profiling-selection.v3.json"))
    parser.add_argument("--n-profiling", type=int, default=128)
    parser.add_argument("--length-quotas", default="43,43,42")
    parser.add_argument("--safetoolbench-quota", type=int, default=32)
    parser.add_argument("--tau-hard-minimum", type=int, default=32)
    parser.add_argument("--seed", type=int, default=20260730)
    parser.add_argument("--tokenizer-id", default=TOKENIZER_ID)
    parser.add_argument("--tokenizer-revision", default=TOKENIZER_REVISION)
    parser.add_argument("--exclude-safetoolbench-calibration", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()

    if args.n_profiling <= 0:
        raise ValueError("--n-profiling must be positive")
    if args.exclude_safetoolbench_calibration:
        raise ValueError(
            "v3 requires SafeToolBench calibration-latency inputs; do not exclude this stratum"
        )
    length_quotas = parse_length_quotas(args.length_quotas, args.n_profiling)

    records = load_records(args.records)
    manifest = load_json(args.manifest)
    events = {event["event_id"]: event for event in manifest["events"]}
    policy = (PROJECT_ROOT / "experiments/prompts/policy-v1.txt").read_text(encoding="utf-8")
    template = (PROJECT_ROOT / "experiments/prompts/verifier-v1.txt").read_text(encoding="utf-8")

    all_issues: list[str] = []
    for record in records:
        if record["event_id"] not in events:
            all_issues.append(f"{record['event_id']}: not found in event manifest")
            continue
        if record.get("source") != events[record["event_id"]].get("source"):
            all_issues.append(f"{record['event_id']}: source disagrees with event manifest")
        all_issues.extend(audit_materialized_record(record, template, policy))
    if all_issues:
        print(f"FIELD / PROVENANCE AUDIT: FAIL ({len(all_issues)} issue(s))")
        for issue in all_issues[:30]:
            print(f"  {issue}")
        return 1
    print(f"FIELD / PROVENANCE AUDIT: PASS ({len(records)} materialized records)")
    if args.audit_only:
        return 0

    # The explicit decision: SafeToolBench remains calibration-only for risk
    # thresholding, but 32 of its valid actions enter the latency-only stratum.
    candidate_records: list[tuple[dict[str, Any], str]] = []
    for record in records:
        event = events[record["event_id"]]
        if not record.get("eligible_for_profiling", True):
            continue
        if record["source"] == "tau2-bench" and event.get("split") == "evaluation":
            candidate_records.append((record, "evaluation"))
        elif record["source"] == "safetoolbench" and event.get("split") == "calibration":
            candidate_records.append((record, "calibration_latency_only"))

    print(f"Eligible v3 pool before prompt de-duplication: {len(candidate_records)}")
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        args.tokenizer_id,
        revision=args.tokenizer_revision,
    )
    candidates: list[dict[str, Any]] = []
    for record, role in candidate_records:
        chat_prompt = render_chat_prompt(record, template, policy, tokenizer)
        candidates.append(
            {
                "record": record,
                "selection_role": role,
                "profiling_prompt_sha256": sha256_text(chat_prompt),
                "profiling_input_tokens": len(tokenizer.encode(chat_prompt, add_special_tokens=False)),
            }
        )
    candidates, duplicate_count = deduplicate_candidates(candidates)
    print(f"Unique model-ready pool: {len(candidates)} (removed {duplicate_count} duplicate prompts)")

    short_max, medium_max = compute_terciles(
        [candidate["profiling_input_tokens"] for candidate in candidates]
    )
    for candidate in candidates:
        candidate["input_length_tercile"] = assign_tercile(
            candidate["profiling_input_tokens"], short_max, medium_max
        )
    selected, quota_audit = select_with_fixed_quotas(
        candidates,
        length_quotas=length_quotas,
        safetoolbench_quota=args.safetoolbench_quota,
        tau_hard_minimum=args.tau_hard_minimum,
        seed=args.seed,
    )

    output_records: list[dict[str, Any]] = []
    for candidate in selected:
        output = dict(candidate["record"])
        output.update(
            {
                "profiling_prompt_sha256": candidate["profiling_prompt_sha256"],
                "profiling_input_tokens": candidate["profiling_input_tokens"],
                "input_length_tercile": candidate["input_length_tercile"],
                "selection_role": candidate["selection_role"],
            }
        )
        output_records.append(output)

    safety_counts = Counter(
        events[record["event_id"]].get("ground_truth_safety", "unknown")
        for record in output_records
    )
    payload = {
        "schema_version": "0.2",
        "selection_contract_version": SELECTION_CONTRACT_VERSION,
        "invalidates": "data/processed/g2-profiling-selection.json (v2 skewed allocation)",
        "code": {
            "git_revision": git_revision(),
            "selector_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
        "profiling_seed": args.seed,
        "n_profiling_actions": len(output_records),
        "tokenizer": {"model_id": args.tokenizer_id, "revision": args.tokenizer_revision},
        "token_tercile_boundaries": {"short_max": short_max, "medium_max": medium_max},
        "pool": {
            "eligible_records_before_deduplication": len(candidate_records),
            "unique_model_ready_prompts": len(candidates),
            "duplicate_prompts_removed": duplicate_count,
            "sources": dict(Counter(item["record"]["source"] for item in candidates)),
        },
        "stratification": {
            **quota_audit,
            "safety_counts_for_audit_only": dict(safety_counts),
            "safetoolbench_semantics": "calibration_latency_only; excluded from evaluation and threshold fitting",
            "length_measurement": "full Qwen non-thinking chat prompt tokens",
        },
        "leakage_audit": {
            "passed": True,
            "records_audited": len(records),
            "scope": "all model-visible fields plus rendered prompt hash provenance",
        },
        "selection_sha256": canonical_selection_sha(output_records),
        "records": output_records,
    }
    if payload["n_profiling_actions"] != args.n_profiling:
        raise AssertionError("exact profiling count check failed")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(output_records)} inputs to {args.output}")
    print(f"Selection SHA-256: {payload['selection_sha256']}")
    print("QUOTA AUDIT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
