#!/usr/bin/env python3
"""Create a source-verifiable, owner-signoff ledger for G2 SafeToolBench rows.

The ledger deliberately stores source locators and hashes rather than the risky
instructions themselves.  A reviewer can inspect the pinned archive at the
recorded row, while the project does not duplicate raw benchmark content.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path


SAFE_TOOL_COMMIT = "ffdef6e782b0b05f579316003f3b084b549f1366"
SAFE_TOOL_ARCHIVE_SHA256 = (
    "0F0BA04880DA6C5DE3C36FE7590D5C17976C54E984E020A2A9C15FC1FB696444"
)
EXPECTED_MANIFEST_SHA256 = (
    "8afed1ffe3dcd20e930bd914d74329352308c426aacb99d0ef50ba0879cad3fb"
)
EXPECTED_CATEGORIES = {
    "Bias & Offensiveness",
    "Physical Injury",
    "Privacy Leak",
    "Property Damage",
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def normalized_instruction_sha256(instruction: str) -> str:
    normalized = " ".join(instruction.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def source_tool_names(row: dict) -> list[str]:
    names: list[str] = []
    for call in row["output"]["used_api"]:
        names.extend(name for name in call if name != "use_times")
    return list(dict.fromkeys(names))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/g2-event-selection.json"),
    )
    parser.add_argument(
        "--archive",
        type=Path,
        default=Path(
            "data/raw/"
            "safetoolbench-ffdef6e782b0b05f579316003f3b084b549f1366.zip"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/audits/g2-safetoolbench-label-review.csv"),
    )
    args = parser.parse_args()

    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    if payload["selection_sha256"] != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("Unexpected G2 event manifest SHA-256")
    if file_sha256(args.archive) != SAFE_TOOL_ARCHIVE_SHA256:
        raise RuntimeError("Unexpected SafeToolBench archive SHA-256")

    events = sorted(
        (event for event in payload["events"] if event["source"] == "safetoolbench"),
        key=lambda event: event["event_id"],
    )
    if len(events) != 150:
        raise RuntimeError(f"Expected 150 SafeToolBench events, found {len(events)}")
    if len({event["instruction_sha256"] for event in events}) != 150:
        raise RuntimeError("Selected SafeToolBench instructions are not unique")

    cached_rows: dict[str, list[dict]] = {}
    category_counts: Counter[str] = Counter()
    output_rows: list[dict[str, str]] = []
    prefix = f"SafeToolBench-{SAFE_TOOL_COMMIT}/"
    with zipfile.ZipFile(args.archive) as archive:
        for event in events:
            archive_name = prefix + event["source_file"]
            if archive_name not in cached_rows:
                cached_rows[archive_name] = json.loads(
                    archive.read(archive_name).decode("utf-8")
                )
            row = cached_rows[archive_name][event["source_row_index"]]
            row_hash = normalized_instruction_sha256(row["instruction"])
            row_tools = source_tool_names(row)
            if not row["instruction"].strip() or not row["output"]["used_api"]:
                raise RuntimeError(f"Empty instruction or API list for {event['event_id']}")
            if row_hash != event["instruction_sha256"]:
                raise RuntimeError(f"Instruction hash mismatch for {event['event_id']}")
            if int(row["quality_score"]) != event["quality_score"] or event["quality_score"] < 7:
                raise RuntimeError(f"Quality-score mismatch for {event['event_id']}")
            if row["Risk category"] != event["risk_category"]:
                raise RuntimeError(f"Risk-category mismatch for {event['event_id']}")
            if row_tools != event["tool_names"]:
                raise RuntimeError(f"Tool-name mismatch for {event['event_id']}")
            if row["Risk category"] not in EXPECTED_CATEGORIES:
                raise RuntimeError(f"Unexpected risk category for {event['event_id']}")

            category_counts[row["Risk category"]] += 1
            output_rows.append(
                {
                    "event_id": event["event_id"],
                    "source_file": event["source_file"],
                    "source_row_index": str(event["source_row_index"]),
                    "instruction_sha256": event["instruction_sha256"],
                    "risk_category": event["risk_category"],
                    "quality_score": str(event["quality_score"]),
                    "tool_names": " | ".join(event["tool_names"]),
                    "source_row_integrity": "PASS",
                    "semantic_label_review": "PENDING_OWNER_SIGNOFF",
                    "reviewer": "",
                    "reviewed_at": "",
                    "notes": "",
                }
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(output_rows[0])
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"manifest_sha256={payload['selection_sha256']}")
    print(f"archive_sha256={SAFE_TOOL_ARCHIVE_SHA256}")
    print(f"selected_rows={len(output_rows)}")
    print(f"category_counts={json.dumps(dict(sorted(category_counts.items())), ensure_ascii=False)}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
