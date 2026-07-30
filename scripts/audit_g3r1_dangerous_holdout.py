#!/usr/bin/env python3
"""Audit the G3-R1 materialized SafeToolBench dangerous-action environment."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.prepare_g3r1_dangerous_holdout import EXPECTED_CATEGORIES, canonical_sha256
from src.g3_replay import write_json


FORBIDDEN_HOLDOUT_FIELDS = {"instruction", "explanation", "used_api", "output"}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def load_ledger(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        event_id = str(row.get("event_id", "")).strip()
        if not event_id or event_id in indexed:
            raise ValueError(f"ledger contains a missing or duplicate event_id: {event_id!r}")
        indexed[event_id] = {str(key): str(value or "").strip() for key, value in row.items()}
    return indexed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("data/g3r1-event-selection.json"))
    parser.add_argument(
        "--ledger", type=Path, default=Path("docs/audits/g3r1-safetoolbench-heldout-review.csv")
    )
    parser.add_argument(
        "--materialization-summary", type=Path,
        default=Path("data/processed/g3r1-materialization-summary.json"),
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("docs/audits/g3r1-dangerous-holdout-audit.json"),
    )
    args = parser.parse_args()
    try:
        manifest = load_json(args.manifest)
        ledger = load_ledger(args.ledger)
        summary = load_json(args.materialization_summary)
        errors: list[str] = []
        events = manifest.get("events", [])
        heldout = [
            event for event in events
            if event.get("source") == "safetoolbench" and event.get("split") == "evaluation"
        ]
        calibration = [
            event for event in events
            if event.get("source") == "safetoolbench" and event.get("split") == "calibration"
        ]
        if len(events) != 1000:
            errors.append(f"expected 1,000 total events, found {len(events)}")
        if len(heldout) != 300:
            errors.append(f"expected 300 SafeToolBench dangerous evaluation rows, found {len(heldout)}")
        if len(calibration) != 150:
            errors.append(f"expected 150 SafeToolBench calibration rows, found {len(calibration)}")
        if canonical_sha256(events) != manifest.get("selection_sha256"):
            errors.append("immutable selection SHA does not verify")
        categories = Counter(str(event.get("risk_category")) for event in heldout)
        expected_categories = {category: 75 for category in EXPECTED_CATEGORIES}
        if dict(categories) != expected_categories:
            errors.append(f"risk-category quota mismatch: {dict(categories)}")
        calibration_hashes = {str(event.get("instruction_sha256", "")) for event in calibration}
        heldout_hashes = {str(event.get("instruction_sha256", "")) for event in heldout}
        if "" in calibration_hashes or len(calibration_hashes) != len(calibration):
            errors.append("calibration instruction hashes are missing or non-unique")
        if "" in heldout_hashes or len(heldout_hashes) != len(heldout):
            errors.append("heldout instruction hashes are missing or non-unique")
        if calibration_hashes & heldout_hashes:
            errors.append("calibration/heldout instruction overlap")
        for event in heldout:
            event_id = str(event.get("event_id", ""))
            if not event.get("hard_required"):
                errors.append(f"{event_id}: dangerous holdout is not protected by the conservative hard envelope")
            if set(event) & FORBIDDEN_HOLDOUT_FIELDS:
                errors.append(f"{event_id}: manifest stores forbidden raw risky source field(s)")
            row = ledger.get(event_id)
            if row is None:
                errors.append(f"{event_id}: missing ledger row")
                continue
            for key in ("instruction_sha256", "source_file", "source_row_index", "risk_category"):
                if str(row.get(key, "")) != str(event.get(key, "")):
                    errors.append(f"{event_id}: ledger {key} does not match manifest")
            if manifest.get("status") == "owner_signed":
                if event.get("semantic_label_review") != "PASS":
                    errors.append(f"{event_id}: signed manifest semantic review is not PASS")
                if event.get("hard_mapping_status") != "owner_signed_conservative_envelope":
                    errors.append(f"{event_id}: signed manifest hard envelope is not owner-signed")
                for key in ("semantic_label_review", "hard_capability_review"):
                    if row.get(key) != "PASS":
                        errors.append(f"{event_id}: signed ledger {key} is not PASS")
                if not row.get("reviewer") or not row.get("reviewed_at"):
                    errors.append(f"{event_id}: signed ledger lacks reviewer/timestamp")
        if set(ledger) != {str(event.get("event_id", "")) for event in heldout}:
            errors.append("ledger event IDs do not exactly match heldout manifest")
        if summary.get("manifest_sha256") != manifest.get("selection_sha256"):
            errors.append("materialization summary manifest SHA mismatch")
        if summary.get("total_materialized") != 1000 or summary.get("errors_by_source"):
            errors.append("materialization summary is incomplete or contains source errors")
        status = manifest.get("status")
        if status == "candidate_pending_owner_signoff":
            audit_status = "passed_with_owner_signoff_pending" if not errors else "failed"
        elif status == "owner_signed":
            audit_status = "passed" if not errors else "failed"
        else:
            errors.append(f"unexpected manifest status {status!r}")
            audit_status = "failed"
        artifact = {
            "schema_version": "0.1",
            "audit": "g3r1-dangerous-holdout",
            "status": audit_status,
            "manifest_status": status,
            "counts": {
                "total_events": len(events),
                "safetoolbench_calibration": len(calibration),
                "safetoolbench_dangerous_evaluation": len(heldout),
                "risk_categories": dict(categories),
                "calibration_evaluation_instruction_overlap": len(calibration_hashes & heldout_hashes),
            },
            "materialization": {
                "total_materialized": summary.get("total_materialized"),
                "errors_by_source": summary.get("errors_by_source"),
            },
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
