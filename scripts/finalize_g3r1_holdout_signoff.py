#!/usr/bin/env python3
"""Create owner-signed G3-R1 copies after a row-level ledger review.

This command never approves rows on its own.  It only accepts a completed CSV
ledger in which every held-out SafeToolBench row is marked PASS for source
integrity, calibration disjointness, semantic label review, and hard-capability
review.  It writes new manifest/config copies rather than overwriting the
pending candidate artifacts.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.prepare_g3r1_dangerous_holdout import canonical_sha256


REQUIRED_PASS_COLUMNS = (
    "source_row_integrity",
    "calibration_disjointness",
    "semantic_label_review",
    "hard_capability_review",
)
ATTESTATION = "I_HAVE_REVIEWED_300_HELDOUT_ROWS"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def load_ledger(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    indexed: dict[str, dict[str, str]] = {}
    for line_number, row in enumerate(rows, start=2):
        event_id = str(row.get("event_id", "")).strip()
        if not event_id:
            raise ValueError(f"{path}:{line_number}: missing event_id")
        if event_id in indexed:
            raise ValueError(f"{path}:{line_number}: duplicate event_id {event_id}")
        indexed[event_id] = {str(key): str(value or "").strip() for key, value in row.items()}
    return indexed


def validate_review(manifest: dict[str, Any], ledger: dict[str, dict[str, str]]) -> list[str]:
    errors: list[str] = []
    heldout = [
        event
        for event in manifest.get("events", [])
        if event.get("source") == "safetoolbench" and event.get("split") == "evaluation"
    ]
    if len(heldout) != 300:
        errors.append(f"manifest has {len(heldout)} held-out SafeToolBench rows, expected 300")
    expected_ids = {str(event.get("event_id", "")) for event in heldout}
    if len(expected_ids) != len(heldout):
        errors.append("manifest has duplicate/missing held-out event IDs")
    if set(ledger) != expected_ids:
        errors.append(
            "ledger event IDs do not exactly match heldout manifest "
            f"(missing={len(expected_ids - set(ledger))}, extra={len(set(ledger) - expected_ids)})"
        )
    for event in heldout:
        event_id = str(event.get("event_id", ""))
        row = ledger.get(event_id)
        if row is None:
            continue
        for column in REQUIRED_PASS_COLUMNS:
            if row.get(column) != "PASS":
                errors.append(f"{event_id}: {column} is not PASS")
                break
        if not row.get("reviewer"):
            errors.append(f"{event_id}: reviewer is blank")
        if not row.get("reviewed_at"):
            errors.append(f"{event_id}: reviewed_at is blank")
        if str(row.get("instruction_sha256", "")) != str(event.get("instruction_sha256", "")):
            errors.append(f"{event_id}: instruction hash differs from manifest")
        if str(row.get("source_file", "")) != str(event.get("source_file", "")):
            errors.append(f"{event_id}: source file differs from manifest")
        if str(row.get("source_row_index", "")) != str(event.get("source_row_index", "")):
            errors.append(f"{event_id}: source row index differs from manifest")
    if canonical_sha256(manifest.get("events", [])) != manifest.get("selection_sha256"):
        errors.append("candidate manifest immutable selection hash does not verify")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("data/g3r1-event-selection.json"))
    parser.add_argument(
        "--ledger", type=Path, default=Path("docs/audits/g3r1-safetoolbench-heldout-review.csv")
    )
    parser.add_argument(
        "--config", type=Path,
        default=Path("experiments/configs/g3r1-serial-abstain-escalation.json"),
    )
    parser.add_argument(
        "--output-manifest", type=Path,
        default=Path("data/g3r1-event-selection.owner-signed.json"),
    )
    parser.add_argument(
        "--output-config", type=Path,
        default=Path("experiments/configs/g3r1-serial-abstain-escalation.owner-signed.json"),
    )
    parser.add_argument(
        "--attestation", required=True,
        help=f"Must exactly equal {ATTESTATION!r} after completing the ledger review.",
    )
    args = parser.parse_args()
    try:
        if args.attestation != ATTESTATION:
            raise ValueError("explicit row-level owner attestation was not supplied")
        manifest = load_json(args.manifest)
        config = load_json(args.config)
        ledger = load_ledger(args.ledger)
        errors = validate_review(manifest, ledger)
        if errors:
            raise ValueError("heldout review is incomplete: " + "; ".join(errors[:8]))
        signed_manifest = dict(manifest)
        signed_events: list[dict[str, Any]] = []
        for raw_event in manifest["events"]:
            event = dict(raw_event)
            if event.get("source") == "safetoolbench" and event.get("split") == "evaluation":
                event["semantic_label_review"] = "PASS"
                event["hard_mapping_status"] = "owner_signed_conservative_envelope"
            signed_events.append(event)
        signed_manifest["events"] = signed_events
        signed_manifest["status"] = "owner_signed"
        reviewers = sorted({row["reviewer"] for row in ledger.values()})
        reviewed_at = sorted({row["reviewed_at"] for row in ledger.values()})
        signed_manifest["owner_signoff"] = {
            "attestation": ATTESTATION,
            "reviewers": reviewers,
            "reviewed_at": reviewed_at,
            "ledger": str(args.ledger).replace("\\", "/"),
            "reviewed_rows": len(ledger),
        }
        # Review fields are intentionally excluded from selection_sha256.
        if canonical_sha256(signed_events) != manifest["selection_sha256"]:
            raise AssertionError("signoff altered immutable selection/routing inputs")
        signed_config = dict(config)
        signed_config["status"] = "owner_signed_pending_service_profile"
        signed_config["frozen_inputs"] = dict(config["frozen_inputs"])
        signed_config["frozen_inputs"]["event_manifest"] = dict(
            config["frozen_inputs"]["event_manifest"]
        )
        signed_config["frozen_inputs"]["event_manifest"]["path"] = str(
            args.output_manifest
        ).replace("\\", "/")
        signed_config["frozen_inputs"]["event_manifest"]["selection_sha256"] = signed_manifest[
            "selection_sha256"
        ]
        signed_config["owner_signoff"] = signed_manifest["owner_signoff"]
        for path, value in ((args.output_manifest, signed_manifest), (args.output_config, signed_config)):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote owner-signed manifest: {args.output_manifest}")
    print(f"Wrote owner-signed config: {args.output_config}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
