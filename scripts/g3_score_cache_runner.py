#!/usr/bin/env python3
"""Materialize the frozen dual-verifier score cache required by the G3 pilot.

Run this on the same cloud GPU used for the audited G2 v3 profiles.  It scores
only 500 tau2 evaluation actions plus 50 tau2 and 150 SafeToolBench calibration
actions.  AgentDojo is intentionally excluded: the frozen records lack a
pre-execution tool action and must not be fabricated for this replay.

The runner never writes benchmark safety labels into the cache.  Those labels
are read later only by the calibration/audit layer, not by routing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer
except ModuleNotFoundError:  # Allows --help and static inspection off the cloud GPU image.
    torch = None  # type: ignore[assignment]
    transformers = None  # type: ignore[assignment]
    AutoModelForCausalLM = None  # type: ignore[assignment,misc]
    AutoTokenizer = None  # type: ignore[assignment,misc]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.g3_replay import (
    MODEL_SPECS,
    SCORE_CACHE_CONTRACT_VERSION,
    _expected_scored_events,
)
from src.verifier_prompting import render_chat_prompt, sha256_text


MAX_INPUT_TOKENS = 4096
MAX_NEW_TOKENS = 1


def git_revision() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, check=True, text=True
        )
    except Exception:
        return ""
    return completed.stdout.strip()


def input_length_tercile(tokens: int, boundaries: dict[str, Any]) -> str:
    if tokens <= int(boundaries["short_max"]):
        return "short"
    if tokens <= int(boundaries["medium_max"]):
        return "medium"
    return "long"


def load_jsonl_by_id(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            event_id = str(record.get("event_id", ""))
            if not event_id:
                raise ValueError(f"{path}:{line_number}: missing event_id")
            if event_id in records:
                raise ValueError(f"{path}:{line_number}: duplicate event_id {event_id}")
            records[event_id] = record
    return records


def run_score_cache(
    tier: str,
    records_path: Path,
    event_manifest_path: Path,
    profiling_selection_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    if torch is None or transformers is None or AutoTokenizer is None or AutoModelForCausalLM is None:
        return {"passed": False, "error": "PyTorch and transformers are required on the cloud GPU image"}
    from src.verifier_runtime import SingleTokenLabelConstraint

    if not torch.cuda.is_available():
        return {"passed": False, "error": "CUDA not available"}
    manifest = json.loads(event_manifest_path.read_text(encoding="utf-8"))
    selection = json.loads(profiling_selection_path.read_text(encoding="utf-8"))
    boundaries = selection.get("token_tercile_boundaries")
    if not isinstance(boundaries, dict) or set(boundaries) != {"short_max", "medium_max"}:
        return {"passed": False, "error": "invalid frozen G2 v3 token-tercile boundaries"}
    targets = _expected_scored_events(manifest)
    expected_count = 700
    if len(targets) != expected_count:
        return {
            "passed": False,
            "error": f"expected exactly {expected_count} permitted score inputs, found {len(targets)}",
        }
    materialized = load_jsonl_by_id(records_path)
    missing = [event["event_id"] for event in targets if event["event_id"] not in materialized]
    if missing:
        return {
            "passed": False,
            "error": f"missing {len(missing)} materialized inputs (first: {missing[:3]})",
        }
    spec = MODEL_SPECS[tier]
    policy_path = PROJECT_ROOT / "experiments/prompts/policy-v1.txt"
    template_path = PROJECT_ROOT / "experiments/prompts/verifier-v1.txt"
    policy = policy_path.read_text(encoding="utf-8")
    template = template_path.read_text(encoding="utf-8")
    policy_sha256 = sha256_text(policy)
    template_sha256 = hashlib.sha256(template.encode("utf-8")).hexdigest().lower()
    print(f"Loading {spec['model_id']} at frozen revision {spec['revision']}...")
    try:
        tokenizer = AutoTokenizer.from_pretrained(spec["model_id"], revision=spec["revision"])
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        constraint = SingleTokenLabelConstraint.from_tokenizer(tokenizer)
        model = AutoModelForCausalLM.from_pretrained(
            spec["model_id"],
            revision=spec["revision"],
            torch_dtype=torch.bfloat16,
            device_map="auto",
        )
        model.eval()
    except Exception as exc:
        return {"passed": False, "error": f"model/tokenizer setup failed: {exc}"}
    generation_kwargs = {
        "max_new_tokens": MAX_NEW_TOKENS,
        "do_sample": False,
        "pad_token_id": tokenizer.pad_token_id,
        "logits_processor": constraint.logits_processor(),
        "return_dict_in_generate": True,
        "output_scores": True,
    }
    output_rows: list[dict[str, Any]] = []
    started = time.time()
    try:
        for index, event in enumerate(targets, start=1):
            event_id = str(event["event_id"])
            record = materialized[event_id]
            if record.get("source") != event.get("source"):
                raise ValueError(f"{event_id}: materialized source does not match frozen manifest")
            if bool(record.get("hard_required")) != bool(event.get("hard_required")):
                raise ValueError(f"{event_id}: materialized hard_required does not match frozen manifest")
            if str(record.get("policy_sha256", "")).lower() != policy_sha256:
                raise ValueError(f"{event_id}: materialized policy hash does not match frozen policy")
            if str(record.get("prompt_template_sha256", "")).lower() != template_sha256:
                raise ValueError(f"{event_id}: materialized template hash does not match frozen template")
            # The render contract exposes only model-visible fields.  The event
            # manifest's ground-truth label is not merged into this record.
            prompt = render_chat_prompt(record, template, policy, tokenizer)
            prompt_sha256 = sha256_text(prompt)
            inputs = tokenizer(prompt, add_special_tokens=False, return_tensors="pt").to(model.device)
            input_tokens = int(inputs.input_ids.shape[1])
            if input_tokens > MAX_INPUT_TOKENS:
                raise ValueError(f"{event_id}: input exceeds {MAX_INPUT_TOKENS} tokens")
            with torch.no_grad():
                outputs = model.generate(**inputs, **generation_kwargs)
            generated = outputs.sequences[0][input_tokens:]
            label, raw_output = constraint.decode(tokenizer, generated)
            if label is None:
                raise ValueError(f"{event_id}: constrained decode violation {raw_output!r}")
            probabilities = constraint.probabilities(outputs.scores[0][0])
            risk_score = min(1.0, max(0.0, float(probabilities["1"] + probabilities["2"])))
            output_rows.append(
                {
                    "score_cache_contract_version": SCORE_CACHE_CONTRACT_VERSION,
                    "status": "ok",
                    "tier": tier,
                    "event_id": event_id,
                    "source": event["source"],
                    "split": event["split"],
                    "model_id": spec["model_id"],
                    "revision": spec["revision"],
                    "dtype": "bfloat16",
                    "verifier_prompt_sha256": prompt_sha256,
                    "input_tokens": input_tokens,
                    "input_length_tercile": input_length_tercile(input_tokens, boundaries),
                    "output_tokens": int(generated.shape[0]),
                    "raw_output": raw_output,
                    "label": label,
                    "constrained_label_probabilities": probabilities,
                    "risk_score": risk_score,
                    "policy_sha256": policy_sha256,
                    "template_sha256": template_sha256,
                    "decoding_constraint": constraint.metadata,
                    "selection_sha256": selection.get("selection_sha256"),
                    "code_git_revision": git_revision(),
                }
            )
            if index % 25 == 0 or index == len(targets):
                print(f"{tier}: scored {index}/{len(targets)}")
    except Exception as exc:
        del model
        del tokenizer
        torch.cuda.empty_cache()
        return {"passed": False, "error": str(exc), "completed_rows": len(output_rows)}
    del model
    del tokenizer
    torch.cuda.empty_cache()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in output_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = {
        "passed": True,
        "tier": tier,
        "output": str(output_path),
        "rows": len(output_rows),
        "elapsed_seconds": round(time.time() - started, 2),
        "gpu": torch.cuda.get_device_name(0),
        "torch_version": torch.__version__,
        "transformers_version": transformers.__version__,
        "model": spec,
        "selection_sha256": selection.get("selection_sha256"),
        "code_git_revision": git_revision(),
    }
    output_path.with_suffix(".summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", required=True, choices=sorted(MODEL_SPECS))
    parser.add_argument(
        "--records", type=Path, default=Path("data/processed/g2-materialized-records.jsonl")
    )
    parser.add_argument("--event-manifest", type=Path, default=Path("data/g2-event-selection.json"))
    parser.add_argument(
        "--profiling-selection",
        type=Path,
        default=Path("data/processed/g2-profiling-selection.v3.json"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or Path(f"artifact/cloud-gpu/g3-scores-{args.tier}.jsonl")
    summary = run_score_cache(
        args.tier, args.records, args.event_manifest, args.profiling_selection, output
    )
    if summary.get("error"):
        print(f"ERROR: {summary['error']}", file=sys.stderr)
    return 0 if summary.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
