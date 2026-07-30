"""Dependency-free correctness tests for the authorized G3 tau replay."""

from __future__ import annotations

import copy
import unittest

from src.g3_replay import (
    MODEL_SPECS,
    SCORE_CACHE_CONTRACT_VERSION,
    derive_light_threshold,
    run_tau_pilot,
    simulate_method,
    validate_score_cache,
)


def event(event_id: str, source: str, split: str, safety: str, hard: bool = False) -> dict:
    return {
        "event_id": event_id,
        "source": source,
        "split": split,
        "ground_truth_safety": safety,
        "hard_required": hard,
        "session_id": f"session:{event_id.split(':')[0]}",
    }


def cache_row(event_row: dict, tier: str, label: str = "0", risk: float = 0.0) -> dict:
    probabilities = {"0": 1.0 - risk, "1": risk, "2": 0.0}
    return {
        "score_cache_contract_version": SCORE_CACHE_CONTRACT_VERSION,
        "status": "ok",
        "tier": tier,
        "event_id": event_row["event_id"],
        "source": event_row["source"],
        "split": event_row["split"],
        "model_id": MODEL_SPECS[tier]["model_id"],
        "revision": MODEL_SPECS[tier]["revision"],
        "verifier_prompt_sha256": f"prompt-{event_row['event_id']}",
        "policy_sha256": "policy",
        "template_sha256": "template",
        "decoding_constraint": {"version": "test"},
        "selection_sha256": "selection",
        "input_tokens": 5,
        "input_length_tercile": "short",
        "output_tokens": 1,
        "raw_output": label,
        "label": label,
        "constrained_label_probabilities": probabilities,
        "risk_score": risk,
    }


class G3ReplayTests(unittest.TestCase):
    def test_calibration_excludes_unsafe_light_allow(self) -> None:
        manifest = {
            "events": [
                event("tau:cal", "tau2-bench", "calibration", "benign_expected"),
                event("stb:unsafe", "safetoolbench", "calibration", "unsafe_for_light_allow"),
            ]
        }
        scores = {
            "tau:cal": cache_row(manifest["events"][0], "light", "0", 0.1),
            "stb:unsafe": cache_row(manifest["events"][1], "light", "0", 0.2),
        }
        calibration = derive_light_threshold(scores, manifest, epsilon=0.99)
        self.assertLess(calibration["threshold"], 0.2)
        self.assertEqual(calibration["unsafe_false_allows_at_threshold"], 0)

    def test_score_cache_rejects_oracle_field(self) -> None:
        manifest = {
            "events": [
                event("tau:eval", "tau2-bench", "evaluation", "benign_expected"),
                event("tau:cal", "tau2-bench", "calibration", "benign_expected"),
                event("stb:cal", "safetoolbench", "calibration", "unsafe_for_light_allow"),
            ]
        }
        records = [cache_row(row, "light") for row in manifest["events"]]
        errors, _ = validate_score_cache(records, manifest, "light", {"short_max": 10, "medium_max": 20})
        self.assertEqual(errors, [])
        records[0]["ground_truth_safety"] = "benign_expected"
        errors, _ = validate_score_cache(records, manifest, "light", {"short_max": 10, "medium_max": 20})
        self.assertTrue(any("oracle" in message for message in errors))

    def test_hard_job_never_downgrades_and_timeout_abstains(self) -> None:
        trace = {
            "jobs": [
                {
                    "event_id": "hard",
                    "session_id": "s1",
                    "tenant_id": 0,
                    "arrival_ms": 0.0,
                    "sequence": 0,
                    "hard_required": True,
                    "ground_truth_safety": "benign_expected",
                    "risk_score": 0.0,
                    "model_decisions": {"light": {"label": "0"}, "strong": {"label": "1"}},
                    "service_draw_ms": {"light": 1.0, "strong": 20.0},
                    "estimated_service_cost": {"light": 0.1, "strong": 1.0},
                },
                {
                    "event_id": "waiting",
                    "session_id": "s2",
                    "tenant_id": 1,
                    "arrival_ms": 0.0,
                    "sequence": 1,
                    "hard_required": False,
                    "ground_truth_safety": "benign_expected",
                    "risk_score": 0.0,
                    "model_decisions": {"light": {"label": "0"}, "strong": {"label": "0"}},
                    "service_draw_ms": {"light": 1.0, "strong": 20.0},
                    "estimated_service_cost": {"light": 0.1, "strong": 1.0},
                },
            ]
        }
        metrics, outcomes = simulate_method(
            "calibrated_cascade_fifo", trace, threshold=1.0, maximum_wait_ms=5.0,
            tenant_count=2, drr_quantum=1.0,
        )
        by_id = {outcome["event_id"]: outcome for outcome in outcomes}
        self.assertEqual(by_id["hard"]["service_tier"], "strong")
        self.assertFalse(by_id["hard"]["hard_job_downgrade"])
        self.assertTrue(by_id["waiting"]["timed_out"])
        self.assertEqual(by_id["waiting"]["decision"], "abstain")
        self.assertEqual(metrics["fail_open_count"], 0)

    def test_small_pilot_is_deterministic_and_remains_inconclusive(self) -> None:
        events = [
            event("tau0:eval", "tau2-bench", "evaluation", "benign_expected", hard=True),
            event("tau1:eval", "tau2-bench", "evaluation", "benign_expected"),
            event("tau0:cal", "tau2-bench", "calibration", "benign_expected"),
            event("stb:cal", "safetoolbench", "calibration", "unsafe_for_light_allow"),
        ]
        manifest = {"events": events}
        light = [
            cache_row(events[0], "light", "1", 0.9),
            cache_row(events[1], "light", "0", 0.1),
            cache_row(events[2], "light", "0", 0.1),
            cache_row(events[3], "light", "1", 0.8),
        ]
        strong = [cache_row(row, "strong", "0", 0.1) for row in events]
        profiles = [
            {"status": "ok", "input_length_tercile": length, "wall_ms": wall}
            for length, wall in (("short", 2.0), ("medium", 3.0), ("long", 4.0))
        ]
        config = {
            "replay_contract_version": "g3-minimal-tau-replay-v1",
            "experiment_id": "test",
            "scope": {"tau2_evaluation_events": 2},
            "frozen_inputs": {
                "g2_profiling_selection": {
                    "token_tercile_boundaries": {"short_max": 10, "medium_max": 20},
                    "selection_sha256": "selection"
                }
            },
            "calibration": {"epsilon": 0.99},
            "tenants": {"count": 2, "heavy_tenant_share": 0.5},
            "arrival_process": {
                "seeds": [7],
                "regimes": [{"id": "low", "process": "poisson", "offered_load_rho": 0.35}],
            },
            "methods": [
                "full_strong_fifo", "calibrated_cascade_fifo", "static_risk_priority",
                "drr_fair", "safequeue_mve",
            ],
            "maximum_wait_ms": 5000,
            "drr": {"quantum": 1.0},
            "statistics": {"bootstrap_resamples": 20},
            "gate_thresholds": {"maximum_jain_drop_vs_drr": 0.02, "maximum_benign_pass_rate_drop": 0.03},
        }
        first = run_tau_pilot(manifest, light, strong, profiles, profiles, config, {"test": True})
        second = run_tau_pilot(manifest, light, strong, profiles, profiles, copy.deepcopy(config), {"test": True})
        self.assertEqual(first["scenarios"], second["scenarios"])
        self.assertEqual(first["gate"]["status"], "partial_inconclusive")
        self.assertEqual(first["gate"]["F5_matched_danger"]["status"], "not_evaluable")


if __name__ == "__main__":
    unittest.main()
