#!/usr/bin/env python3
"""Audit a completed G3 tau-only replay without upgrading its scientific gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.g3_replay import REPLAY_CONTRACT_VERSION, write_json


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("experiments/configs/g3-minimal-tau-replay.json")
    )
    parser.add_argument(
        "--result", type=Path, default=Path("experiments/results/g3-tau2-minimal-replay.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("experiments/results/g3-tau2-minimal-replay-audit.json")
    )
    args = parser.parse_args()
    try:
        config = load_json(args.config)
        result = load_json(args.result)
        errors: list[str] = []
        if result.get("replay_contract_version") != REPLAY_CONTRACT_VERSION:
            errors.append("unexpected replay contract version")
        if result.get("experiment_id") != config.get("experiment_id"):
            errors.append("experiment_id mismatch")
        if result.get("result_status") != "partial_inconclusive_until_dangerous_actions_are_materialized":
            errors.append("tau-only result must remain partial/inconclusive")
        expected_scenarios = len(config["arrival_process"]["regimes"]) * len(
            config["arrival_process"]["seeds"]
        )
        scenarios = result.get("scenarios", [])
        if len(scenarios) != expected_scenarios:
            errors.append(f"expected {expected_scenarios} scenarios, found {len(scenarios)}")
        expected_methods = set(config["methods"])
        for scenario in scenarios:
            methods = scenario.get("methods", {})
            if set(methods) != expected_methods:
                errors.append(f"{scenario.get('regime')}/{scenario.get('seed')}: method set mismatch")
                continue
            if not scenario.get("trace_sha256"):
                errors.append(f"{scenario.get('regime')}/{scenario.get('seed')}: missing trace hash")
            for method_id, metrics in methods.items():
                if metrics.get("hard_job_downgrade_count") != 0:
                    errors.append(f"{scenario.get('regime')}/{scenario.get('seed')}/{method_id}: hard downgrade")
                if metrics.get("fail_open_count") != 0:
                    errors.append(f"{scenario.get('regime')}/{scenario.get('seed')}/{method_id}: fail open")
                if metrics.get("maximum_queue_wait_ms_observed", float("inf")) > float(
                    config["maximum_wait_ms"]
                ):
                    errors.append(f"{scenario.get('regime')}/{scenario.get('seed')}/{method_id}: wait cap exceeded")
        matched_danger = result.get("gate", {}).get("F5_matched_danger", {})
        if matched_danger.get("status") != "not_evaluable":
            errors.append("F5 must be marked not_evaluable for the tau-only pilot")
        if matched_danger.get("dangerous_action_evaluation_events") != 0:
            errors.append("tau-only pilot unexpectedly contains dangerous evaluation actions")
        artifact = {
            "schema_version": "0.1",
            "audit": "g3-minimal-tau-replay",
            "status": "passed" if not errors else "failed",
            "result_gate_status": result.get("gate", {}).get("status"),
            "scientific_gate": "not_promoted; F5 matched-danger remains not evaluable",
            "errors": errors,
        }
        write_json(args.output, artifact)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {args.output}: {artifact['status']}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
