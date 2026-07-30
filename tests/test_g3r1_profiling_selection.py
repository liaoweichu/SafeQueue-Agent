"""Quota checks for the dependency-free parts of the G3-R1 profile selector."""

from __future__ import annotations

import unittest
from collections import Counter

from scripts.build_g3r1_profiling_selection import select_with_quotas


def candidate(event_id: str, source: str, length: str, hard: bool = False) -> dict:
    return {
        "record": {"event_id": event_id, "source": source, "hard_required": hard},
        "input_length_tercile": length,
    }


class G3R1ProfileSelectionTests(unittest.TestCase):
    def test_fixed_source_hard_and_length_quotas_are_all_honored(self) -> None:
        candidates: list[dict] = []
        for length in ("short", "medium", "long"):
            for index in range(2):
                candidates.append(candidate(f"stb:{length}:{index}", "safetoolbench", length, True))
            for index in range(2):
                candidates.append(candidate(f"tau-hard:{length}:{index}", "tau2-bench", length, True))
            for index in range(2):
                candidates.append(candidate(f"tau-soft:{length}:{index}", "tau2-bench", length, False))
        selected, audit = select_with_quotas(
            candidates,
            length_quotas={"short": 3, "medium": 3, "long": 3},
            tau_quota=6,
            safetoolbench_quota=3,
            tau_hard_minimum=3,
            seed=7,
        )
        self.assertEqual(len(selected), 9)
        self.assertEqual(Counter(item["record"]["source"] for item in selected), {"tau2-bench": 6, "safetoolbench": 3})
        self.assertEqual(Counter(item["input_length_tercile"] for item in selected), {"short": 3, "medium": 3, "long": 3})
        self.assertGreaterEqual(audit["actual_tau_hard_count"], 3)


if __name__ == "__main__":
    unittest.main()
