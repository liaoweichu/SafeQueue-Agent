"""Materializer for SafeToolBench (calibration-only).

Reads the frozen SafeToolBench archive and extracts user instructions and
tool plans for each calibration event in the G2 event manifest.

SafeToolBench is calibration-only: its events are used to select a risk
threshold for the light verifier, not for evaluation.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Optional

from src.materializers.base import MaterializedRecord, PromptRenderer

SAFE_TOOL_ARCHIVE_PATH = Path(
    "data/raw/safetoolbench-ffdef6e782b0b05f579316003f3b084b549f1366.zip"
)
SAFE_TOOL_COMMIT = "ffdef6e782b0b05f579316003f3b084b549f1366"
SAFE_TOOL_SOURCE = "safetoolbench"


def _normalized_instruction_sha256(instruction: str) -> str:
    normalized = " ".join(instruction.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class SafeToolBenchMaterializer:
    """Materialize verifier inputs from SafeToolBench risky tool plans.

    Each calibration event contains a user instruction and a tool plan
    (list of API calls).  The materializer reads the full instruction and
    the proposed tool calls from the frozen archive.

    Fields rendered:
      state_summary  — "SafeToolBench prospective tool plan (no pre-execution state)"
      user_intent    — user instruction text
      tool_name      — comma-separated list of tool names in the plan
      tool_arguments — JSON dump of the tool plan's API calls
    """

    def __init__(
        self,
        archive_path: Optional[Path] = None,
        renderer: Optional[PromptRenderer] = None,
    ) -> None:
        self.archive_path = archive_path or SAFE_TOOL_ARCHIVE_PATH
        self.renderer = renderer or PromptRenderer()
        self._file_cache: dict[str, list[dict]] = {}

    def _load_source_rows(self, source_file: str) -> list[dict]:
        """Load and cache a SafeToolBench JSON data file."""
        if source_file not in self._file_cache:
            if not self.archive_path.exists():
                raise FileNotFoundError(
                    f"SafeToolBench archive not found at {self.archive_path}. "
                    f"Download commit {SAFE_TOOL_COMMIT} from "
                    "https://github.com/BITHLP/SafeToolBench and save to data/raw/."
                )
            archive_name = f"SafeToolBench-{SAFE_TOOL_COMMIT}/{source_file}"
            with zipfile.ZipFile(self.archive_path) as archive:
                self._file_cache[source_file] = json.loads(
                    archive.read(archive_name).decode("utf-8")
                )
        return self._file_cache[source_file]

    def materialize(self, event: dict) -> MaterializedRecord:
        """Produce a rendered verifier input for one SafeToolBench event.

        Args:
            event: A single event dict from the G2 event manifest.

        Returns:
            MaterializedRecord with rendered prompt.
        """
        source_file = event["source_file"]
        row_index = event["source_row_index"]
        rows = self._load_source_rows(source_file)
        row = rows[row_index]

        # Verify instruction hash integrity
        row_hash = _normalized_instruction_sha256(row["instruction"])
        if row_hash != event["instruction_sha256"]:
            raise ValueError(
                f"Instruction hash mismatch for {event['event_id']}: "
                f"expected {event['instruction_sha256']}, got {row_hash}"
            )

        user_intent = row["instruction"]
        tool_plan = row["output"]["used_api"]

        # Extract tool names
        tool_names: list[str] = []
        for call in tool_plan:
            tool_names.extend(name for name in call if name != "use_times")
        unique_names = list(dict.fromkeys(tool_names))

        tool_name = ", ".join(unique_names)
        tool_arguments = json.dumps(tool_plan, ensure_ascii=False)

        # SafeToolBench has no pre-execution state; it provides prospective plans only.
        state_summary = (
            "SafeToolBench prospective tool plan — no pre-execution environment "
            "state is available. Evaluate based on the instruction and proposed "
            "tool calls alone."
        )

        # SafeToolBench events are calibration only, hard_required is always None
        hard_required = event.get("hard_required", False)
        if hard_required is None:
            hard_required = False

        return self.renderer.render(
            event_id=event["event_id"],
            source=SAFE_TOOL_SOURCE,
            source_version=SAFE_TOOL_COMMIT,
            state_summary=state_summary,
            user_intent=user_intent,
            tool_name=tool_name,
            tool_arguments=tool_arguments,
            hard_required=hard_required,
        )

    def materialize_all(
        self,
        events: list[dict],
    ) -> tuple[list[MaterializedRecord], list[str]]:
        """Materialize a batch of SafeToolBench events.

        Returns:
            Tuple of (successful records, list of error messages).
        """
        records: list[MaterializedRecord] = []
        errors: list[str] = []
        for event in events:
            if event.get("source") != SAFE_TOOL_SOURCE:
                continue
            try:
                records.append(self.materialize(event))
            except Exception as exc:
                errors.append(f"event_id={event['event_id']}: {exc}")
        return records, errors
