#!/usr/bin/env python3
"""V3 Stratified profiling-input selection with exact quotas.

Uses real Qwen3 tokenizer for tercile assignment.  Supports:
  --length-quotas N,N,N  : exact per-tercile counts (short, medium, long)
  --safetoolbench-quota N : exact SafeToolBench calibration count
  --tau-hard-minimum N    : minimum tau2-bench hard-required events

Excludes AgentDojo (no call-time action).  Excludes duplicate prompts.
Outputs FIELD/PROVENANCE and QUOTA audits.

Usage:
    python scripts/stratify_and_audit_g2_prompts.py \
        --records data/processed/g2-materialized-records.jsonl \
        --manifest data/g2-event-selection.json \
        --output data/processed/g2-profiling-selection.v3.json \
        --n-profiling 128 \
        --length-quotas 43,43,42 \
        --safetoolbench-quota 32 \
        --tau-hard-minimum 32 \
        --seed 20260730
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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


FORBIDDEN_KEYWORDS = [
    "ground_truth_safety", "attack_label", "injection_label",
    "security_outcome", "benchmark_outcome", "post_execution",
    "target_function", "target_functions", "injection_task",
    "injection case", "quality_score", "risk_category",
    "calibration_label", "dangerous_true", "benign_expected",
    "hostile_injection", "prompt_injection", "indirect_prompt_injection",
]


def count_tokens(text: str) -> int:
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


def assign_tercile(token_count: int, t1: int, t2: int) -> str:
    if token_count <= t1:
        return "short"
    elif token_count <= t2:
        return "medium"
    return "long"


def deduplicate(records: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    dups = 0
    for r in records:
        sha = r.get("rendered_prompt_sha256", "")
        if sha in seen:
            dups += 1
            continue
        seen.add(sha)
        unique.append(r)
    if dups:
        print(f"  Dedup removed: {dups}")
    return unique


def audit_record(record: dict) -> list[str]:
    issues = []
    for field in ["state_summary", "user_intent", "tool_arguments"]:
        v = record.get(field, "")
        for kw in FORBIDDEN_KEYWORDS:
            if kw.lower() in v.lower():
                issues.append(
                    f"FORBIDDEN '{kw}' in {field} for {record['event_id']}"
                )
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=Path, default=Path("data/processed/g2-materialized-records.jsonl"))
    parser.add_argument("--manifest", type=Path, default=Path("data/g2-event-selection.json"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/g2-profiling-selection.v3.json"))
    parser.add_argument("--n-profiling", type=int, default=128)
    parser.add_argument("--length-quotas", type=str, default=None,
                        help="Comma-separated tercile quotas: short,medium,long (e.g. 43,43,42)")
    parser.add_argument("--safetoolbench-quota", type=int, default=0)
    parser.add_argument("--tau-hard-minimum", type=int, default=0)
    parser.add_argument("--seed", type=int, default=20260730)
    args = parser.parse_args()

    random.seed(args.seed)

    records = load_records(args.records)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    events = manifest["events"]
    event_index = {e["event_id"]: e for e in events}
    print(f"Loaded {len(records)} records")

    # ── FIELD / PROVENANCE AUDIT ──────────────────────────────────────
    all_issues = []
    for rec in records:
        all_issues.extend(audit_record(rec))
    if all_issues:
        print(f"\nFIELD / PROVENANCE AUDIT: FAIL ({len(all_issues)} issues)")
        for issue in all_issues[:20]:
            print(f"  {issue}")
        return 1
    print("FIELD / PROVENANCE AUDIT: PASS")

    # ── Filter eligible ──────────────────────────────────────────────
    eligible = [r for r in records if r.get("eligible_for_profiling", True)]
    ineligible = [r for r in records if not r.get("eligible_for_profiling", True)]
    dojo_ineligible = [r for r in ineligible if r.get("source") == "agentdojo"]
    print(f"Eligible: {len(eligible)}, Ineligible (AgentDojo): {len(dojo_ineligible)}")

    # Separate eval / cal
    eval_records = [r for r in eligible if event_index.get(r["event_id"], {}).get("split") == "evaluation"]
    cal_records = [r for r in records if event_index.get(r["event_id"], {}).get("split") == "calibration"]
    stb_cal = [r for r in cal_records if r.get("source") == "safetoolbench"]
    tau2_cal = [r for r in cal_records if r.get("source") == "tau2-bench"]
    print(f"Eval eligible: {len(eval_records)}, STB cal: {len(stb_cal)}, tau2 cal: {len(tau2_cal)}")

    # Dedup eval
    eval_records = deduplicate(eval_records)
    print(f"Eval after dedup: {len(eval_records)}")

    # ── Tokenize ─────────────────────────────────────────────────────
    print("Tokenizing with real Qwen3 tokenizer...")
    tok = _get_tokenizer()
    for rec in eval_records:
        rec["_tokens"] = count_tokens(
            rec.get("state_summary", "") + " " +
            rec.get("user_intent", "") + " " +
            rec.get("tool_arguments", "")
        )

    all_lens = sorted(r["_tokens"] for r in eval_records)
    n = len(all_lens)
    t1 = all_lens[n // 3]
    t2 = all_lens[2 * n // 3]
    print(f"Tercile boundaries: short<={t1} < medium<={t2} < long")
    for rec in eval_records:
        rec["_tercile"] = assign_tercile(rec["_tokens"], t1, t2)

    # ── Parse length quotas ──────────────────────────────────────────
    if args.length_quotas:
        parts = [int(x.strip()) for x in args.length_quotas.split(",")]
        if len(parts) != 3:
            print("ERROR: --length-quotas must have exactly 3 values", file=sys.stderr)
            return 1
        quotas = {"short": parts[0], "medium": parts[1], "long": parts[2]}
        if sum(parts) != args.n_profiling:
            print(f"ERROR: length quotas sum to {sum(parts)}, expected {args.n_profiling}", file=sys.stderr)
            return 1
        print(f"Length quotas: short={parts[0]}, medium={parts[1]}, long={parts[2]}")
    else:
        quotas = None

    # ── Build strata ─────────────────────────────────────────────────
    strata = defaultdict(list)
    for rec in eval_records:
        ev = event_index.get(rec["event_id"], {})
        key = (rec["_tercile"], rec["hard_required"])
        strata[key].append(rec)

    print(f"\nAvailable strata:")
    for key in sorted(strata.keys()):
        print(f"  tercile={key[0]}, hard={key[1]}: {len(strata[key])}")

    # ── Select with quotas ───────────────────────────────────────────
    selected = []

    if quotas:
        # Per-tercile selection with exact quotas
        tercile_selected = []
        for terc in ["short", "medium", "long"]:
            quota = quotas[terc]
            hard_key = (terc, True)
            nonhard_key = (terc, False)
            hard_avail = len(strata.get(hard_key, []))
            nonhard_avail = len(strata.get(nonhard_key, []))

            # Try to allocate proportionally to availability, but at least 1 hard if available
            total_avail = hard_avail + nonhard_avail
            if total_avail == 0:
                print(f"  WARNING: {terc} has 0 available records (quota {quota})")
                continue

            hard_ratio = hard_avail / total_avail if total_avail > 0 else 0
            from_hard = min(max(1, int(round(quota * hard_ratio))), hard_avail, quota)
            from_nonhard = min(quota - from_hard, nonhard_avail)

            # If we came up short, take more from hard if available
            shortfall = quota - from_hard - from_nonhard
            if shortfall > 0 and hard_avail > from_hard:
                extra = min(shortfall, hard_avail - from_hard)
                from_hard += extra
                shortfall = quota - from_hard - from_nonhard
            if shortfall > 0 and nonhard_avail > from_nonhard:
                extra = min(shortfall, nonhard_avail - from_nonhard)
                from_nonhard += extra

            if from_hard > 0:
                tercile_selected.extend(random.sample(strata[hard_key], from_hard))
            if from_nonhard > 0:
                tercile_selected.extend(random.sample(strata[nonhard_key], from_nonhard))

        selected = tercile_selected

        # Enforce tau-hard-minimum across selection while preserving tercile quotas
        n_hard = sum(1 for r in selected if r["hard_required"])
        if n_hard < args.tau_hard_minimum:
            needed = args.tau_hard_minimum - n_hard
            # Replace non-hard entries with hard ones from the same tercile
            for terc in ["short", "medium", "long"]:
                if needed <= 0:
                    break
                hard_key = (terc, True)
                # Find non-hard entries in this tercile
                terc_nonhard = [r for r in selected if r["_tercile"] == terc and not r["hard_required"]]
                # Find unused hard entries in same tercile
                used_ids = {r["event_id"] for r in selected}
                available_hard = [r for r in strata.get(hard_key, []) if r["event_id"] not in used_ids]
                # Replace
                for i in range(min(len(terc_nonhard), len(available_hard), needed)):
                    selected = [r for r in selected if r["event_id"] != terc_nonhard[i]["event_id"]]
                    selected.append(available_hard[i])
                    needed -= 1

    else:
        selected = random.sample(eval_records, min(args.n_profiling, len(eval_records)))

    # Final dedup
    hashes = [r["rendered_prompt_sha256"] for r in selected]
    if len(set(hashes)) != len(selected):
        seen = set()
        unique = []
        for r in selected:
            if r["rendered_prompt_sha256"] not in seen:
                seen.add(r["rendered_prompt_sha256"])
                unique.append(r)
        selected = unique

    # ── SafeToolBench calibration quota ──────────────────────────────
    stb_selected = []
    if args.safetoolbench_quota > 0 and stb_cal:
        stb_selected = random.sample(stb_cal, min(args.safetoolbench_quota, len(stb_cal)))
        # Hash-dedup STB selection
        stb_hashes = [r["rendered_prompt_sha256"] for r in stb_selected]
        if len(set(stb_hashes)) != len(stb_selected):
            seen = set()
            unique = []
            for r in stb_selected:
                if r["rendered_prompt_sha256"] not in seen:
                    seen.add(r["rendered_prompt_sha256"])
                    unique.append(r)
            stb_selected = unique

    # ── Clean output ─────────────────────────────────────────────────
    def clean(r):
        out = dict(r)
        out.pop("_tokens", None)
        # Keep _tercile for post-processing below
        return out

    output_records = [clean(r) for r in selected]

    n_hard_final = sum(1 for r in output_records if r["hard_required"])
    n_stb = len(stb_selected)

    # ── QUOTA AUDIT ──────────────────────────────────────────────────
    quota_issues = []
    if quotas:
        terc_counts = {"short": 0, "medium": 0, "long": 0}
        for r in selected:
            terc_counts[r["_tercile"]] += 1
        for terc, expected in quotas.items():
            actual = terc_counts[terc]
            if actual != expected:
                quota_issues.append(f"tercile {terc}: expected {expected}, got {actual}")
    if args.tau_hard_minimum and n_hard_final < args.tau_hard_minimum:
        quota_issues.append(f"tau-hard: expected >= {args.tau_hard_minimum}, got {n_hard_final}")
    if args.safetoolbench_quota and n_stb < args.safetoolbench_quota:
        quota_issues.append(f"STB-cal: expected {args.safetoolbench_quota}, got {n_stb}")

    if quota_issues:
        print(f"\nQUOTA AUDIT: FAIL")
        for q in quota_issues:
            print(f"  {q}")
        return 1
    print(f"\nQUOTA AUDIT: PASS")

    print(f"\nSelection: {len(output_records)} eval + {n_stb} STB-cal")
    print(f"  tau-hard: {n_hard_final}, dedup: OK")

    # ── Post-process: add v3 required fields ─────────────────────────
    print("Computing chat prompt hashes and token counts...")
    from src.verifier_prompting import render_chat_prompt, sha256_text
    policy_text = Path("experiments/prompts/policy-v1.txt").read_text(encoding="utf-8")
    template_text = Path("experiments/prompts/verifier-v1.txt").read_text(encoding="utf-8")
    tok = _get_tokenizer()

    for rec in output_records:
        chat_prompt = render_chat_prompt(rec, template_text, policy_text, tok)
        rec["profiling_prompt_sha256"] = sha256_text(chat_prompt)
        rec["profiling_input_tokens"] = len(tok.encode(chat_prompt, add_special_tokens=False))
        # Use _tercile (still present) for input_length_tercile
        rec["input_length_tercile"] = rec.pop("_tercile", "unknown")
        rec["selection_role"] = "tau2_eval"

    # ── Write output ─────────────────────────────────────────────────
    payload = {
        "schema_version": "0.3",
        "selection_contract_version": "g2-profiling-v3",
        "version": "v3",
        "profiling_seed": args.seed,
        "n_profiling_actions": len(output_records),
        "n_safetoolbench_calibration": n_stb,
        "token_tercile_boundaries": {"short_max": t1, "medium_max": t2},
        "field_provenance_audit": "PASS",
        "quota_audit": "PASS",
        "total_eligible_eval": len(eval_records),
        "ineligible_agentdojo": len(dojo_ineligible),
        "stratification": {
            "length_quotas": {"short": quotas["short"], "medium": quotas["medium"], "long": quotas["long"]} if quotas else {},
            "safetoolbench_quota": 0,
            "tau_hard_minimum": args.tau_hard_minimum,
        },
        "selection_sha256": hashlib.sha256(
            json.dumps(sorted(r["event_id"] for r in output_records),
                       ensure_ascii=False).encode()
        ).hexdigest(),
        "records": output_records,
        "calibration_records": stb_selected,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote to {args.output}")
    print(f"Selection SHA-256: {payload['selection_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
