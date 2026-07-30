"""Frozen G2 v3 verifier-prompt rendering helpers.

All prompt construction is locked to:
  - policy-v1.txt
  - verifier-v1.txt
  - Qwen3 chat template  (enable_thinking=False, add_generation_prompt=True)
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from transformers import AutoTokenizer

POLICY_PATH = Path("experiments/prompts/policy-v1.txt")
TEMPLATE_PATH = Path("experiments/prompts/verifier-v1.txt")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def render_chat_prompt(
    record: dict,
    template: str,
    policy: str,
    tokenizer: AutoTokenizer,
) -> str:
    """Render the final chat-formatted prompt that enters the model."""
    rendered = template.replace("{{policy}}", policy)
    rendered = rendered.replace("{{state_summary}}", record.get("state_summary", ""))
    rendered = rendered.replace("{{user_intent}}", record.get("user_intent", ""))
    rendered = rendered.replace("{{source}}", record.get("source", ""))
    rendered = rendered.replace("{{tool_name}}", record.get("tool_name", ""))
    rendered = rendered.replace("{{tool_arguments}}", record.get("tool_arguments", ""))
    rendered = rendered.replace(
        "{{hard_required}}", "true" if record.get("hard_required") else "false"
    )
    messages = [{"role": "user", "content": rendered}]
    return tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        enable_thinking=False,
        add_generation_prompt=True,
    )
