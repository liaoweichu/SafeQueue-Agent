"""Frozen G2 v3 single-token-label logits constraint.

Constrains the first generated token to exactly ``0``, ``1``, or ``2``
by masking all other logits.  Retains the constrained probabilities
for use in the replay risk-score calculation.
"""

from __future__ import annotations

from typing import Any

import torch
from transformers import AutoTokenizer, LogitsProcessor


ALLOWED_TOKEN_IDS: tuple[int, ...] = ()
ALLOWED_TOKENS: tuple[str, ...] = ("0", "1", "2")


class SingleTokenLabelConstraint:
    """Sets a logits processor that only allows 0 / 1 / 2 at the first position."""

    def __init__(self, token_ids: tuple[int, ...]):
        self._token_ids = token_ids
        self.metadata: dict[str, Any] = {
            "version": "single_token_label_logits_mask_v1",
            "max_new_tokens": 1,
            "allowed_tokens": list(ALLOWED_TOKENS),
            "allowed_token_ids": list(token_ids),
            "enforced_by": "logits_processor",
        }

    @classmethod
    def from_tokenizer(cls, tokenizer: AutoTokenizer) -> "SingleTokenLabelConstraint":
        token_ids: list[int] = []
        for token in ALLOWED_TOKENS:
            ids = tokenizer.encode(token, add_special_tokens=False)
            if len(ids) == 1:
                token_ids.append(ids[0])
            else:
                raise ValueError(f"token {token!r} is not a single token for this tokenizer")
        return cls(tuple(token_ids))

    def logits_processor(self) -> list[LogitsProcessor]:
        allowed = self._token_ids
        mask_value = -float("inf")

        class _MaskLogits(LogitsProcessor):
            def __call__(
                self, input_ids: torch.LongTensor, scores: torch.FloatTensor
            ) -> torch.FloatTensor:
                mask = torch.full_like(scores, mask_value)
                for tid in allowed:
                    mask[0, tid] = 0.0
                return scores + mask

        return [_MaskLogits()]  # return list

    def decode(self, tokenizer: AutoTokenizer, generated_ids: torch.Tensor) -> tuple[str | None, str]:
        raw = tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
        if raw in ALLOWED_TOKENS:
            return raw, raw
        return None, raw

    def probabilities(self, scores: torch.Tensor) -> dict[str, float]:
        """Extract constrained probabilities from first-step logits."""
        probs = torch.softmax(scores, dim=-1)
        return {
            tok: round(float(probs[tid].item()), 8)
            for tok, tid in zip(ALLOWED_TOKENS, self._token_ids)
        }
