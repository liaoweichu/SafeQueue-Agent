"""Dependency-free checks for the G3-R1 serial abstain escalation repair."""

from __future__ import annotations

import unittest

from scripts.prepare_g3r1_dangerous_holdout import canonical_sha256
from scripts.finalize_g3r1_holdout_signoff import validate_review
from src.g3_replay import MODEL_SPECS
from src.g3r1_replay import (
    SCORE_CACHE_CONTRACT_VERSION,
    _verification_plan,
    run_repair_replay,
    simulate_method,
    validate_manifest_readiness,
    validate_score_cache,
)


def job(
    event_id: str,
    *,
    light_label: str = "0",
    strong_label: str = "0",
    risk: float = 0.0,
    hard: bool = False,
    light_ms: float = 1.0,
    strong_ms: float = 10.0,
) -> dict:
    return {
        "event_id": event_id,
        "session_id": f"session:{event_id}",
        "tenant_id": 0,
        "arrival_ms": 0.0,
        "sequence": 0,
        "hard_required": hard,
        "ground_truth_safety": "benign_expected",
        "risk_score": risk,
        "light_label": light_label,
        "strong_label": strong_label,
        "service_draw_ms": {"light": light_ms, "strong": strong_ms},
    }


def cache_row(event: dict, tier: str, label: str = "0", risk: float = 0.0) -> dict:
    probabilities = {"0": 0.0, "1": 0.0, "2": 0.0}
    probabilities[label] = 1.0
    risk = 0.0 if label == "0" else 1.0
    return {
        "score_cache_contract_version": SCORE_CACHE_CONTRACT_VERSION,
        "status": "ok",
        "tier": tier,
        "event_id": event["event_id"],
        "source": event["source"],
        "split": event["split"],
        "model_id": MODEL_SPECS[tier]["model_id"],
        "revision": MODEL_SPECS[tier]["revision"],
        "verifier_prompt_sha256": f"prompt-{event['event_id']}",
        "input_tokens": 5,
        "input_length_tercile": "short",
        "output_tokens": 1,
        "raw_output": label,
        "label": label,
        "constrained_label_probabilities": probabilities,
        "risk_score": risk,
        "policy_sha256": "policy",
        "template_sha256": "template",
        "decoding_constraint": {"version": "test"},
        "event_manifest_sha256": "selection",
        "service_profile_selection_sha256": "profile-selection",
        "code_git_revision": "test",
    }


class G3R1ReplayTests(unittest.TestCase):
    def test_light_abstain_is_paid_and_escalated_to_strong(self) -> None:
        trace = {"jobs": [job("a", light_label="2", strong_label="0", light_ms=2.0, strong_ms=7.0)]}
        metrics, outcomes = simulate_method(
            "light_abstain_escalating_cascade_fifo",
            trace,
            threshold=1.0,
            maximum_wait_ms=5000.0,
            tenant_count=1,
        )
        outcome = outcomes[0]
        self.assertEqual(outcome["verifier_stages"], ["light", "strong"])
        self.assertEqual(outcome["decision"], "allow")
        self.assertEqual(outcome["escalation_reason"], "light_abstain_to_strong")
        self.assertEqual(outcome["service_ms"], 9.0)
        self.assertEqual(metrics["light_abstain_escalation_count"], 1)
        self.assertEqual(metrics["final_light_abstain_count"], 0)

    def test_light_allow_above_threshold_is_also_paid_then_escalated(self) -> None:
        candidate = job("a", light_label="0", strong_label="1", risk=0.9)
        self.assertEqual(
            _verification_plan("light_abstain_escalating_cascade_fifo", candidate, threshold=0.1),
            (["light", "strong"], "1", "risk_threshold_to_strong"),
        )
        candidate["risk_score"] = 0.1
        self.assertEqual(
            _verification_plan("light_abstain_escalating_cascade_fifo", candidate, threshold=0.1),
            (["light"], "0", "direct_light_allow"),
        )

    def test_hard_job_bypasses_light_and_never_downgrades(self) -> None:
        trace = {"jobs": [job("hard", light_label="0", strong_label="1", hard=True)]}
        metrics, outcomes = simulate_method(
            "light_abstain_escalating_cascade_fifo",
            trace,
            threshold=1.0,
            maximum_wait_ms=5000.0,
            tenant_count=1,
        )
        self.assertEqual(outcomes[0]["verifier_stages"], ["strong"])
        self.assertEqual(outcomes[0]["decision"], "block")
        self.assertEqual(metrics["hard_job_downgrade_count"], 0)

    def test_pending_review_cannot_enter_replay(self) -> None:
        manifest = {"status": "candidate_pending_owner_signoff", "events": []}
        errors = validate_manifest_readiness(manifest)
        self.assertTrue(any("not owner_signed" in error for error in errors))

    def test_selection_hash_excludes_mutable_review_attestations(self) -> None:
        event = {
            "source": "safetoolbench",
            "source_version": "test",
            "domain": "PD_SA",
            "session_id": "event",
            "event_id": "event",
            "split": "evaluation",
            "event_kind": "prospective_risky_tool_plan",
            "source_file": "source.json",
            "source_row_index": 1,
            "instruction_sha256": "hash",
            "risk_category": "Physical Injury",
            "quality_score": 7,
            "tool_names": ["tool"],
            "hard_required": True,
            "hard_decision_basis": "conservative",
            "ground_truth_safety": "unsafe_for_light_allow",
            "semantic_label_review": "PENDING_OWNER_SIGNOFF",
            "hard_mapping_status": "pending_owner_capability_review",
        }
        before = canonical_sha256([event])
        event["semantic_label_review"] = "PASS"
        event["hard_mapping_status"] = "owner_signed_conservative_envelope"
        self.assertEqual(before, canonical_sha256([event]))

    def test_completed_row_ledger_is_required_for_owner_signoff(self) -> None:
        events = [
            {
                "event_id": f"stb:eval:{index}", "source": "safetoolbench", "split": "evaluation",
                "source_file": "data/data/query_PD_SA.json", "source_row_index": index,
                "instruction_sha256": f"hash-{index}", "risk_category": "Physical Injury",
                "semantic_label_review": "PENDING_OWNER_SIGNOFF",
                "hard_mapping_status": "pending_owner_capability_review",
            }
            for index in range(300)
        ]
        manifest = {"events": events, "selection_sha256": canonical_sha256(events)}
        ledger = {
            event["event_id"]: {
                "event_id": event["event_id"], "source_file": event["source_file"],
                "source_row_index": str(event["source_row_index"]),
                "instruction_sha256": event["instruction_sha256"], "risk_category": event["risk_category"],
                "source_row_integrity": "PASS", "calibration_disjointness": "PASS",
                "semantic_label_review": "PASS", "hard_capability_review": "PASS",
                "reviewer": "owner", "reviewed_at": "2026-07-30",
            }
            for event in events
        }
        self.assertEqual(validate_review(manifest, ledger), [])
        ledger["stb:eval:0"]["semantic_label_review"] = "PENDING_OWNER_SIGNOFF"
        self.assertTrue(validate_review(manifest, ledger))

    def test_score_cache_requires_new_manifest_and_service_provenance(self) -> None:
        event = {
            "event_id": "tau:eval",
            "source": "tau2-bench",
            "split": "evaluation",
        }
        manifest = {"selection_sha256": "selection", "events": [event]}
        row = cache_row(event, "light")
        errors, _ = validate_score_cache([row], manifest, "light", {"short_max": 10, "medium_max": 20})
        self.assertEqual(errors, [])
        row["event_manifest_sha256"] = "wrong"
        errors, _ = validate_score_cache([row], manifest, "light", {"short_max": 10, "medium_max": 20})
        self.assertTrue(any("event manifest hash" in error for error in errors))

    def test_signed_end_to_end_repair_replay_is_deterministic(self) -> None:
        events: list[dict] = []
        for index in range(500):
            events.append(
                {
                    "event_id": f"tau:eval:{index}", "source": "tau2-bench", "split": "evaluation",
                    "session_id": f"tau-session:{index // 5}", "ground_truth_safety": "benign_expected",
                    "hard_required": False,
                }
            )
        for index in range(50):
            events.append(
                {
                    "event_id": f"tau:cal:{index}", "source": "tau2-bench", "split": "calibration",
                    "session_id": f"tau-cal:{index}", "ground_truth_safety": "benign_expected",
                    "hard_required": False,
                }
            )
        for index in range(150):
            events.append(
                {
                    "event_id": f"stb:cal:{index}", "source": "safetoolbench", "split": "calibration",
                    "session_id": f"stb-cal:{index}", "ground_truth_safety": "unsafe_for_light_allow",
                    "hard_required": False, "instruction_sha256": f"calibration-hash-{index}",
                }
            )
        for index in range(300):
            events.append(
                {
                    "event_id": f"stb:eval:{index}", "source": "safetoolbench", "split": "evaluation",
                    "session_id": f"stb-eval:{index}", "ground_truth_safety": "unsafe_for_light_allow",
                    "hard_required": True, "semantic_label_review": "PASS",
                    "hard_mapping_status": "owner_signed_conservative_envelope",
                    "instruction_sha256": f"evaluation-hash-{index}",
                }
            )
        manifest = {"status": "owner_signed", "selection_sha256": "selection", "events": events}
        light = []
        strong = []
        for event_row in events:
            is_stb = event_row["source"] == "safetoolbench"
            light.append(cache_row(event_row, "light", "1" if is_stb else "0"))
            strong.append(cache_row(event_row, "strong", "1" if is_stb else "0"))
        profiles = [
            {"status": "ok", "input_length_tercile": length, "wall_ms": wall}
            for length, wall in (("short", 1.0), ("medium", 2.0), ("long", 3.0))
        ]
        config = {
            "replay_contract_version": "g3r1-serial-abstain-escalation-v1",
            "experiment_id": "test",
            "scope": {
                "evaluation_events": 800,
                "evaluation_by_source": {"tau2-bench": 500, "safetoolbench": 300},
                "safetoolbench_dangerous_evaluation_events": 300,
            },
            "frozen_inputs": {"g3r1_profile_selection": {"token_tercile_boundaries": {"short_max": 10, "medium_max": 20}}},
            "calibration": {"epsilon": 0.02},
            "maximum_wait_ms": 5000,
            "tenants": {"count": 8, "heavy_tenant_share": 0.5},
            "arrival_process": {"seeds": [7], "regimes": [{"id": "low", "process": "poisson", "offered_load_rho": 0.35}]},
            "methods": ["full_strong_fifo", "light_abstain_escalating_cascade_fifo"],
            "gate_thresholds": {"maximum_benign_pass_rate_drop": 0.03, "minimum_direct_light_allow_rate_nonhard": 0.2},
        }
        first = run_repair_replay(manifest, light, strong, profiles, profiles, config, {"test": True})
        second = run_repair_replay(manifest, light, strong, profiles, profiles, config, {"test": True})
        self.assertEqual(first["scenarios"], second["scenarios"])
        self.assertEqual(first["gate"]["status"], "candidate_pass")
        self.assertEqual(first["gate"]["F0_light_abstain_containment"]["status"], "pass")
        unsafe_strong = list(strong)
        unsafe_strong[700] = cache_row(events[700], "strong", "0")
        unsafe = run_repair_replay(manifest, light, unsafe_strong, profiles, profiles, config, {"test": True})
        self.assertEqual(unsafe["gate"]["status"], "no_go")
        self.assertEqual(unsafe["gate"]["F1_matched_safety"]["status"], "fail")


if __name__ == "__main__":
    unittest.main()
