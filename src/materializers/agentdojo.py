"""Materializer for AgentDojo (v1.2.2, package v0.1.35).

Reads the frozen AgentDojo archive and extracts user task descriptions and
injection task descriptions from the Python source files.

IMPORTANT: AgentDojo does not provide pre-recorded gold actions.  The
tool_name and tool_arguments fields CANNOT be populated from the archive
alone — they require environment execution.  Events materialized here carry
a placeholder noting this limitation.  Per the profiling input contract,
AgentDojo events that cannot render a call-time visible action are NOT
eligible for verifier latency profiling; they are held-out security evidence.
"""

from __future__ import annotations

import ast
import json
import re
import zipfile
from pathlib import Path
from typing import Optional

from src.materializers.base import MaterializedRecord, PromptRenderer

DOJO_ARCHIVE_PATH = Path("data/raw/agentdojo-v0.1.35.zip")
DOJO_SOURCE = "agentdojo"
DOJO_PACKAGE_VERSION = "package-v0.1.35"
DOJO_BENCHMARK_VERSION = "v1.2.2"
DOJO_TASKS_PREFIX = "agentdojo-0.1.35/src/agentdojo/default_suites/"


def _parse_version_dir(name: str) -> tuple[int, ...]:
    match = re.fullmatch(r"v(\d+(?:_\d+)*)", name)
    if not match:
        return ()
    return tuple(int(part) for part in match.group(1).split("_"))


def _extract_class_docstring(class_node: ast.ClassDef) -> str:
    """Extract the docstring from a class definition node."""
    if (
        class_node.body
        and isinstance(class_node.body[0], ast.Expr)
        and isinstance(class_node.body[0].value, (ast.Constant, ast.Str))
    ):
        val = class_node.body[0].value
        return str(val.value if isinstance(val, ast.Constant) else val.s)
    return ""


def _extract_class_attributes(class_node: ast.ClassDef) -> dict[str, str]:
    """Extract string-valued class-level assignments (e.g. PROMPT, TASK)."""
    attrs: dict[str, str] = {}
    for node in class_node.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(node.value, (ast.Constant, ast.Str)):
                    val = node.value
                    attrs[target.id] = str(val.value if isinstance(val, ast.Constant) else val.s)
    return attrs


def _literal_function_calls(class_node: ast.ClassDef) -> list[str]:
    """Extract FunctionCall target function names from AST."""
    functions: list[str] = []
    for node in ast.walk(class_node):
        if not isinstance(node, ast.Call):
            continue
        call_name = None
        if isinstance(node.func, ast.Name):
            call_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            call_name = node.func.attr
        if (
            call_name == "FunctionCall"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            functions.append(node.args[0].value)
        for keyword in node.keywords:
            if (
                keyword.arg == "function"
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, str)
            ):
                functions.append(keyword.value.value)
    return list(dict.fromkeys(functions))


class AgentDojoMaterializer:
    """Materialize verifier inputs from AgentDojo security cases.

    Extracts user task descriptions and injection task descriptions by
    parsing Python source files from the frozen archive.  Because AgentDojo
    does not ship pre-recorded agent actions, tool_name and tool_arguments
    are rendered as placeholder values indicating environment execution
    is required.

    Fields rendered:
      state_summary  — combined user task and injection task descriptions
      user_intent    — user task description (the benign user's goal)
      tool_name      — target functions from injection task (if available),
                       otherwise "requires_environment_execution"
      tool_arguments — "requires_environment_execution"
    """

    def __init__(
        self,
        archive_path: Optional[Path] = None,
        renderer: Optional[PromptRenderer] = None,
    ) -> None:
        self.archive_path = archive_path or DOJO_ARCHIVE_PATH
        self.renderer = renderer or PromptRenderer()
        self._task_cache: Optional[dict[tuple[str, str], dict]] = None

    @property
    def task_cache(self) -> dict[tuple[str, str], dict]:
        """Lazy cache: {(domain, task_type, task_number): {desc, target_functions}}."""
        if self._task_cache is None:
            self._load_archive()
        return self._task_cache  # type: ignore[return-value]

    def _load_archive(self) -> None:
        """Parse all AgentDojo user_tasks.py and injection_tasks.py files."""
        if not self.archive_path.exists():
            raise FileNotFoundError(
                f"AgentDojo archive not found at {self.archive_path}. "
                "Download release v0.1.35 from "
                "https://github.com/ethz-spylab/agentdojo and save to data/raw/."
            )
        self._task_cache = {}
        with zipfile.ZipFile(self.archive_path) as archive:
            for name in archive.namelist():
                if not name.startswith(DOJO_TASKS_PREFIX):
                    continue
                if not name.endswith(("user_tasks.py", "injection_tasks.py")):
                    continue
                relative = name[len(DOJO_TASKS_PREFIX):]
                parts = relative.split("/")
                if len(parts) < 3:
                    continue
                version = _parse_version_dir(parts[0])
                if not version:
                    continue
                domain = parts[-2]
                file_type = parts[-1]  # "user_tasks.py" or "injection_tasks.py"
                text = archive.read(name).decode("utf-8")
                tree = ast.parse(text, filename=name)

                for node in tree.body:
                    if not isinstance(node, ast.ClassDef):
                        continue
                    user_match = re.fullmatch(r"UserTask(\d+)", node.name)
                    injection_match = re.fullmatch(r"InjectionTask(\d+)", node.name)
                    if not user_match and not injection_match:
                        continue

                    task_number = int(
                        (user_match or injection_match).group(1)  # type: ignore[union-attr]
                    )
                    task_type = "user" if user_match else "injection"
                    docstring = _extract_class_docstring(node)
                    attrs = _extract_class_attributes(node)
                    target_funcs = _literal_function_calls(node) if injection_match else []

                    # Build description from docstring and relevant attributes
                    desc_parts: list[str] = []
                    if docstring:
                        desc_parts.append(docstring)
                    for attr_name in ("PROMPT", "TASK", "GOAL", "USER_PROMPT"):
                        if attr_name in attrs:
                            desc_parts.append(f"{attr_name}: {attrs[attr_name]}")
                    description = "\n".join(desc_parts) if desc_parts else ""

                    self._task_cache[(domain, task_type, task_number)] = {
                        "description": description,
                        "target_functions": target_funcs,
                        "domain": domain,
                        "task_type": task_type,
                        "task_number": task_number,
                    }

    def _parse_session_id(self, session_id: str) -> tuple[str, str, str]:
        """Parse session_id into (domain, user_task, injection_task).

        Format: "agentdojo:{domain}:user_task_N:injection_task_M"
        """
        parts = session_id.split(":")
        if len(parts) < 4:
            raise ValueError(f"Unexpected AgentDojo session_id: {session_id}")
        return parts[1], parts[2], parts[3]

    def materialize(self, event: dict) -> MaterializedRecord:
        """Produce a rendered verifier input for one AgentDojo event.

        Args:
            event: A single event dict from the G2 event manifest.

        Returns:
            MaterializedRecord with rendered prompt.
        """
        domain, user_task_id, injection_task_id = self._parse_session_id(
            event["session_id"]
        )

        # Parse task numbers
        user_num = int(user_task_id.replace("user_task_", ""))
        injection_num = int(injection_task_id.replace("injection_task_", ""))

        user_info = self.task_cache.get((domain, "user", user_num), {})
        injection_info = self.task_cache.get((domain, "injection", injection_num), {})

        user_desc = user_info.get("description", "")
        injection_desc = injection_info.get("description", "")
        target_funcs = injection_info.get("target_functions", [])

        # Build state summary from both task descriptions.
        # IMPORTANT: Do NOT leak structural labels like "injection_task"
        # or "user_task" into the model input.  Use neutral identifiers.
        parts: list[str] = []
        if user_desc:
            parts.append(f"Task context ({domain}):\n{user_desc}")
        if injection_desc:
            parts.append(f"Additional context ({domain}):\n{injection_desc}")
        if not parts:
            parts.append(f"AgentDojo context: {domain}")
        state_summary = "\n\n".join(parts)

        # User intent is the user's benign task
        user_intent = user_desc or f"AgentDojo {domain} user task {user_task_id}"

        # AgentDojo does not provide pre-recorded actions.
        # Render known tool names as context when available,
        # but flag that environment execution is needed for actual proposed action.
        if target_funcs:
            tool_name = ", ".join(target_funcs)
            tool_arguments = (
                "Known tools available in this context: "
                + json.dumps(target_funcs, ensure_ascii=False)
            )
        else:
            tool_name = "requires_environment_execution"
            tool_arguments = (
                "AgentDojo does not ship pre-recorded agent actions. "
                "This event requires environment execution to obtain the actual "
                "proposed action (tool_name, tool_arguments). Per the profiling "
                "input contract, events without call-time visible actions are not "
                "eligible for verifier latency profiling."
            )

        hard_required = event.get("hard_required", False)

        return self.renderer.render(
            event_id=event["event_id"],
            source=DOJO_SOURCE,
            source_version=f"{DOJO_PACKAGE_VERSION}/{DOJO_BENCHMARK_VERSION}",
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
        """Materialize a batch of AgentDojo events.

        Returns:
            Tuple of (successful records, list of error messages).
        """
        records: list[MaterializedRecord] = []
        errors: list[str] = []
        for event in events:
            if event.get("source") != DOJO_SOURCE:
                continue
            try:
                records.append(self.materialize(event))
            except Exception as exc:
                errors.append(f"event_id={event['event_id']}: {exc}")
        return records, errors



