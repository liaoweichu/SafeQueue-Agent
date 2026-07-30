"""Protocol-locked rendering and constrained decoding for G2 verifiers.

The profiling selector, smoke test, and profiling runner must use exactly the
same chat rendering and label semantics.  Keeping them here prevents a later
script-only change from silently invalidating latency measurements.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

import torch
from transformers import LogitsProcessor, LogitsProcessorList

from src.verifier_prompting import render_chat_prompt, render_verifier_payload, sha256_text


ALLOWED_LABELS = ("0", "1", "2")
CONSTRAINT_VERSION = "single_token_label_logits_mask_v1"


@dataclass(frozen=True)
class SingleTokenLabelConstraint:
    """Restrict one decoding step to the three frozen verifier labels."""

    label_token_ids: dict[str, int]

    @classmethod
    def from_tokenizer(cls, tokenizer: Any) -> "SingleTokenLabelConstraint":
        token_ids: dict[str, int] = {}
        for label in ALLOWED_LABELS:
            ids = tokenizer.encode(label, add_special_tokens=False)
            decoded = tokenizer.decode(ids, skip_special_tokens=True).strip()
            if len(ids) != 1 or decoded != label:
                raise ValueError(
                    "Frozen Qwen tokenizer cannot represent label "
                    f"{label!r} as one exact token: ids={ids}, decoded={decoded!r}"
                )
            token_ids[label] = int(ids[0])
        if len(set(token_ids.values())) != len(ALLOWED_LABELS):
            raise ValueError(f"Verifier labels map to duplicate token IDs: {token_ids}")
        return cls(label_token_ids=token_ids)

    @property
    def allowed_token_ids(self) -> list[int]:
        return [self.label_token_ids[label] for label in ALLOWED_LABELS]

    @property
    def metadata(self) -> dict[str, Any]:
        payload = {
            "version": CONSTRAINT_VERSION,
            "allowed_labels": list(ALLOWED_LABELS),
            "label_token_ids": self.label_token_ids,
            "max_new_tokens": 1,
            "probability_semantics": "softmax over first-step logits restricted to labels 0/1/2",
        }
        return {
            **payload,
            "sha256": hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        }

    def logits_processor(self) -> LogitsProcessorList:
        return LogitsProcessorList([_AllowedLabelLogitsProcessor(self.allowed_token_ids)])

    def decode(self, tokenizer: Any, generated_token_ids: Any) -> tuple[str | None, str]:
        """Return the exact label and decoded text, or ``None`` on any violation."""
        ids = [int(token_id) for token_id in generated_token_ids.tolist()]
        text = tokenizer.decode(ids, skip_special_tokens=True).strip()
        if len(ids) != 1:
            return None, text
        inverse = {token_id: label for label, token_id in self.label_token_ids.items()}
        label = inverse.get(ids[0])
        if label is None or text != label:
            return None, text
        return label, text

    def probabilities(self, processed_scores: torch.Tensor) -> dict[str, float]:
        """Normalize the processed first-step logits across the allowed labels."""
        allowed_logits = processed_scores[self.allowed_token_ids]
        probabilities = torch.softmax(allowed_logits.float(), dim=-1).tolist()
        return {
            label: float(probability)
            for label, probability in zip(ALLOWED_LABELS, probabilities, strict=True)
        }


class _AllowedLabelLogitsProcessor(LogitsProcessor):
    """Mask every next-token logit except the frozen label-token set."""

    def __init__(self, allowed_token_ids: list[int]) -> None:
        self.allowed_token_ids = allowed_token_ids

    def __call__(self, input_ids: torch.Tensor, scores: torch.Tensor) -> torch.Tensor:
        del input_ids
        constrained = torch.full_like(scores, float("-inf"))
        constrained[:, self.allowed_token_ids] = scores[:, self.allowed_token_ids]
        return constrained
