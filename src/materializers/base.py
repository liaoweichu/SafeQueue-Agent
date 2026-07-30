"""Base classes and the prompt renderer for G2 source-to-prompt materialization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Absolute paths; these will be determined from the project root.
DEFAULT_POLICY_PATH = Path("experiments/prompts/policy-v1.txt")
DEFAULT_TEMPLATE_PATH = Path("experiments/prompts/verifier-v1.txt")
DEFAULT_EVENT_MANIFEST = Path("data/g2-event-selection.json")


@dataclass
class MaterializedRecord:
    """A single fully-materialized verifier input record.

    Every field populated here is safe for model input (no attack labels,
    benchmark outcomes, or post-execution state).
    """

    event_id: str
    source: str
    source_version: str
    policy_text: str
    policy_sha256: str
    prompt_template_sha256: str
    state_summary: str
    user_intent: str
    tool_name: str
    tool_arguments: str
    hard_required: bool
    rendered_prompt: str = field(repr=False)
    rendered_prompt_sha256: str = ""

    def __post_init__(self) -> None:
        if not self.rendered_prompt_sha256:
            self.rendered_prompt_sha256 = hashlib.sha256(
                self.rendered_prompt.encode("utf-8")
            ).hexdigest()

    def to_dict(self) -> dict:
        """Serialize to the profiling input contract format."""
        return {
            "event_id": self.event_id,
            "source": self.source,
            "source_version": self.source_version,
            "policy_text": self.policy_text,
            "policy_sha256": self.policy_sha256,
            "prompt_template_sha256": self.prompt_template_sha256,
            "state_summary": self.state_summary,
            "user_intent": self.user_intent,
            "tool_name": self.tool_name,
            "tool_arguments": self.tool_arguments,
            "hard_required": self.hard_required,
            "rendered_prompt_sha256": self.rendered_prompt_sha256,
        }


class PromptRenderer:
    """Renders a full verifier prompt from a materialized record.

    Reads the policy text and the verifier template, fills in the
    placeholders, and produces a MaterializedRecord.
    """

    def __init__(
        self,
        policy_path: Optional[Path] = None,
        template_path: Optional[Path] = None,
    ) -> None:
        self.policy_path = policy_path or DEFAULT_POLICY_PATH
        self.template_path = template_path or DEFAULT_TEMPLATE_PATH

        self._policy_text: Optional[str] = None
        self._policy_sha256: Optional[str] = None
        self._template_text: Optional[str] = None
        self._template_sha256: Optional[str] = None

    @property
    def policy_text(self) -> str:
        if self._policy_text is None:
            self._load_policy()
        return self._policy_text  # type: ignore[return-value]

    @property
    def policy_sha256(self) -> str:
        if self._policy_sha256 is None:
            self._load_policy()
        return self._policy_sha256  # type: ignore[return-value]

    @property
    def template_text(self) -> str:
        if self._template_text is None:
            self._load_template()
        return self._template_text  # type: ignore[return-value]

    @property
    def template_sha256(self) -> str:
        if self._template_sha256 is None:
            self._load_template()
        return self._template_sha256  # type: ignore[return-value]

    def _load_policy(self) -> None:
        raw = self.policy_path.read_text(encoding="utf-8")
        self._policy_text = raw
        self._policy_sha256 = hashlib.sha256(
            raw.encode("utf-8")
        ).hexdigest()

    def _load_template(self) -> None:
        raw = self.template_path.read_text(encoding="utf-8")
        self._template_text = raw
        self._template_sha256 = hashlib.sha256(
            raw.encode("utf-8")
        ).hexdigest().upper()

    def render(
        self,
        event_id: str,
        source: str,
        source_version: str,
        state_summary: str,
        user_intent: str,
        tool_name: str,
        tool_arguments: str,
        hard_required: bool,
    ) -> MaterializedRecord:
        """Render a complete prompt for a single event.

        All string fields are treated as untrusted data by the verifier;
        do NOT embed instructions or labels inside them.
        """
        rendered = self.template_text.replace("{{policy}}", self.policy_text)
        rendered = rendered.replace("{{state_summary}}", state_summary)
        rendered = rendered.replace("{{user_intent}}", user_intent)
        rendered = rendered.replace("{{source}}", source)
        rendered = rendered.replace("{{tool_name}}", tool_name)
        rendered = rendered.replace("{{tool_arguments}}", tool_arguments)
        rendered = rendered.replace(
            "{{hard_required}}", "true" if hard_required else "false"
        )

        return MaterializedRecord(
            event_id=event_id,
            source=source,
            source_version=source_version,
            policy_text=self.policy_text,
            policy_sha256=self.policy_sha256,
            prompt_template_sha256=self.template_sha256,
            state_summary=state_summary,
            user_intent=user_intent,
            tool_name=tool_name,
            tool_arguments=tool_arguments,
            hard_required=hard_required,
            rendered_prompt=rendered,
        )
