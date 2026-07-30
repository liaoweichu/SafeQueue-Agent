"""Dependency-light frozen prompt rendering shared by G2 tools."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping


def sha256_text(value: str) -> str:
    """Return the lowercase SHA-256 digest used by JSON artifacts."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def render_verifier_payload(record: Mapping[str, Any], template: str, policy: str) -> str:
    """Fill the frozen verifier template with model-visible record fields only."""
    rendered = template.replace("{{policy}}", policy)
    rendered = rendered.replace("{{state_summary}}", str(record.get("state_summary", "")))
    rendered = rendered.replace("{{user_intent}}", str(record.get("user_intent", "")))
    rendered = rendered.replace("{{source}}", str(record.get("source", "")))
    rendered = rendered.replace("{{tool_name}}", str(record.get("tool_name", "")))
    rendered = rendered.replace("{{tool_arguments}}", str(record.get("tool_arguments", "")))
    return rendered.replace(
        "{{hard_required}}", "true" if bool(record.get("hard_required")) else "false"
    )


def render_chat_prompt(record: Mapping[str, Any], template: str, policy: str, tokenizer: Any) -> str:
    """Render the exact non-thinking Qwen chat prompt used for inference."""
    payload = render_verifier_payload(record, template, policy)
    return tokenizer.apply_chat_template(
        [{"role": "user", "content": payload}],
        tokenize=False,
        enable_thinking=False,
        add_generation_prompt=True,
    )
