"""Unit tests for the dependency-free quota allocator used by G2 v3."""

from __future__ import annotations

import unittest
from collections import Counter

from scripts.stratify_and_audit_g2_prompts import (
    bounded_proportional_allocation,
    select_with_fixed_quotas,
)


def candidate(index: int, length: str, source: str, hard: bool = False) -> dict:
    return {
        "record": {
            "event_id": f"{source}-{length}-{hard}-{index}",
            "source": source,
            "hard_required": hard,
        },
        "input_length_tercile": length,
        "profiling_prompt_sha256": f"sha-{source}-{length}-{hard}-{index}",
    }


class SelectionQuotaTests(unittest.TestCase):
    def test_bounded_proportional_allocation_is_exact_and_capped(self) -> None:
        allocation = bounded_proportional_allocation(32, {"short": 80, "medium": 10, "long": 2})
        self.assertEqual(sum(allocation.values()), 32)
        self.assertLessEqual(allocation["short"], 80)
        self.assertLessEqual(allocation["medium"], 10)
        self.assertLessEqual(allocation["long"], 2)

    def test_fixed_quotas_prevent_single_stratum_dominance(self) -> None:
        candidates: list[dict] = []
        for length, total in (("short", 43), ("medium", 43), ("long", 42)):
            for index in range(40):
                candidates.append(candidate(index, length, "safetoolbench"))
                candidates.append(candidate(index, length, "tau2-bench", hard=True))
                candidates.append(candidate(index, length, "tau2-bench", hard=False))
        selected, audit = select_with_fixed_quotas(
            candidates,
            length_quotas={"short": 43, "medium": 43, "long": 42},
            safetoolbench_quota=32,
            tau_hard_minimum=32,
            seed=20260730,
        )
        self.assertEqual(len(selected), 128)
        self.assertEqual(
            Counter(item["input_length_tercile"] for item in selected),
            Counter({"short": 43, "medium": 43, "long": 42}),
        )
        self.assertEqual(
            sum(item["record"]["source"] == "safetoolbench" for item in selected), 32
        )
        self.assertGreaterEqual(audit["actual_tau_hard_count"], 32)


if __name__ == "__main__":
    unittest.main()
