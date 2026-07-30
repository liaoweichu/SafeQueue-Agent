"""Materializer for tau2-bench Retail domain (v1.0.1).

Reads the frozen tau2-bench archive and extracts pre-action state summaries,
user intents, and gold action arguments for each event in the G2 event manifest.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Optional

from src.materializers.base import MaterializedRecord, PromptRenderer

TAU_ARCHIVE_PATH = Path("data/raw/tau2-bench-v1.0.1.zip")
TAU_TASKS_PATH = "tau2-bench-1.0.1/data/tau2/domains/retail/tasks.json"
TAU_SOURCE = "tau2-bench"
TAU_VERSION = "v1.0.1"


class TauBenchMaterializer:
    """Materialize verifier inputs from the tau2-bench Retail gold-action trace.

    Each event in the manifest corresponds to one gold action from a task
    session.  The materializer reads the task description and the specific
    action's name and arguments from the frozen archive.

    Fields rendered:
      state_summary  — task description + initial environment state
      user_intent    — user scenario instructions
      tool_name      — gold action name
      tool_arguments — gold action arguments (JSON)
    """

    def __init__(
        self,
        archive_path: Optional[Path] = None,
        renderer: Optional[PromptRenderer] = None,
    ) -> None:
        self.archive_path = archive_path or TAU_ARCHIVE_PATH
        self.renderer = renderer or PromptRenderer()
        self._tasks: Optional[list[dict]] = None
        self._tasks_by_id: Optional[dict[str, dict]] = None

    @property
    def tasks(self) -> list[dict]:
        if self._tasks is None:
            self._load_archive()
        return self._tasks  # type: ignore[return-value]

    def _load_archive(self) -> None:
        """Load tasks.json from the frozen archive and index by task id."""
        if not self.archive_path.exists():
            raise FileNotFoundError(
                f"tau2-bench archive not found at {self.archive_path}. "
                "Download from https://github.com/sierra-research/tau2-bench "
                "release v1.0.1 and place in data/raw/."
            )
        with zipfile.ZipFile(self.archive_path) as archive:
            raw = json.loads(archive.read(TAU_TASKS_PATH).decode("utf-8"))
        self._tasks = raw
        self._tasks_by_id = {str(task.get("id", task.get("task_id", ""))): task for task in raw}

    def _parse_event_id(self, event: dict) -> tuple[str, str]:
        """Parse a tau2 event_id into (task_id, action_id).

        event_id format: "tau2:retail:{task_id}:{action_id}"
        """
        parts = event["event_id"].split(":")
        if len(parts) < 4:
            raise ValueError(f"Unexpected tau2 event_id format: {event['event_id']}")
        task_id = parts[2]
        action_id = parts[3]
        return task_id, action_id

    def _find_action(self, task: dict, action_id: str) -> dict:
        """Find the specific action within a task's gold actions."""
        actions = task.get("evaluation_criteria", {}).get("actions", [])
        for idx, action in enumerate(actions):
            aid = action.get("action_id", f"{task.get('id', '')}_{idx}")
            if str(aid) == action_id:
                return action
        # Fallback: try by index
        try:
            idx = int(action_id.split("_")[-1]) if "_" in action_id else int(action_id)
            if 0 <= idx < len(actions):
                return actions[idx]
        except (ValueError, IndexError):
            pass
        raise KeyError(f"Action {action_id} not found in task {task.get('id', 'unknown')}")

    def _extract_state_summary(self, task: dict) -> str:
        """Build a state summary from the task's description and initial state."""
        parts: list[str] = []

        description = task.get("description", "")
        if description:
            parts.append(f"Task description: {description}")

        # Try common key names for initial/user state
        user_scenario = task.get("user_scenario", {})
        if isinstance(user_scenario, dict):
            persona = user_scenario.get("persona", "")
            if persona:
                parts.append(f"User persona: {persona}")

        initial_state = task.get("initial_state", task.get("state", {}))
        if isinstance(initial_state, dict) and initial_state:
            state_str = json.dumps(initial_state, ensure_ascii=False, indent=2)
            parts.append(f"Initial state: {state_str}")

        return "\n".join(parts) if parts else "No state summary available."

    def _extract_user_intent(self, task: dict) -> str:
        """Extract user intent from the task's user scenario."""
        user_scenario = task.get("user_scenario", {})
        if isinstance(user_scenario, dict):
            instructions = user_scenario.get(
                "instructions",
                user_scenario.get("task", user_scenario.get("goal", "")),
            )
            if instructions:
                return str(instructions)
        # Fallback to description
        return str(task.get("description", "No user intent available."))

    def materialize(self, event: dict) -> MaterializedRecord:
        """Produce a fully rendered verifier input for one tau2-bench event.

        Args:
            event: A single event dict from the G2 event manifest.

        Returns:
            MaterializedRecord with rendered prompt ready for profiling.
        """
        if self._tasks_by_id is None:
            self._load_archive()
        task_id, action_id = self._parse_event_id(event)
        task = self._tasks_by_id.get(task_id)  # type: ignore[union-attr]
        if task is None:
            raise KeyError(f"Task {task_id} not found in tau2 tasks.json")

        action = self._find_action(task, action_id)

        state_summary = self._extract_state_summary(task)
        user_intent = self._extract_user_intent(task)
        tool_name = action.get("name", event.get("tool_name", "unknown"))
        tool_arguments = json.dumps(
            action.get("arguments", action.get("args", {})),
            ensure_ascii=False,
        )
        hard_required = event.get("hard_required", False)

        return self.renderer.render(
            event_id=event["event_id"],
            source=TAU_SOURCE,
            source_version=TAU_VERSION,
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
        """Materialize a batch of tau2-bench events.

        Returns:
            Tuple of (successful records, list of error messages for failures).
        """
        records: list[MaterializedRecord] = []
        errors: list[str] = []
        for event in events:
            if event.get("source") != TAU_SOURCE:
                continue
            try:
                records.append(self.materialize(event))
            except Exception as exc:
                errors.append(f"event_id={event['event_id']}: {exc}")
        return records, errors
