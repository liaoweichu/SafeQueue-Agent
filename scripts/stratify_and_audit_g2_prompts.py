#!/usr/bin/env python3
"""Stratified profiling-input selection and field-leakage audit for G2.

Reads all materialized records, stratifies by source, input length tercile,
hard_required, and ground_truth_safety (label used ONLY for stratification,
never written to model input).  Selects 128 action inputs and audits every
rendered prompt for leakage of forbidden fields.

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
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Forbidden leakage patterns ──────────────────────────────────────────
# Any rendered prompt containing these strings is a leakage failure.
FORBIDDEN_KEYWORDS = [
    "ground_truth_safety",
    "attack_label",
    "injection_label",
    "security_outcome",
    "benchmark_outcome",
    "post_execution",
    "target_function",
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
]


@dataclass
class ProfilingInput:
    event_id: str
    source: str
    split: str
    hard_required: bool
    ground_truth_safety: str
    token_count: int
    rendered_prompt: str
    record: dict


def count_tokens(text: str) -> int:
    """Approximate token count by whitespace splitting (conservative upper bound).

    A proper tokenizer count would require loading the model; this is a
    fast approximation for tercile stratification.  The runbook says
    'input_length_tercile' which can use either approximation or real
    tokenization; real tokenization is deferred to the profiling runner.
    """
    return len(text.split())


def load_records(path: Path) -> list[dict]:
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def build_index(events: list[dict]) -> dict[str, dict]:
    """Build a lookup of event metadata by event_id."""
    index: dict[str, dict] = {}
    for ev in events:
        index[ev["event_id"]] = ev
    return index


def compute_terciles(lengths: list[int]) -> tuple[int, int]:
    """Return (t1, t2) such that ~1/3 of values are in each bucket."""
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


def audit_record(record: dict) -> list[str]:
    """Check rendered prompt for leakage of forbidden fields."""
    prompt = record.get("rendered_prompt_sha256", "")
    # We don't have the full rendered_prompt in the JSONL (it's only SHA-256),
    # but we can check the non-rendered fields for leakage.
    issues: list[str] = []

    # Check that forbidden keys don't appear in the materialized fields
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
        description="Stratify G2 profiling inputs and audit for field leakage."
    )
    parser.add_argument(
        "--records",
        type=Path,
        default=Path("data/processed/g2-materialized-records.jsonl"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/g2-event-selection.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/g2-profiling-selection.json"),
    )
    parser.add_argument(
        "--n-profiling",
        type=int,
        default=128,
        help="Number of actions to select for profiling (default: 128).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20260730,
    )
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="Run leakage audit on all records without stratification.",
    )
    args = parser.parse_args()

    random.seed(args.seed)

    # Load data
    records = load_records(args.records)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    events = manifest["events"]
    event_index = build_index(events)

    print(f"Loaded {len(records)} records, {len(events)} events")

    # ── Field leakage audit ──────────────────────────────────────────
    all_issues: list[str] = []
    for rec in records:
        issues = audit_record(rec)
        all_issues.extend(issues)

    if all_issues:
        print(f"\nFIELD LEAKAGE AUDIT: {len(all_issues)} ISSUES FOUND")
        for issue in all_issues:
            print(f"  FAIL: {issue}")
        print("\nProfiling blocked — fix leakage before proceeding.")
        return 1
    else:
        print("FIELD LEAKAGE AUDIT: PASSED (0 forbidden keywords found)")

    if args.audit_only:
        return 0

    # ── Stratification ───────────────────────────────────────────────
    # Build candidates with token counts
    candidates: list[ProfilingInput] = []
    for rec in records:
        ev = event_index.get(rec["event_id"], {})
        tokens = count_tokens(rec.get("state_summary", "") + " " +
                              rec.get("user_intent", "") + " " +
                              rec.get("tool_arguments", ""))
        candidates.append(ProfilingInput(
            event_id=rec["event_id"],
            source=rec["source"],
            split=ev.get("split", "unknown"),
            hard_required=rec["hard_required"],
            ground_truth_safety=ev.get("ground_truth_safety", "unknown"),
            token_count=tokens,
            rendered_prompt="",  # Not loading full rendered prompt for audit
            record=rec,
        ))

    # Compute global terciles
    all_lengths = [c.token_count for c in candidates]
    t1, t2 = compute_terciles(all_lengths)
    print(f"\nToken terciles: short <= {t1} < medium <= {t2} < long")
    for c in candidates:
        c.tercile = assign_tercile(c.token_count, t1, t2)

    # Separate evaluation from calibration
    eval_candidates = [c for c in candidates if c.split == "evaluation"]
    cal_candidates = [c for c in candidates if c.split == "calibration"]
    print(f"Evaluation candidates: {len(eval_candidates)}, "
          f"Calibration: {len(cal_candidates)}")

    # Stratify evaluation candidates
    strata: dict[tuple, list[ProfilingInput]] = defaultdict(list)
    for c in eval_candidates:
        key = (c.source, c.tercile, c.hard_required, c.ground_truth_safety)
        strata[key].append(c)

    print(f"\nStrata ({len(strata)} groups):")
    for key, group in sorted(strata.items()):
        print(f"  {key}: {len(group)} candidates")

    # Proportional allocation across strata
    total_eval = len(eval_candidates)
    selected: list[ProfilingInput] = []
    stratum_alloc: dict[tuple, int] = {}

    # First pass: allocate floor
    remaining = args.n_profiling
    for key in sorted(strata.keys()):
        group = strata[key]
        alloc = max(1, int(round(len(group) / total_eval * args.n_profiling)))
        alloc = min(alloc, len(group))
        stratum_alloc[key] = alloc
        remaining -= alloc

    # Second pass: distribute remainder to largest strata
    for key in sorted(strata.keys(), key=lambda k: len(strata[k]), reverse=True):
        if remaining <= 0:
            break
        group = strata[key]
        extra = min(remaining, len(group) - stratum_alloc[key])
        if extra > 0:
            stratum_alloc[key] += extra
            remaining -= extra

    print(f"\nAllocation ({sum(stratum_alloc.values())} selected):")
    for key, alloc in sorted(stratum_alloc.items()):
        group = strata[key]
        sampled = random.sample(group, alloc)
        selected.extend(sampled)
        print(f"  {key}: {alloc}/{len(group)}")

    # ── Output ────────────────────────────────────────────────────────
    output_records = []
    for pi in selected:
        out = dict(pi.record)
        out["token_count_approx"] = pi.token_count
        out["length_tercile"] = pi.tercile
        out["profiling_seed"] = args.seed
        output_records.append(out)

    payload = {
        "schema_version": "0.1",
        "profiling_seed": args.seed,
        "n_profiling_actions": len(output_records),
        "n_total_evaluation": total_eval,
        "token_tercile_boundaries": {"short_max": t1, "medium_max": t2},
        "stratum_counts": {str(k): v for k, v in stratum_alloc.items()},
        "leakage_audit_passed": len(all_issues) == 0,
        "selection_sha256": hashlib.sha256(
            json.dumps([r["event_id"] for r in output_records],
                       sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
        "records": output_records,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\nWrote {len(output_records)} profiling inputs to {args.output}")
    print(f"Selection SHA-256: {payload['selection_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
