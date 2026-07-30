#!/usr/bin/env python3
"""Select the new 128-input, 3-repetition service profile for signed G3-R1.

G3-R1 adds 300 materialized dangerous SafeToolBench evaluation plans, so it
must not silently reuse the old G2 v3 service sample.  This selector derives a
fresh, exact-quota profile set from the signed R1 evaluation workload only:
80 tau2 actions and 48 SafeToolBench dangerous actions, with 43/43/42 prompt
length quotas and at least 24 tau2 hard actions.  No benchmark label or model
output influences selection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.stratify_and_audit_g2_prompts import audit_materialized_record
from src.verifier_prompting import render_chat_prompt, sha256_text


SELECTION_CONTRACT_VERSION = "g3r1-profiling-v1"
TOKENIZER_ID = "Qwen/Qwen3-1.7B"
TOKENIZER_REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"
LENGTH_ORDER = ("short", "medium", "long")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def load_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, dict) or not record.get("event_id"):
            raise ValueError(f"{path}:{line_number}: missing event_id")
        records.append(record)
    return records


def parse_length_quotas(raw: str, n_profiling: int) -> dict[str, int]:
    try:
        values = [int(value.strip()) for value in raw.split(",")]
    except ValueError as exc:
        raise ValueError("--length-quotas must be three comma-separated integers") from exc
    if len(values) != 3 or any(value <= 0 for value in values) or sum(values) != n_profiling:
        raise ValueError("--length-quotas must be three positive values summing to --n-profiling")
    return dict(zip(LENGTH_ORDER, values, strict=True))


def compute_terciles(lengths: list[int]) -> tuple[int, int]:
    if len(lengths) < 3:
        raise ValueError("need at least three model-ready evaluation inputs")
    ordered = sorted(lengths)
    return ordered[len(ordered) // 3], ordered[(2 * len(ordered)) // 3]


def assign_tercile(token_count: int, short_max: int, medium_max: int) -> str:
    if token_count <= short_max:
        return "short"
    if token_count <= medium_max:
        return "medium"
    return "long"


def bounded_proportional_allocation(total: int, capacities: dict[str, int]) -> dict[str, int]:
    """Allocate exactly ``total`` over fixed lengths without exceeding capacity."""
    if total < 0 or total > sum(capacities.values()):
        raise ValueError(f"cannot allocate {total} from capacities {capacities}")
    if total == 0:
        return {key: 0 for key in capacities}
    capacity_total = sum(capacities.values())
    ideal = {key: total * capacities[key] / capacity_total for key in capacities}
    allocation = {key: min(int(ideal[key]), capacities[key]) for key in capacities}
    remaining = total - sum(allocation.values())
    while remaining:
        options = [key for key in capacities if allocation[key] < capacities[key]]
        if not options:
            raise AssertionError("allocation exhausted all capacities")
        key = max(options, key=lambda item: (ideal[item] - allocation[item], capacities[item] - allocation[item], item))
        allocation[key] += 1
        remaining -= 1
    return allocation


def stable_sample(rng: random.Random, candidates: list[dict[str, Any]], count: int, label: str) -> list[dict[str, Any]]:
    ordered = sorted(candidates, key=lambda item: str(item["record"]["event_id"]))
    if count > len(ordered):
        raise ValueError(f"{label}: need {count}, have {len(ordered)}")
    return rng.sample(ordered, count)


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
                "selection_source_split": record["selection_source_split"],
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


def select_with_quotas(
    candidates: list[dict[str, Any]],
    *,
    length_quotas: dict[str, int],
    tau_quota: int,
    safetoolbench_quota: int,
    tau_hard_minimum: int,
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if tau_quota + safetoolbench_quota != sum(length_quotas.values()):
        raise ValueError("source quotas must sum to total profile count")
    if tau_hard_minimum > tau_quota:
        raise ValueError("tau hard minimum exceeds tau quota")
    by_length = {length: [] for length in LENGTH_ORDER}
    stb_by_length = {length: [] for length in LENGTH_ORDER}
    tau_by_length = {length: [] for length in LENGTH_ORDER}
    tau_hard_by_length = {length: [] for length in LENGTH_ORDER}
    for candidate in candidates:
        length = candidate["input_length_tercile"]
        by_length[length].append(candidate)
        source = candidate["record"]["source"]
        if source == "safetoolbench":
            stb_by_length[length].append(candidate)
        elif source == "tau2-bench":
            tau_by_length[length].append(candidate)
            if candidate["record"].get("hard_required"):
                tau_hard_by_length[length].append(candidate)
        else:
            raise ValueError(f"unsupported source in profiling pool: {source!r}")
    for length in LENGTH_ORDER:
        if len(by_length[length]) < length_quotas[length]:
            raise ValueError(f"{length}: only {len(by_length[length])} unique prompts for quota {length_quotas[length]}")
    stb_allocation = bounded_proportional_allocation(
        safetoolbench_quota,
        {length: min(len(stb_by_length[length]), length_quotas[length]) for length in LENGTH_ORDER},
    )
    hard_allocation = bounded_proportional_allocation(
        tau_hard_minimum,
        {
            length: min(len(tau_hard_by_length[length]), length_quotas[length] - stb_allocation[length])
            for length in LENGTH_ORDER
        },
    )
    rng = random.Random(seed)
    selected: list[dict[str, Any]] = []
    for length in LENGTH_ORDER:
        selected_stb = stable_sample(rng, stb_by_length[length], stb_allocation[length], f"SafeToolBench/{length}")
        selected_hard = stable_sample(rng, tau_hard_by_length[length], hard_allocation[length], f"tau hard/{length}")
        selected_ids = {item["record"]["event_id"] for item in selected_stb + selected_hard}
        fill = length_quotas[length] - len(selected_stb) - len(selected_hard)
        selected_tau = stable_sample(
            rng,
            [item for item in tau_by_length[length] if item["record"]["event_id"] not in selected_ids],
            fill,
            f"tau fill/{length}",
        )
        selected.extend(selected_stb + selected_hard + selected_tau)
    rng.shuffle(selected)
    source_counts = Counter(item["record"]["source"] for item in selected)
    length_counts = Counter(item["input_length_tercile"] for item in selected)
    tau_hard_count = sum(
        item["record"]["source"] == "tau2-bench" and bool(item["record"].get("hard_required"))
        for item in selected
    )
    if len(selected) != sum(length_quotas.values()) or len({item["record"]["event_id"] for item in selected}) != len(selected):
        raise AssertionError("profile selection cardinality/uniqueness violation")
    if dict(length_counts) != length_quotas:
        raise AssertionError("profile length quota violation")
    if source_counts["tau2-bench"] != tau_quota or source_counts["safetoolbench"] != safetoolbench_quota:
        raise AssertionError("profile source quota violation")
    if tau_hard_count < tau_hard_minimum:
        raise AssertionError("profile tau hard minimum violation")
    return selected, {
        "length_quotas": length_quotas,
        "tau2_evaluation_quota": tau_quota,
        "safetoolbench_dangerous_evaluation_quota": safetoolbench_quota,
        "tau_hard_minimum": tau_hard_minimum,
        "actual_length_counts": {length: length_counts[length] for length in LENGTH_ORDER},
        "actual_source_counts": dict(source_counts),
        "actual_tau_hard_count": tau_hard_count,
        "safetoolbench_allocation_by_length": stb_allocation,
        "tau_hard_allocation_by_length": hard_allocation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, default=Path("data/processed/g3r1-materialized-records.jsonl"))
    parser.add_argument("--manifest", type=Path, default=Path("data/g3r1-event-selection.owner-signed.json"))
    parser.add_argument(
        "--output", type=Path, default=Path("data/processed/g3r1-profiling-selection.v1.json")
    )
    parser.add_argument("--n-profiling", type=int, default=128)
    parser.add_argument("--length-quotas", default="43,43,42")
    parser.add_argument("--tau2-quota", type=int, default=80)
    parser.add_argument("--safetoolbench-quota", type=int, default=48)
    parser.add_argument("--tau-hard-minimum", type=int, default=24)
    parser.add_argument("--seed", type=int, default=20260730)
    parser.add_argument("--tokenizer-id", default=TOKENIZER_ID)
    parser.add_argument("--tokenizer-revision", default=TOKENIZER_REVISION)
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.n_profiling <= 0:
            raise ValueError("--n-profiling must be positive")
        length_quotas = parse_length_quotas(args.length_quotas, args.n_profiling)
        manifest = load_json(args.manifest)
        if manifest.get("status") != "owner_signed":
            raise ValueError("G3-R1 profiling requires an owner_signed manifest")
        events = {str(event["event_id"]): event for event in manifest.get("events", [])}
        records = load_records(args.records)
        policy = (PROJECT_ROOT / "experiments/prompts/policy-v1.txt").read_text(encoding="utf-8")
        template = (PROJECT_ROOT / "experiments/prompts/verifier-v1.txt").read_text(encoding="utf-8")
        issues: list[str] = []
        for record in records:
            event = events.get(str(record["event_id"]))
            if event is None:
                issues.append(f"{record['event_id']}: absent from signed manifest")
                continue
            if record.get("source") != event.get("source"):
                issues.append(f"{record['event_id']}: source mismatch")
            if bool(record.get("hard_required")) != bool(event.get("hard_required")):
                issues.append(f"{record['event_id']}: hard_required mismatch")
            issues.extend(audit_materialized_record(record, template, policy))
        if len(records) != 1000:
            issues.append(f"expected 1,000 materialized records, found {len(records)}")
        if len({str(record["event_id"]) for record in records}) != len(records):
            issues.append("materialized records contain duplicate event IDs")
        if issues:
            raise ValueError("materialized input audit failed: " + "; ".join(issues[:12]))
        print(f"FIELD / PROVENANCE AUDIT: PASS ({len(records)} materialized records)")
        if args.audit_only:
            return 0
        candidates: list[dict[str, Any]] = []
        for record in records:
            event = events[str(record["event_id"])]
            if not record.get("eligible_for_profiling", True):
                continue
            if record.get("source") == "tau2-bench" and event.get("split") == "evaluation":
                role = "tau2_evaluation"
            elif record.get("source") == "safetoolbench" and event.get("split") == "evaluation":
                if not event.get("hard_required"):
                    raise ValueError(f"{record['event_id']}: dangerous SafeToolBench evaluation row is not hard-required")
                role = "safetoolbench_dangerous_evaluation"
            else:
                continue
            candidates.append({"record": record, "selection_source_role": role})
        if len(candidates) != 800:
            raise ValueError(f"expected 800 replay-evaluation candidates, found {len(candidates)}")
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_id, revision=args.tokenizer_revision)
        unique: list[dict[str, Any]] = []
        seen: set[str] = set()
        for candidate in sorted(candidates, key=lambda item: str(item["record"]["event_id"])):
            prompt = render_chat_prompt(candidate["record"], template, policy, tokenizer)
            prompt_sha = sha256_text(prompt)
            if prompt_sha in seen:
                continue
            seen.add(prompt_sha)
            candidate["profiling_prompt_sha256"] = prompt_sha
            candidate["profiling_input_tokens"] = len(tokenizer.encode(prompt, add_special_tokens=False))
            unique.append(candidate)
        if len(unique) < args.n_profiling:
            raise ValueError(f"only {len(unique)} unique model-ready evaluation prompts remain")
        short_max, medium_max = compute_terciles([item["profiling_input_tokens"] for item in unique])
        for candidate in unique:
            candidate["input_length_tercile"] = assign_tercile(
                candidate["profiling_input_tokens"], short_max, medium_max
            )
        selected, stratification = select_with_quotas(
            unique,
            length_quotas=length_quotas,
            tau_quota=args.tau2_quota,
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
                    "selection_role": "replay_evaluation",
                    "selection_source_role": candidate["selection_source_role"],
                    "selection_source_split": "evaluation",
                }
            )
            output_records.append(output)
        payload = {
            "schema_version": "0.1",
            "selection_contract_version": SELECTION_CONTRACT_VERSION,
            "event_manifest_sha256": manifest["selection_sha256"],
            "profile_scope": "signed G3-R1 replay evaluation workload; calibration inputs excluded from latency sampling",
            "code": {
                "git_revision": git_revision(),
                "selector_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            },
            "profiling_seed": args.seed,
            "n_profiling_actions": len(output_records),
            "tokenizer": {"model_id": args.tokenizer_id, "revision": args.tokenizer_revision},
            "token_tercile_boundaries": {"short_max": short_max, "medium_max": medium_max},
            "pool": {
                "evaluation_candidates_before_deduplication": len(candidates),
                "unique_model_ready_prompts": len(unique),
                "duplicate_prompts_removed": len(candidates) - len(unique),
                "sources": dict(Counter(item["record"]["source"] for item in unique)),
            },
            "stratification": {
                **stratification,
                "length_measurement": "full Qwen non-thinking chat prompt tokens",
                "selection_basis": "source, evaluation split, structural hard_required, full prompt length, fixed seed; never benchmark labels or model outputs",
            },
            "leakage_audit": {
                "passed": True,
                "records_audited": len(records),
                "scope": "all model-visible fields plus rendered prompt hash provenance",
            },
            "selection_sha256": canonical_selection_sha(output_records),
            "records": output_records,
        }
        if len(output_records) != args.n_profiling:
            raise AssertionError("exact 128 profile count check failed")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {len(output_records)} inputs to {args.output}")
    print(f"Selection SHA-256: {payload['selection_sha256']}")
    print("QUOTA AUDIT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
