#!/usr/bin/env python3
"""Materialize the owner-signed G3-R1 dual-verifier score caches on a cloud GPU.

The runner scores exactly the 1,000 materialized inputs in the signed G3-R1
manifest.  It does not run tools, train models, or serialize benchmark labels
into model caches.  The 300 SafeToolBench holdout inputs are eligible only
after the row-level owner signoff produced by ``finalize_g3r1_holdout_signoff``.
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
except ModuleNotFoundError:  # Keep --help/static checks usable off the cloud image.
    torch = None  # type: ignore[assignment]
    transformers = None  # type: ignore[assignment]
    AutoModelForCausalLM = None  # type: ignore[assignment,misc]
    AutoTokenizer = None  # type: ignore[assignment,misc]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.g3_replay import MODEL_SPECS
from src.g3r1_replay import SCORE_CACHE_CONTRACT_VERSION, expected_counts, expected_score_events
from src.verifier_prompting import render_chat_prompt, sha256_text


MAX_INPUT_TOKENS = 4096
MAX_NEW_TOKENS = 1


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


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


def assert_signed_inputs(
    manifest: dict[str, Any], config: dict[str, Any], summary: dict[str, Any]
) -> dict[str, Any]:
    frozen = config["frozen_inputs"]
    manifest_frozen = frozen["event_manifest"]
    profile = frozen["g3r1_profile_selection"]
    if config.get("status") != "owner_signed_service_profile_frozen":
        raise ValueError("G3-R1 score caching requires an owner-signed, profile-frozen config")
    if manifest.get("status") != "owner_signed":
        raise ValueError("G3-R1 score caching requires an owner_signed manifest")
    if manifest.get("selection_sha256") != manifest_frozen.get("selection_sha256"):
        raise ValueError("event manifest selection_sha256 does not match signed config")
    if profile.get("event_manifest_sha256") != manifest.get("selection_sha256"):
        raise ValueError("profile selection is not bound to the signed event manifest")
    if summary.get("manifest_sha256") != manifest.get("selection_sha256"):
        raise ValueError("materialization summary does not match signed event manifest")
    if summary.get("total_materialized") != config["scope"]["scored_events_per_tier"]:
        raise ValueError("materialization summary row count does not match signed scope")
    if summary.get("errors_by_source"):
        raise ValueError("materialization summary records source errors")
    boundaries = profile.get("token_tercile_boundaries")
    if not isinstance(boundaries, dict) or set(boundaries) != {"short_max", "medium_max"}:
        raise ValueError("invalid frozen G3-R1 token-tercile boundaries")
    expected = expected_counts(manifest)
    if expected["total_per_tier"] != int(config["scope"]["scored_events_per_tier"]):
        raise ValueError(f"expected {config['scope']['scored_events_per_tier']} score inputs, found {expected}")
    return boundaries


def run_score_cache(
    tier: str,
    records_path: Path,
    event_manifest_path: Path,
    materialization_summary_path: Path,
    profiling_selection_path: Path,
    config_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    if torch is None or transformers is None or AutoTokenizer is None or AutoModelForCausalLM is None:
        return {"passed": False, "error": "PyTorch and transformers are required on the cloud GPU image"}
    from src.verifier_runtime import SingleTokenLabelConstraint

    if not torch.cuda.is_available():
        return {"passed": False, "error": "CUDA not available"}
    manifest = load_json(event_manifest_path)
    config = load_json(config_path)
    summary = load_json(materialization_summary_path)
    selection = load_json(profiling_selection_path)
    if selection.get("selection_contract_version") != config["frozen_inputs"]["g3r1_profile_selection"][
        "selection_contract_version"
    ]:
        return {"passed": False, "error": "G3-R1 profiling selection contract does not match signed config"}
    if selection.get("selection_sha256") != config["frozen_inputs"]["g3r1_profile_selection"]["selection_sha256"]:
        return {"passed": False, "error": "G3-R1 profiling selection SHA does not match signed config"}
    boundaries = assert_signed_inputs(manifest, config, summary)
    if selection.get("token_tercile_boundaries") != boundaries:
        return {"passed": False, "error": "G3-R1 profiling token boundaries do not match signed config"}
    targets = expected_score_events(manifest)
    materialized = load_jsonl_by_id(records_path)
    missing = [str(event["event_id"]) for event in targets if str(event["event_id"]) not in materialized]
    if missing:
        return {"passed": False, "error": f"missing {len(missing)} materialized inputs (first: {missing[:3]})"}
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
                raise ValueError(f"{event_id}: materialized source does not match signed manifest")
            if bool(record.get("hard_required")) != bool(event.get("hard_required")):
                raise ValueError(f"{event_id}: materialized hard_required does not match signed manifest")
            if str(record.get("policy_sha256", "")).lower() != policy_sha256:
                raise ValueError(f"{event_id}: materialized policy hash does not match frozen policy")
            if str(record.get("prompt_template_sha256", "")).lower() != template_sha256:
                raise ValueError(f"{event_id}: materialized template hash does not match frozen template")
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
                    "event_manifest_sha256": manifest["selection_sha256"],
                    "service_profile_selection_sha256": selection["selection_sha256"],
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
    result = {
        "passed": True,
        "tier": tier,
        "output": str(output_path),
        "rows": len(output_rows),
        "elapsed_seconds": round(time.time() - started, 2),
        "gpu": torch.cuda.get_device_name(0),
        "torch_version": torch.__version__,
        "transformers_version": transformers.__version__,
        "model": spec,
        "event_manifest_sha256": manifest["selection_sha256"],
        "service_profile_selection_sha256": selection["selection_sha256"],
        "code_git_revision": git_revision(),
    }
    output_path.with_suffix(".summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", required=True, choices=sorted(MODEL_SPECS))
    parser.add_argument(
        "--config", type=Path,
        default=Path("experiments/configs/g3r1-serial-abstain-escalation.owner-signed.profile-frozen.json"),
    )
    parser.add_argument(
        "--records", type=Path, default=Path("data/processed/g3r1-materialized-records.jsonl")
    )
    parser.add_argument("--event-manifest", type=Path)
    parser.add_argument(
        "--materialization-summary", type=Path,
        default=Path("data/processed/g3r1-materialization-summary.json"),
    )
    parser.add_argument(
        "--profiling-selection", type=Path,
        default=Path("data/processed/g3r1-profiling-selection.v1.json"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        config = load_json(args.config)
        manifest_path = args.event_manifest or Path(config["frozen_inputs"]["event_manifest"]["path"])
        output = args.output or Path(f"artifact/cloud-gpu/g3r1-scores-{args.tier}.jsonl")
        summary = run_score_cache(
            args.tier,
            args.records,
            manifest_path,
            args.materialization_summary,
            args.profiling_selection,
            args.config,
            output,
        )
    except Exception as exc:
        summary = {"passed": False, "error": str(exc)}
    if summary.get("error"):
        print(f"ERROR: {summary['error']}", file=sys.stderr)
    return 0 if summary.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
