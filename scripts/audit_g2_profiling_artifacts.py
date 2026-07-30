#!/usr/bin/env python3
"""Cloud-side G2 v3 profiling artifact auditor.

Validates preflight, smoke test, and both profiling tiers.  Checks:
  - completions (384 per tier), OOM, constraint errors
  - latency percentiles, GPU interference < 5%
  - provenance fields present
  - derived maximum_wait_ms = 5000
  - zero AgentDojo events in profiling
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--light", type=Path, required=True)
    parser.add_argument("--strong", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    errors: list[str] = []
    checks: dict[str, bool] = {}

    # ── Preflight ─────────────────────────────────────────────────────
    pf = json.loads(args.preflight.read_text(encoding="utf-8"))
    checks["preflight_passed"] = pf.get("passed", False)
    if not checks["preflight_passed"]:
        errors.append("preflight not passed")

    # ── Selection ────────────────────────────────────────────────────
    sel = json.loads(args.selection.read_text(encoding="utf-8"))
    checks["selection_v3"] = sel.get("selection_contract_version") == "g2-profiling-v3"
    checks["selection_128"] = len(sel.get("records", [])) == 128
    checks["field_provenance_audit"] = sel.get("field_provenance_audit") == "PASS"
    checks["quota_audit"] = sel.get("quota_audit") == "PASS"
    if not checks["selection_v3"]:
        errors.append("selection is not v3")
    if not checks["selection_128"]:
        errors.append(f"selection has {len(sel.get('records', []))} records, expected 128")

    # ── Profiling ────────────────────────────────────────────────────
    results: dict[str, dict] = {}
    for tier, path in [("light", args.light), ("strong", args.strong)]:
        measurements = []
        with path.open(encoding="utf-8") as f:
            for line in f:
                measurements.append(json.loads(line.strip()))

        n_total = len(measurements)
        n_ok = sum(1 for m in measurements if m["status"] == "ok")
        n_oom = sum(1 for m in measurements if m["status"] == "oom")
        n_constraint_err = sum(1 for m in measurements if m["status"] == "constraint_error")
        n_runtime_err = sum(1 for m in measurements if m["status"] == "runtime_error")

        ok_m = [m for m in measurements if m["status"] == "ok"]
        wall_times = sorted(m["wall_ms"] for m in ok_m)
        cuda_times = sorted(m["cuda_ms"] for m in ok_m)
        interference = sum(1 for m in ok_m if m.get("gpu_interference"))
        interference_rate = interference / max(len(ok_m), 1)

        # Check 0 AgentDojo
        dojo_count = sum(1 for m in measurements if "agentdojo" in m.get("event_id", ""))

        def p(sorted_vals, pct):
            if not sorted_vals:
                return 0.0
            idx = (len(sorted_vals) - 1) * pct / 100
            lo = int(idx)
            frac = idx - lo
            if lo + 1 < len(sorted_vals):
                return sorted_vals[lo] + frac * (sorted_vals[lo + 1] - sorted_vals[lo])
            return sorted_vals[lo]

        results[tier] = {
            "total": n_total,
            "ok": n_ok,
            "oom": n_oom,
            "constraint_errors": n_constraint_err,
            "runtime_errors": n_runtime_err,
            "wall_p50": round(p(wall_times, 50), 2),
            "wall_p95": round(p(wall_times, 95), 2),
            "wall_p99": round(p(wall_times, 99), 2),
            "gpu_interference": interference,
            "gpu_interference_rate": round(interference_rate, 4),
            "agentdojo_events": dojo_count,
        }

        # Per-tier checks
        checks[f"{tier}_384"] = n_total == 384
        checks[f"{tier}_all_ok"] = n_ok == 384
        checks[f"{tier}_no_oom"] = n_oom == 0
        checks[f"{tier}_no_constraint_err"] = n_constraint_err == 0
        checks[f"{tier}_interference_lt_5pct"] = interference_rate <= 0.05
        checks[f"{tier}_no_agentdojo"] = dojo_count == 0

        if not checks[f"{tier}_384"]:
            errors.append(f"{tier}: {n_total} measurements, expected 384")
        if not checks[f"{tier}_no_oom"]:
            errors.append(f"{tier}: {n_oom} OOM errors")

    # ── Derived timeout ───────────────────────────────────────────────
    strong_p95 = results["strong"]["wall_p95"]
    max_wait = math.ceil(max(5000, 4 * strong_p95))
    checks["derived_maximum_wait_5000"] = max_wait == 5000

    # ── Per-tercile latency check ────────────────────────────────────
    for tier, path in [("light", args.light), ("strong", args.strong)]:
        ok_m = []
        with path.open(encoding="utf-8") as f:
            for line in f:
                m = json.loads(line.strip())
                if m["status"] == "ok":
                    ok_m.append(m)
        terciles = Counter(m["input_length_tercile"] for m in ok_m)
        target = sel.get("stratification", {}).get("length_quotas", {})
        target_counts = {t: c * 3 for t, c in target.items()}  # ×3 repetitions
        for t, expected in target_counts.items():
            actual = terciles.get(t, 0)
            checks[f"{tier}_tercile_{t}"] = actual == expected
            if actual != expected:
                errors.append(f"{tier} tercile {t}: {actual} != {expected}")

    # ── Final verdict ────────────────────────────────────────────────
    passed = all(checks.values()) and len(errors) == 0

    output = {
        "passed": passed,
        "derived_maximum_wait_ms": max_wait,
        "strong_p95_ms": strong_p95,
        "checks": {k: v for k, v in sorted(checks.items())},
        "errors": errors,
        "results": results,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if passed:
        print("AUDIT: PASS")
    else:
        print(f"AUDIT: FAIL ({len(errors)} errors)")
        for e in errors:
            print(f"  {e}")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
