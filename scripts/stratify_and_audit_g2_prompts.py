#!/usr/bin/env python3
"""Stratified profiling-input selection and field-leakage audit for G2.

Uses the real Qwen3 tokenizer for input-length tercile stratification.
Selects exactly 128 profiling actions from tau2-bench evaluation events
(stratified by input_length_tercile, hard_required, ground_truth_safety).
Excludes AgentDojo (no call-time actions) and SafeToolBench (calibration-only).
Excludes duplicate rendered prompts.  Includes SafeToolBench calibration
stratum as a separate output for completeness.

Usage:
    python scripts/stratify_and_audit_g2_prompts.py \
        --records data/processed/g2-materialized-records.jsonl \
        --manifest data/g2-event-selection.json \
        --output data/processed/g2-profiling-selection.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Tokenizer loading ─────────────────────────────────────────────────
_TOKENIZER = None


def _get_tokenizer():
    global _TOKENIZER
    if _TOKENIZER is None:
        from transformers import AutoTokenizer
        _TOKENIZER = AutoTokenizer.from_pretrained(
            "Qwen/Qwen3-1.7B",
            revision="70d244cc86ccca08cf5af4e1e306ecf908b1ad5e",
        )
    return _TOKENIZER


# ── Forbidden leakage patterns ────────────────────────────────────────
FORBIDDEN_KEYWORDS = [
    "ground_truth_safety", "attack_label", "injection_label",
    "security_outcome", "benchmark_outcome", "post_execution",
    "target_function", "injection_task", "injection case",
    "quality_score", "risk_category", "calibration_label",
    "dangerous_true", "benign_expected", "hostile_injection",
    "prompt_injection", "indirect_prompt_injection",
    "target_functions",
]


def count_tokens(text: str) -> int:
    """Count tokens using the real Qwen3 tokenizer."""
    tok = _get_tokenizer()
    return len(tok.encode(text))


def load_records(path: Path) -> list[dict]:
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def compute_terciles(lengths: list[int]) -> tuple[int, int]:
    sorted_lens = sorted(lengths)
    n = len(sorted_lens)
    t1 = sorted_lens[n // 3]
    t2 = sorted_lens[2 * n // 3]
    return t1, t2


def assign_tercile(token_count: int, t1: int, t2: int) -> str:
    if token_count <= t1:
        return "short"
    elif token_count <= t2:
        return "medium"
    return "long"


def deduplicate_by_prompt(records: list[dict]) -> list[dict]:
    """Remove records with duplicate rendered_prompt_sha256."""
    seen: set[str] = set()
    unique: list[dict] = []
    duplicates = 0
    for rec in records:
        sha = rec.get("rendered_prompt_sha256", "")
        if sha in seen:
            duplicates += 1
            continue
        seen.add(sha)
        unique.append(rec)
    if duplicates:
        print(f"  Deduplication: removed {duplicates} duplicate prompts")
    return unique


def audit_record(record: dict) -> list[str]:
    """Check materialized fields for leakage of forbidden keywords."""
    issues: list[str] = []
    for field in ["state_summary", "user_intent", "tool_arguments"]:
        value = record.get(field, "")
        for keyword in FORBIDDEN_KEYWORDS:
            if keyword.lower() in value.lower():
                issues.append(
                    f"FORBIDDEN KEYWORD '{keyword}' found in {field} "
                    f"for event {record['event_id']}"
                )
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stratify G2 profiling inputs — real tokenizer, exact 128, SafeToolBench calibration."
    )
    parser.add_argument("--records", type=Path, default=Path("data/processed/g2-materialized-records.jsonl"))
    parser.add_argument("--manifest", type=Path, default=Path("data/g2-event-selection.json"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/g2-profiling-selection.json"))
    parser.add_argument("--n-profiling", type=int, default=128)
    parser.add_argument("--seed", type=int, default=20260730)
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()

    random.seed(args.seed)

    records = load_records(args.records)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    events = manifest["events"]
    event_index: dict[str, dict] = {e["event_id"]: e for e in events}
    print(f"Loaded {len(records)} records, {len(events)} events")

    # ── Field leakage audit ──────────────────────────────────────────
    all_issues: list[str] = []
    for rec in records:
        all_issues.extend(audit_record(rec))
    if all_issues:
        print(f"\nFIELD LEAKAGE AUDIT: {len(all_issues)} ISSUES FOUND")
        for issue in all_issues[:20]:
            print(f"  FAIL: {issue}")
        print("\nProfiling blocked.")
        return 1
    print("FIELD LEAKAGE AUDIT: PASSED")

    if args.audit_only:
        return 0

    # ── Filter: eligible for profiling only ──────────────────────────
    eligible = [r for r in records if r.get("eligible_for_profiling", True)]
    ineligible = [r for r in records if not r.get("eligible_for_profiling", True)]
    print(f"Eligible for profiling: {len(eligible)}, ineligible: {len(ineligible)}")

    if ineligible:
        sources = defaultdict(int)
        for r in ineligible:
            sources[r.get("source", "?")] += 1
        for src, cnt in sources.items():
            print(f"  Ineligible {src}: {cnt} events (no call-time action available)")

    # Separete calibration from evaluation
    eval_records = [
        r for r in eligible
        if event_index.get(r["event_id"], {}).get("split") == "evaluation"
    ]
    cal_records = [
        r for r in records
        if event_index.get(r["event_id"], {}).get("split") == "calibration"
    ]
    print(f"\nEvaluation (eligible): {len(eval_records)}")
    print(f"Calibration: {len(cal_records)}")

    # ── Deduplicate evaluation records ───────────────────────────────
    eval_records = deduplicate_by_prompt(eval_records)
    print(f"Evaluation (after dedup): {len(eval_records)}")

    if len(eval_records) < args.n_profiling:
        print(f"ERROR: only {len(eval_records)} eligible unique eval records, "
              f"need {args.n_profiling}")
        return 1

    # ── Tokenize with real tokenizer ─────────────────────────────────
    print("\nTokenizing with real Qwen3 tokenizer...")
    tok = _get_tokenizer()
    for rec in eval_records:
        prompt = rec.get("rendered_prompt", "")
        if not prompt:
            # Reconstruct from fields if full prompt not stored
            pass
        tokens = count_tokens(rec.get("state_summary", "") + " " +
                              rec.get("user_intent", "") + " " +
                              rec.get("tool_arguments", ""))
        rec["_token_count"] = tokens

    all_lengths = [r["_token_count"] for r in eval_records]
    t1, t2 = compute_terciles(all_lengths)
    print(f"Token terciles (real tokenizer): short <= {t1} < medium <= {t2} < long")
    for rec in eval_records:
        rec["_tercile"] = assign_tercile(rec["_token_count"], t1, t2)

    # ── Stratify by (source, tercile, hard_required, safety) ─────────
    strata: dict[tuple, list[dict]] = defaultdict(list)
    for rec in eval_records:
        ev = event_index.get(rec["event_id"], {})
        key = (
            rec["source"],
            rec["_tercile"],
            rec["hard_required"],
            ev.get("ground_truth_safety", "unknown"),
        )
        strata[key].append(rec)

    print(f"\nStrata ({len(strata)} groups):")
    for key, group in sorted(strata.items()):
        print(f"  {key}: {len(group)}")

    # ── Proportional allocation, floor 1 per stratum ─────────────────
    total_eval = len(eval_records)
    # First pass: allocate floor of 1 per stratum, then proportional remainder
    n_strata = len(strata)
    floor_alloc = min(args.n_profiling // n_strata, 1) if n_strata > 0 else 0
    allocated: dict[tuple, int] = {}
    remaining = args.n_profiling

    for key in sorted(strata.keys()):
        alloc = max(floor_alloc, 0)
        alloc = min(alloc, len(strata[key]))
        allocated[key] = alloc
        remaining -= alloc

    # Second pass: proportional allocation of remainder
    for key in sorted(strata.keys(), key=lambda k: len(strata[k]), reverse=True):
        if remaining <= 0:
            break
        group = strata[key]
        extra = min(remaining, len(group) - allocated[key])
        if extra > 0:
            allocated[key] += extra
            remaining -= extra

    # Ensure exact 128: if still short, top up
    while sum(allocated.values()) < args.n_profiling:
        for key in sorted(strata.keys(), key=lambda k: len(strata[k]), reverse=True):
            if sum(allocated.values()) >= args.n_profiling:
                break
            if allocated[key] < len(strata[key]):
                allocated[key] += 1

    # Trim if over
    while sum(allocated.values()) > args.n_profiling:
        for key in sorted(strata.keys(), key=lambda k: len(strata[k])):
            if sum(allocated.values()) <= args.n_profiling:
                break
            if allocated[key] > 1:
                allocated[key] -= 1

    print(f"\nAllocation ({sum(allocated.values())} selected, target={args.n_profiling}):")
    for key, alloc in sorted(allocated.items()):
        print(f"  {key}: {alloc}/{len(strata[key])}")

    # ── Sample from each stratum ─────────────────────────────────────
    selected: list[dict] = []
    for key, alloc in allocated.items():
        group = strata[key]
        sampled = random.sample(group, alloc)
        for rec in sampled:
            rec["_allocation_stratum"] = str(key)
        selected.extend(sampled)

    print(f"\nSelected: {len(selected)} (target: {args.n_profiling})")

    # ── SafeToolBench calibration stratum (separate, not for profiling) ──
    stb_cal = [r for r in cal_records if r.get("source") == "safetoolbench"]
    print(f"SafeToolBench calibration stratum: {len(stb_cal)} events (calibration-only, not profiled)")
    tau2_cal = [r for r in cal_records if r.get("source") == "tau2-bench"]
    print(f"tau2-bench benign calibration: {len(tau2_cal)} events (calibration-only, not profiled)")

    # ── Final dedup check on selected ────────────────────────────────
    selected_hashes = [r["rendered_prompt_sha256"] for r in selected]
    if len(set(selected_hashes)) != len(selected):
        print("WARNING: selected set has duplicate prompts!")
        # De-dup final selection
        seen = set()
        unique_selected = []
        for r in selected:
            if r["rendered_prompt_sha256"] not in seen:
                seen.add(r["rendered_prompt_sha256"])
                unique_selected.append(r)
        print(f"  After final dedup: {len(unique_selected)}")
        selected = unique_selected

    # ── Output ───────────────────────────────────────────────────────
    output_records = []
    for rec in selected:
        out = dict(rec)
        out.pop("_token_count", None)
        out.pop("_tercile", None)
        out.pop("_allocation_stratum", None)
        output_records.append(out)

    payload = {
        "schema_version": "0.1",
        "profiling_seed": args.seed,
        "n_profiling_actions": len(output_records),
        "n_total_eligible_evaluation": len(eval_records),
        "token_tercile_boundaries": {"short_max": t1, "medium_max": t2},
        "stratum_counts": {str(k): v for k, v in allocated.items()},
        "leakage_audit_passed": len(all_issues) == 0,
        "ineligible_events": {
            "agentdojo_no_action": len([r for r in ineligible if r.get("source") == "agentdojo"]),
        },
        "calibration_strata": {
            "safetoolbench_unsafe": len(stb_cal),
            "tau2_benign": len(tau2_cal),
        },
        "selection_sha256": hashlib.sha256(
            json.dumps(sorted(r["event_id"] for r in output_records),
                       ensure_ascii=False).encode()
        ).hexdigest(),
        "records": output_records,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {len(output_records)} profiling inputs to {args.output}")
    print(f"Selection SHA-256: {payload['selection_sha256']}")

    assert len(output_records) == args.n_profiling, \
        f"Expected {args.n_profiling}, got {len(output_records)}"
    print("Exact count check: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
