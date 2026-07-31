#!/usr/bin/env python3
"""Perform an auditable delegated review of the G3-R1 dangerous holdout.

The G3-R1 ledger deliberately starts in ``PENDING_OWNER_SIGNOFF``.  This
tool checks every selected SafeToolBench source row against the immutable
candidate manifest before it changes that state.  A semantic PASS means the
row is conservatively unsafe for a Light-only allow decision: its released
risk category, non-empty instruction, and prospective API plan are present
and it remains inside the Strong-only envelope.  It does not claim that the
source category is a fine-grained real-world harm taxonomy.

The command is intentionally two-phase.  Without ``--apply`` it only audits;
with ``--apply`` it accepts only an all-pending ledger and records the named
delegated reviewer, timestamp, and a no-raw-prompt review note for all 300
rows.  The separate finalization script still creates the owner-signed
manifest/config copies only after this ledger passes its independent checks.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.audit_g2_sources import SAFE_TOOL_ARCHIVE_SHA256, SAFE_TOOL_COMMIT, file_sha256
from scripts.prepare_g3r1_dangerous_holdout import EXPECTED_CATEGORIES, canonical_sha256


EXPECTED_CATEGORY_BY_PREFIX = {
    "BO": "Bias & Offensiveness",
    "PD": "Property Damage",
    "PI": "Physical Injury",
    "PL": "Privacy Leak",
}
REVIEW_NOTE = (
    "Delegated source-row review: released category, normalized instruction hash, "
    "quality floor, prospective API plan, calibration disjointness, and "
    "conservative Strong-only envelope verified."
)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def load_ledger(path: Path) -> tuple[list[str], dict[str, dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    indexed: dict[str, dict[str, str]] = {}
    for line_number, raw in enumerate(rows, start=2):
        row = {str(key): str(value or "").strip() for key, value in raw.items()}
        event_id = row.get("event_id", "")
        if not event_id:
            raise ValueError(f"{path}:{line_number}: missing event_id")
        if event_id in indexed:
            raise ValueError(f"{path}:{line_number}: duplicate event_id {event_id}")
        indexed[event_id] = row
    return fieldnames, indexed


def normalized_instruction_sha256(instruction: str) -> str:
    normalized = " ".join(instruction.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def source_prefix(source_file: str) -> str:
    filename = Path(source_file).name
    if not filename.startswith("query_") or len(filename) < len("query_BO_"):
        raise ValueError(f"unexpected SafeToolBench source filename: {source_file}")
    return filename[len("query_") : len("query_") + 2]


def source_tool_names(row: dict[str, Any]) -> list[str]:
    plan = row.get("output", {}).get("used_api")
    if not isinstance(plan, list) or not plan:
        return []
    names: list[str] = []
    for call in plan:
        if not isinstance(call, dict):
            return []
        names.extend(str(name) for name in call if name != "use_times")
    return list(dict.fromkeys(names))


def source_path_in_archive(source_file: str) -> str:
    return f"SafeToolBench-{SAFE_TOOL_COMMIT}/{source_file}"


def review(
    manifest: dict[str, Any],
    ledger: dict[str, dict[str, str]],
    archive_path: Path,
) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    category_counts: Counter[str] = Counter()
    events = [
        event
        for event in manifest.get("events", [])
        if event.get("source") == "safetoolbench" and event.get("split") == "evaluation"
    ]
    if len(events) != 300:
        errors.append(f"expected 300 SafeToolBench evaluation rows, found {len(events)}")
    expected_ids = {str(event.get("event_id", "")) for event in events}
    if set(ledger) != expected_ids:
        errors.append(
            "ledger IDs do not exactly match heldout events "
            f"(missing={len(expected_ids - set(ledger))}, extra={len(set(ledger) - expected_ids)})"
        )
    if canonical_sha256(manifest.get("events", [])) != manifest.get("selection_sha256"):
        errors.append("candidate manifest immutable selection hash does not verify")
    if file_sha256(archive_path) != SAFE_TOOL_ARCHIVE_SHA256:
        errors.append("SafeToolBench archive SHA-256 does not match the frozen source")
        return errors, dict(category_counts)

    calibration_hashes = {
        str(event.get("instruction_sha256", ""))
        for event in manifest.get("events", [])
        if event.get("source") == "safetoolbench" and event.get("split") == "calibration"
    }
    heldout_hashes = {str(event.get("instruction_sha256", "")) for event in events}
    if len(calibration_hashes) != 150 or len(heldout_hashes) != len(events):
        errors.append("SafeToolBench calibration or holdout instruction identities are incomplete")
    if calibration_hashes & heldout_hashes:
        errors.append("SafeToolBench calibration and evaluation instructions overlap")

    file_cache: dict[str, list[dict[str, Any]]] = {}
    with zipfile.ZipFile(archive_path) as archive:
        for event in events:
            event_id = str(event.get("event_id", ""))
            row = ledger.get(event_id)
            if row is None:
                continue
            source_file = str(event.get("source_file", ""))
            try:
                if source_file not in file_cache:
                    loaded = json.loads(archive.read(source_path_in_archive(source_file)).decode("utf-8"))
                    if not isinstance(loaded, list):
                        raise ValueError("source data is not a JSON list")
                    file_cache[source_file] = loaded
                row_index = int(event.get("source_row_index"))
                source_row = file_cache[source_file][row_index]
            except Exception as exc:
                errors.append(f"{event_id}: cannot resolve frozen source row ({exc})")
                continue

            prefix = source_prefix(source_file)
            expected_category = EXPECTED_CATEGORY_BY_PREFIX.get(prefix)
            actual_category = str(source_row.get("Risk category", ""))
            actual_hash = normalized_instruction_sha256(str(source_row.get("instruction", "")))
            actual_quality = int(source_row.get("quality_score", 0))
            actual_tools = source_tool_names(source_row)
            expected_tools = [str(name) for name in event.get("tool_names", [])]
            checks = {
                "event_source": event.get("event_kind") == "prospective_risky_tool_plan",
                "source_locator": row.get("source_file") == source_file
                and row.get("source_row_index") == str(row_index),
                "instruction_hash": actual_hash == str(event.get("instruction_sha256", ""))
                and row.get("instruction_sha256") == actual_hash,
                "risk_category": actual_category == str(event.get("risk_category", ""))
                and actual_category == expected_category
                and actual_category in EXPECTED_CATEGORIES,
                "quality": actual_quality >= 7 and str(actual_quality) == str(event.get("quality_score", "")),
                "action_plan": bool(str(source_row.get("instruction", "")).strip())
                and bool(actual_tools)
                and actual_tools == expected_tools,
                "conservative_semantics": event.get("ground_truth_safety") == "unsafe_for_light_allow",
                "conservative_capability": event.get("hard_required") is True
                and event.get("hard_decision_basis")
                == "conservative_safetoolbench_observable_tool_plan_envelope",
                "prior_ledger_checks": row.get("source_row_integrity") == "PASS"
                and row.get("calibration_disjointness") == "PASS",
            }
            failed = [name for name, passed in checks.items() if not passed]
            if failed:
                errors.append(f"{event_id}: failed " + ", ".join(failed))
            category_counts[actual_category] += 1

    expected_counts = {category: 75 for category in EXPECTED_CATEGORIES}
    if dict(category_counts) != expected_counts:
        errors.append(f"risk-category counts differ from the fixed quota: {dict(category_counts)}")
    return errors, dict(category_counts)


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ledger_review_state(ledger: dict[str, dict[str, str]]) -> str:
    """Classify the mutable review columns without conflating audit and apply."""
    complete = all(
        row.get("semantic_label_review") == "PASS"
        and row.get("hard_capability_review") == "PASS"
        and bool(row.get("reviewer"))
        and bool(row.get("reviewed_at"))
        for row in ledger.values()
    )
    if complete:
        return "complete"
    pending = all(
        row.get("semantic_label_review") == "PENDING_OWNER_SIGNOFF"
        and row.get("hard_capability_review") == "PENDING_OWNER_SIGNOFF"
        and not row.get("reviewer")
        and not row.get("reviewed_at")
        for row in ledger.values()
    )
    return "pending" if pending else "mixed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("data/g3r1-event-selection.json"))
    parser.add_argument(
        "--ledger", type=Path, default=Path("docs/audits/g3r1-safetoolbench-heldout-review.csv")
    )
    parser.add_argument(
        "--archive",
        type=Path,
        default=Path("data/raw/safetoolbench-ffdef6e782b0b05f579316003f3b084b549f1366.zip"),
    )
    parser.add_argument(
        "--audit-output", type=Path, default=Path("docs/audits/g3r1-owner-review-audit.json")
    )
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--reviewed-at")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    try:
        manifest = load_json(args.manifest)
        fieldnames, ledger = load_ledger(args.ledger)
        errors, category_counts = review(manifest, ledger, args.archive)
        reviewed_at = args.reviewed_at or datetime.now().astimezone().isoformat(timespec="seconds")
        state_before = ledger_review_state(ledger)
        applied_in_this_run = False
        if args.apply and not errors:
            if state_before != "pending":
                errors.append(
                    "refusing to overwrite existing review progress "
                    f"(ledger state is {state_before})"
                )
            else:
                for row in ledger.values():
                    row["semantic_label_review"] = "PASS"
                    row["hard_capability_review"] = "PASS"
                    row["reviewer"] = args.reviewer
                    row["reviewed_at"] = reviewed_at
                    row["notes"] = REVIEW_NOTE
                with args.ledger.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(ledger[event_id] for event_id in sorted(ledger))
                applied_in_this_run = True
        status = "passed" if not errors else "failed"
        state_after = ledger_review_state(ledger)
        audit = {
            "schema_version": "0.1",
            "audit": "g3r1-delegated-heldout-owner-review",
            "status": status,
            "ledger_review_state": state_after,
            "applied": state_after == "complete",
            "applied_in_this_run": applied_in_this_run,
            "reviewer": args.reviewer,
            "reviewed_at": reviewed_at,
            "reviewed_rows": len(ledger),
            "manifest_selection_sha256": manifest.get("selection_sha256"),
            "safetoolbench_archive_sha256": SAFE_TOOL_ARCHIVE_SHA256,
            "category_counts": category_counts,
            "semantic_decision": "all rows are unsafe_for_light_allow under the released source-category-plus-prospective-plan evidence; no fine-grained harm claim is made",
            "hard_capability_decision": "all rows retain hard_required=true and the conservative Strong-only observable-tool-plan envelope",
            "errors": errors,
        }
        write_json(args.audit_output, audit)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(audit, ensure_ascii=False))
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
