#!/usr/bin/env python3
"""Run the fresh 128 x 3 service profile for one signed G3-R1 verifier tier."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

try:
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer
except ModuleNotFoundError:  # Let static/off-cloud checks remain usable.
    torch = None  # type: ignore[assignment]
    transformers = None  # type: ignore[assignment]
    AutoModelForCausalLM = None  # type: ignore[assignment,misc]
    AutoTokenizer = None  # type: ignore[assignment,misc]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.g3_replay import MODEL_SPECS
from src.verifier_prompting import render_chat_prompt, sha256_text


SELECTION_CONTRACT_VERSION = "g3r1-profiling-v1"
MAX_INPUT_TOKENS = 4096
MAX_NEW_TOKENS = 1
WARMUP_COUNT = 10
REPETITIONS = 3
MAX_GPU_INTERFERENCE_RATE = 0.05


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * p / 100.0
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (position - lower) * (ordered[upper] - ordered[lower])


def latency_summary(measurements: list[dict[str, Any]]) -> dict[str, float | int]:
    return {
        "wall_p50_ms": round(percentile([float(row["wall_ms"]) for row in measurements], 50), 2),
        "wall_p95_ms": round(percentile([float(row["wall_ms"]) for row in measurements], 95), 2),
        "wall_p99_ms": round(percentile([float(row["wall_ms"]) for row in measurements], 99), 2),
        "cuda_p50_ms": round(percentile([float(row["cuda_ms"]) for row in measurements], 50), 2),
        "cuda_p95_ms": round(percentile([float(row["cuda_ms"]) for row in measurements], 95), 2),
        "cuda_p99_ms": round(percentile([float(row["cuda_ms"]) for row in measurements], 99), 2),
        "n_samples": len(measurements),
    }


def git_revision() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, check=True, text=True
        ).stdout.strip()
    except Exception:
        return ""


def driver_version() -> str:
    try:
        value = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
        return value.splitlines()[0].strip()
    except Exception:
        return ""


def load_selection(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def validate_selection(selection: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if selection.get("selection_contract_version") != SELECTION_CONTRACT_VERSION:
        errors.append("unexpected G3-R1 profile selection contract")
    records = selection.get("records", [])
    if selection.get("n_profiling_actions") != 128 or len(records) != 128:
        errors.append(f"selection must contain exactly 128 records, found {len(records)}")
    ids = [record.get("event_id") for record in records]
    if len(set(ids)) != len(ids):
        errors.append("selection has duplicate event IDs")
    required = {
        "profiling_prompt_sha256", "profiling_input_tokens", "input_length_tercile",
        "selection_role", "selection_source_role", "selection_source_split",
    }
    for record in records:
        missing = sorted(required - set(record))
        if missing:
            errors.append(f"{record.get('event_id')}: missing profile metadata {missing}")
    stratification = selection.get("stratification", {})
    actual_lengths = Counter(record.get("input_length_tercile") for record in records)
    if dict(actual_lengths) != stratification.get("length_quotas"):
        errors.append("length quotas do not match selected records")
    sources = Counter(record.get("source") for record in records)
    if sources.get("tau2-bench", 0) != stratification.get("tau2_evaluation_quota"):
        errors.append("tau2 evaluation quota mismatch")
    if sources.get("safetoolbench", 0) != stratification.get("safetoolbench_dangerous_evaluation_quota"):
        errors.append("SafeToolBench dangerous evaluation quota mismatch")
    hard_tau = sum(record.get("source") == "tau2-bench" and bool(record.get("hard_required")) for record in records)
    if hard_tau < int(stratification.get("tau_hard_minimum", 0)):
        errors.append("tau2 hard-action minimum is not met")
    if any(record.get("selection_role") != "replay_evaluation" for record in records):
        errors.append("all selected records must be replay_evaluation")
    if any(record.get("selection_source_split") != "evaluation" for record in records):
        errors.append("profile selection may not include calibration inputs")
    if len({record.get("profiling_prompt_sha256") for record in records}) != len(records):
        errors.append("selection contains duplicate model-ready prompt hashes")
    return errors


def run_profiling_tier(tier: str, selection_path: Path, output_path: Path, seed: int) -> dict[str, Any]:
    if torch is None or transformers is None or AutoTokenizer is None or AutoModelForCausalLM is None:
        return {"passed": False, "error": "PyTorch and transformers are required on the cloud GPU image"}
    if not torch.cuda.is_available():
        return {"passed": False, "error": "CUDA not available"}
    from src.verifier_runtime import SingleTokenLabelConstraint

    selection = load_selection(selection_path)
    selection_errors = validate_selection(selection)
    if selection_errors:
        return {"passed": False, "error": "; ".join(selection_errors)}
    records = selection["records"]
    spec = MODEL_SPECS[tier]
    policy = (PROJECT_ROOT / "experiments/prompts/policy-v1.txt").read_text(encoding="utf-8")
    template = (PROJECT_ROOT / "experiments/prompts/verifier-v1.txt").read_text(encoding="utf-8")
    policy_sha256 = sha256_text(policy)
    template_sha256 = hashlib.sha256(template.encode("utf-8")).hexdigest().lower()
    try:
        tokenizer = AutoTokenizer.from_pretrained(spec["model_id"], revision=spec["revision"])
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        constraint = SingleTokenLabelConstraint.from_tokenizer(tokenizer)
    except Exception as exc:
        return {"passed": False, "error": f"tokenizer/constraint setup failed: {exc}"}
    prompts: dict[str, str] = {}
    mismatches: list[str] = []
    for record in records:
        event_id = str(record["event_id"])
        prompt = render_chat_prompt(record, template, policy, tokenizer)
        prompts[event_id] = prompt
        tokens = len(tokenizer.encode(prompt, add_special_tokens=False))
        if sha256_text(prompt) != record.get("profiling_prompt_sha256"):
            mismatches.append(f"{event_id}: prompt hash mismatch")
        if tokens != record.get("profiling_input_tokens"):
            mismatches.append(f"{event_id}: token count mismatch")
        if tokens > MAX_INPUT_TOKENS:
            mismatches.append(f"{event_id}: exceeds {MAX_INPUT_TOKENS} tokens")
    if mismatches:
        del tokenizer
        return {"passed": False, "error": "; ".join(mismatches[:10])}
    print(f"Loading {spec['model_id']} at frozen revision {spec['revision']}...")
    torch.cuda.reset_peak_memory_stats()
    loaded_at = time.time()
    try:
        model = AutoModelForCausalLM.from_pretrained(
            spec["model_id"], revision=spec["revision"], torch_dtype=torch.bfloat16, device_map="auto"
        )
        model.eval()
    except Exception as exc:
        del tokenizer
        return {"passed": False, "error": f"model load failed: {exc}"}
    load_summary = {
        "time_s": round(time.time() - loaded_at, 2),
        "peak_vram_mb": round(torch.cuda.max_memory_allocated() / (1024 * 1024), 2),
    }
    generation_kwargs = {
        "max_new_tokens": MAX_NEW_TOKENS,
        "do_sample": False,
        "pad_token_id": tokenizer.pad_token_id,
        "logits_processor": constraint.logits_processor(),
        "return_dict_in_generate": True,
        "output_scores": True,
    }

    def run_one(record: dict[str, Any]) -> tuple[Any, int]:
        inputs = tokenizer(prompts[str(record["event_id"])], add_special_tokens=False, return_tensors="pt").to(model.device)
        return inputs, int(inputs.input_ids.shape[1])

    rng = random.Random(seed)
    try:
        for record in rng.sample(records, WARMUP_COUNT):
            inputs, _ = run_one(record)
            with torch.no_grad():
                model.generate(**inputs, **generation_kwargs)
    except Exception as exc:
        del model
        del tokenizer
        torch.cuda.empty_cache()
        return {"passed": False, "error": f"constrained warm-up failed: {exc}"}
    measurements: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    order = list(records)
    rng.shuffle(order)
    for input_index, record in enumerate(order, start=1):
        for repetition in range(REPETITIONS):
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()
            inputs, input_tokens = run_one(record)
            start = torch.cuda.Event(enable_timing=True)
            end = torch.cuda.Event(enable_timing=True)
            started_at = time.time()
            start.record()
            try:
                with torch.no_grad():
                    output = model.generate(**inputs, **generation_kwargs)
                end.record()
                torch.cuda.synchronize()
                wall_ms = (time.time() - started_at) * 1000.0
                cuda_ms = start.elapsed_time(end)
                generated = output.sequences[0][input_tokens:]
                label, raw_output = constraint.decode(tokenizer, generated)
                probabilities = constraint.probabilities(output.scores[0][0])
                status = "ok" if label is not None else "constraint_error"
                if label is None:
                    errors.append({"event_id": record["event_id"], "repetition": repetition, "error": "decode violation"})
                measurements.append(
                    {
                        "event_id": record["event_id"], "repetition": repetition, "status": status,
                        "input_length_tercile": record["input_length_tercile"],
                        "selection_role": record["selection_role"],
                        "profiling_prompt_sha256": record["profiling_prompt_sha256"],
                        "input_tokens": input_tokens, "output_tokens": int(generated.shape[0]),
                        "raw_output": raw_output, "label": label,
                        "constrained_label_probabilities": probabilities,
                        "risk_score": round(float(probabilities["1"] + probabilities["2"]), 8),
                        "wall_ms": round(wall_ms, 4), "cuda_ms": round(cuda_ms, 4),
                        "peak_vram_mb": round(torch.cuda.max_memory_allocated() / (1024 * 1024), 2),
                        "gpu_interference": abs(wall_ms - cuda_ms) / max(wall_ms, 0.001) > 0.10,
                    }
                )
            except torch.cuda.OutOfMemoryError:
                torch.cuda.empty_cache()
                errors.append({"event_id": record["event_id"], "repetition": repetition, "error": "OOM"})
                measurements.append({"event_id": record["event_id"], "repetition": repetition, "status": "oom", "input_length_tercile": record["input_length_tercile"], "selection_role": record["selection_role"], "input_tokens": input_tokens, "output_tokens": 0, "label": None, "wall_ms": 0.0, "cuda_ms": 0.0, "peak_vram_mb": 0.0})
            except Exception as exc:
                errors.append({"event_id": record["event_id"], "repetition": repetition, "error": str(exc)})
                measurements.append({"event_id": record["event_id"], "repetition": repetition, "status": "runtime_error", "input_length_tercile": record["input_length_tercile"], "selection_role": record["selection_role"], "input_tokens": input_tokens, "output_tokens": 0, "label": None, "wall_ms": 0.0, "cuda_ms": 0.0, "peak_vram_mb": 0.0})
        if input_index % 20 == 0 or input_index == len(order):
            print(f"{tier}: profiled {input_index}/{len(order)}")
    del model
    del tokenizer
    torch.cuda.empty_cache()
    ok = [row for row in measurements if row["status"] == "ok"]
    expected = len(records) * REPETITIONS
    interference = sum(bool(row.get("gpu_interference")) for row in ok)
    per_length = {
        length: latency_summary([row for row in ok if row["input_length_tercile"] == length])
        for length in ("short", "medium", "long")
    }
    summary: dict[str, Any] = {
        "tier": tier, "model_id": spec["model_id"], "revision": spec["revision"], "dtype": "bfloat16",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "selection_contract_version": SELECTION_CONTRACT_VERSION,
        "selection_sha256": selection["selection_sha256"],
        "code": {"git_revision": git_revision(), "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        "stratification": selection["stratification"],
        "gpu": {
            "name": torch.cuda.get_device_name(0),
            "memory_total_mb": torch.cuda.get_device_properties(0).total_memory // (1024 * 1024),
            "cuda_version": torch.version.cuda, "torch_version": torch.__version__,
            "transformers_version": transformers.__version__, "driver_version": driver_version(),
            "tokenizer_revision": spec["revision"],
        },
        "policy_sha256": policy_sha256, "template_sha256": template_sha256,
        "decoding_constraint": constraint.metadata, "load": load_summary,
        "profiling": {
            "warmup_count": WARMUP_COUNT, "inputs": len(records), "repetitions": REPETITIONS,
            "total_expected": expected, "total_ok": len(ok),
            "oom_count": sum(row["status"] == "oom" for row in measurements),
            "constraint_error_count": sum(row["status"] == "constraint_error" for row in measurements),
            "runtime_error_count": sum(row["status"] == "runtime_error" for row in measurements),
            "completion_rate": round(len(ok) / max(expected, 1), 4),
            "gpu_interference_count": interference,
            "gpu_interference_rate": round(interference / max(len(ok), 1), 4),
        },
        "latency": latency_summary(ok), "latency_by_input_length_tercile": per_length,
        "errors": errors[:20], "error_count": len(errors),
    }
    stats = summary["profiling"]
    summary["passed"] = (
        stats["total_ok"] == expected and stats["oom_count"] == 0
        and stats["constraint_error_count"] == 0 and stats["runtime_error_count"] == 0
        and stats["gpu_interference_rate"] <= MAX_GPU_INTERFERENCE_RATE
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in measurements:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary_path = output_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(measurements)} measurements to {output_path}")
    print(f"Summary written to {summary_path}; passed={summary['passed']}")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", choices=sorted(MODEL_SPECS), required=True)
    parser.add_argument(
        "--selection", type=Path, default=Path("data/processed/g3r1-profiling-selection.v1.json")
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=20260730)
    args = parser.parse_args()
    output = args.output or Path(f"artifact/cloud-gpu/profiling-{args.tier}.g3r1.jsonl")
    result = run_profiling_tier(args.tier, args.selection, output, args.seed)
    if result.get("error"):
        print(f"ERROR: {result['error']}", file=sys.stderr)
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
