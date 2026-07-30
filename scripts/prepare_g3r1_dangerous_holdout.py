#!/usr/bin/env python3
"""Build a disjoint, materializable SafeToolBench dangerous-action holdout.

G2 used 150 SafeToolBench rows only for calibration.  This tool selects a
separate 300-row evaluation slice from the remaining quality-filtered,
deduplicated source rows.  It stores source locators and hashes, never copies
the risky instructions into the manifest or review ledger.

The new slice is deliberately conservative: until an owner signs its semantic
and capability ledger, each selected plan is marked hard-required and cannot
promote a replay result.  ``hard_required`` is an evaluation guard derived
from the observable source/tool-plan envelope, not from the benchmark outcome.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.audit_g2_sources import (
    SAFE_TOOL_ARCHIVE_SHA256,
    SAFE_TOOL_COMMIT,
    audit_safetoolbench,
    file_sha256,
    stable_key,
)


SELECTION_SEED = "safequeue-g3r1-20260730"
TARGET_PER_CATEGORY = 75
EXPECTED_CATEGORIES = (
    "Bias & Offensiveness",
    "Physical Injury",
    "Privacy Leak",
    "Property Damage",
)


def canonical_sha256(events: Iterable[dict[str, Any]]) -> str:
    """Hash immutable selection/routing inputs, not mutable review attestations.

    The ledger's PASS/PENDING state must be auditable, but approving a review
    must not silently invalidate already materialized prompts or cause a cache
    provenance hash to drift.  Any change to source identity, input routing,
    or evaluation labels is included here and therefore requires a new hash.
    """
    immutable = [
        {
            key: event.get(key)
            for key in (
                "source",
                "source_version",
                "domain",
                "session_id",
                "event_id",
                "split",
                "event_kind",
                "source_file",
                "source_row_index",
                "instruction_sha256",
                "risk_category",
                "quality_score",
                "tool_names",
                "tool_name",
                "hard_required",
                "hard_decision_basis",
                "ground_truth_safety",
                "calibration_role",
            )
            if key in event
        }
        for event in events
    ]
    payload = json.dumps(
        sorted(immutable, key=lambda event: str(event["event_id"])),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def choose_balanced_holdout(
    rows_by_stratum: dict[str, list[dict[str, Any]]],
    calibration_instruction_hashes: set[str],
    target_per_category: int,
    seed: str,
) -> tuple[list[tuple[str, dict[str, Any]]], dict[str, dict[str, int]]]:
    """Select unique held-out rows, exactly balanced across risk categories."""
    candidates_by_category: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for stratum, rows in rows_by_stratum.items():
        for row in rows:
            if row["instruction_sha256"] in calibration_instruction_hashes:
                continue
            candidates_by_category[str(row["risk_category"])].append((stratum, row))
    unexpected_categories = sorted(set(candidates_by_category) - set(EXPECTED_CATEGORIES))
    if unexpected_categories:
        raise ValueError(f"unexpected SafeToolBench categories: {unexpected_categories}")
    selected: list[tuple[str, dict[str, Any]]] = []
    audit: dict[str, dict[str, int]] = {}
    for category in EXPECTED_CATEGORIES:
        candidates = sorted(
            candidates_by_category[category],
            key=lambda item: stable_key(
                seed,
                "g3r1-safetoolbench-holdout",
                category,
                item[0],
                item[1]["source_file"],
                item[1]["row_index"],
                item[1]["instruction_sha256"],
            ),
        )
        if len(candidates) < target_per_category:
            raise ValueError(
                f"{category}: only {len(candidates)} disjoint candidates, need {target_per_category}"
            )
        chosen = candidates[:target_per_category]
        selected.extend(chosen)
        audit[category] = {
            "eligible_disjoint_candidates": len(candidates),
            "selected": len(chosen),
        }
    hashes = [row["instruction_sha256"] for _, row in selected]
    if len(hashes) != len(set(hashes)):
        raise AssertionError("heldout selection contains duplicate normalized instructions")
    if set(hashes) & calibration_instruction_hashes:
        raise AssertionError("heldout selection overlaps the calibration split")
    return selected, audit


def make_heldout_event(stratum: str, row: dict[str, Any]) -> dict[str, Any]:
    event_id = f"safetoolbench:{stratum}:{row['row_index']}:{row['instruction_sha256'][:12]}"
    return {
        "source": "safetoolbench",
        "source_version": SAFE_TOOL_COMMIT,
        "domain": stratum,
        "session_id": event_id,
        "event_id": event_id,
        "split": "evaluation",
        "event_kind": "prospective_risky_tool_plan",
        "source_file": row["source_file"],
        "source_row_index": row["row_index"],
        "instruction_sha256": row["instruction_sha256"],
        "risk_category": row["risk_category"],
        "quality_score": row["quality_score"],
        "tool_names": row["tool_names"],
        # Conservative envelope: all holdout plans first reach Strong until a
        # per-capability registry is signed.  It does not inspect this row's
        # risk label or any model outcome.
        "hard_required": True,
        "hard_decision_basis": "conservative_safetoolbench_observable_tool_plan_envelope",
        "hard_mapping_status": "pending_owner_capability_review",
        "ground_truth_safety": "unsafe_for_light_allow",
        "semantic_label_review": "PENDING_OWNER_SIGNOFF",
        "calibration_role": None,
    }


def build_ledger_rows(events: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for event in sorted(events, key=lambda item: str(item["event_id"])):
        rows.append(
            {
                "event_id": str(event["event_id"]),
                "source_file": str(event["source_file"]),
                "source_row_index": str(event["source_row_index"]),
                "instruction_sha256": str(event["instruction_sha256"]),
                "risk_category": str(event["risk_category"]),
                "quality_score": str(event["quality_score"]),
                "tool_names": " | ".join(event["tool_names"]),
                "source_row_integrity": "PASS",
                "calibration_disjointness": "PASS",
                "semantic_label_review": "PENDING_OWNER_SIGNOFF",
                "hard_capability_review": "PENDING_OWNER_SIGNOFF",
                "reviewer": "",
                "reviewed_at": "",
                "notes": "",
            }
        )
    return rows


def ledger_has_review_progress(path: Path) -> bool:
    """Do not silently erase a partially completed owner review ledger."""
    if not path.exists():
        return False
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if any(str(row.get(field, "")).strip() for field in ("reviewer", "reviewed_at", "notes")):
                return True
            if row.get("semantic_label_review") == "PASS" or row.get("hard_capability_review") == "PASS":
                return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-manifest", type=Path, default=Path("data/g2-event-selection.json"))
    parser.add_argument(
        "--archive",
        type=Path,
        default=Path("data/raw/safetoolbench-ffdef6e782b0b05f579316003f3b084b549f1366.zip"),
    )
    parser.add_argument("--output-manifest", type=Path, default=Path("data/g3r1-event-selection.json"))
    parser.add_argument(
        "--output-ledger",
        type=Path,
        default=Path("docs/audits/g3r1-safetoolbench-heldout-review.csv"),
    )
    parser.add_argument("--target-per-category", type=int, default=TARGET_PER_CATEGORY)
    parser.add_argument("--seed", default=SELECTION_SEED)
    parser.add_argument(
        "--overwrite-review-ledger",
        action="store_true",
        help="Allow replacing an existing ledger that contains reviewer progress.",
    )
    args = parser.parse_args()

    if args.target_per_category <= 0:
        raise ValueError("--target-per-category must be positive")
    base = json.loads(args.base_manifest.read_text(encoding="utf-8"))
    base_events = list(base.get("events", []))
    calibration_events = [
        event
        for event in base_events
        if event.get("source") == "safetoolbench" and event.get("split") == "calibration"
    ]
    if len(calibration_events) != 150:
        raise ValueError(f"base manifest must have 150 SafeToolBench calibration rows, found {len(calibration_events)}")
    calibration_hashes = {str(event["instruction_sha256"]) for event in calibration_events}
    if len(calibration_hashes) != len(calibration_events):
        raise ValueError("base SafeToolBench calibration rows are not instruction-unique")
    archive_hash = file_sha256(args.archive)
    if archive_hash != SAFE_TOOL_ARCHIVE_SHA256:
        raise ValueError(f"unexpected SafeToolBench archive SHA-256: {archive_hash}")
    with zipfile.ZipFile(args.archive) as archive:
        source_audit, rows_by_stratum = audit_safetoolbench(archive)
    selected, category_audit = choose_balanced_holdout(
        rows_by_stratum, calibration_hashes, args.target_per_category, args.seed
    )
    heldout_events = [make_heldout_event(stratum, row) for stratum, row in selected]
    retained_events = [
        dict(event)
        for event in base_events
        if event.get("source") in {"tau2-bench", "safetoolbench"}
    ]
    if len(retained_events) != 700:
        raise ValueError(f"expected 700 retained tau2/SafeToolBench events, found {len(retained_events)}")
    events = retained_events + heldout_events
    counts = Counter((event.get("source"), event.get("split")) for event in events)
    evaluation_events = [event for event in events if event.get("split") == "evaluation"]
    dangerous_eval = [
        event
        for event in evaluation_events
        if event.get("ground_truth_safety") == "unsafe_for_light_allow"
    ]
    payload = {
        "schema_version": "0.1",
        "status": "candidate_pending_owner_signoff",
        "experiment_id": "g3r1_light_abstain_escalation_with_materialized_dangerous_holdout",
        "selection_seed": args.seed,
        "base_g2_event_manifest_sha256": base.get("selection_sha256"),
        "selection_sha256": canonical_sha256(events),
        "source_audit": {
            "safetoolbench_commit": SAFE_TOOL_COMMIT,
            "safetoolbench_archive_sha256": archive_hash,
            "base_eligible_unique_rows": source_audit["eligible_unique_rows"],
            "calibration_instruction_count": len(calibration_hashes),
            "heldout_instruction_count": len(heldout_events),
            "heldout_category_audit": category_audit,
            "heldout_stratum_counts": dict(
                sorted(Counter(event["domain"] for event in heldout_events).items())
            ),
        },
        "eligibility": {
            "total_events": len(events),
            "calibration_events": sum(1 for event in events if event.get("split") == "calibration"),
            "evaluation_events": len(evaluation_events),
            "tau2_benign_evaluation_events": counts[("tau2-bench", "evaluation")],
            "safetoolbench_dangerous_evaluation_events": len(dangerous_eval),
            "safetoolbench_holdout_hard_required_events": sum(
                bool(event.get("hard_required")) for event in dangerous_eval
            ),
            "calibration_evaluation_instruction_overlap": 0,
            "semantic_review_required": True,
            "capability_review_required": True,
        },
        "events": events,
    }
    if payload["eligibility"]["total_events"] != 1000:
        raise AssertionError("G3-R1 manifest must have exactly 1,000 events")
    if payload["eligibility"]["evaluation_events"] != 800:
        raise AssertionError("G3-R1 manifest must have exactly 800 evaluation events")
    if payload["eligibility"]["safetoolbench_dangerous_evaluation_events"] != 4 * args.target_per_category:
        raise AssertionError("G3-R1 dangerous holdout count does not match category target")
    args.output_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.output_manifest.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if ledger_has_review_progress(args.output_ledger) and not args.overwrite_review_ledger:
        raise ValueError(
            "refusing to overwrite a ledger with review progress; use a new --output-ledger "
            "or explicitly pass --overwrite-review-ledger"
        )
    ledger_rows = build_ledger_rows(heldout_events)
    args.output_ledger.parent.mkdir(parents=True, exist_ok=True)
    with args.output_ledger.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ledger_rows[0]))
        writer.writeheader()
        writer.writerows(ledger_rows)
    print(f"selection_sha256={payload['selection_sha256']}")
    print(f"events={payload['eligibility']['total_events']}; dangerous_eval={len(dangerous_eval)}")
    print(f"manifest={args.output_manifest}")
    print(f"ledger={args.output_ledger}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
