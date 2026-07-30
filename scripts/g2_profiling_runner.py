#!/usr/bin/env python3
"""Run the protocol-locked G2 v3 verifier latency profile on one GPU tier.

Each selected prompt is rendered through the frozen Qwen chat template and
decoded with a logits mask that permits exactly one token: ``0``, ``1``, or
``2``.  The first-step logits are retained to record the constrained-label
probabilities used by the later replay, so timing and risk-score semantics do
not drift apart.
"""

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

import torch
import transformers
from transformers import AutoModelForCausalLM, AutoTokenizer

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.verifier_prompting import render_chat_prompt, sha256_text
from src.verifier_runtime import SingleTokenLabelConstraint


MODELS = {
    "light": {
        "model_id": "Qwen/Qwen3-1.7B",
        "revision": "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e",
        "dtype": torch.bfloat16,
        "label": "Light (Qwen3-1.7B)",
    },
    "strong": {
        "model_id": "Qwen/Qwen3-8B",
        "revision": "b968826d9c46dd6066d109eabc6255188de91218",
        "dtype": torch.bfloat16,
        "label": "Strong (Qwen3-8B)",
    },
}

SELECTION_CONTRACT_VERSION = "g2-profiling-v3"
MAX_INPUT_TOKENS = 4096
MAX_NEW_TOKENS = 1
WARMUP_COUNT = 10
REPETITIONS = 3
MAX_GPU_INTERFERENCE_RATE = 0.05


def get_peak_vram_mb() -> float:
    return torch.cuda.max_memory_allocated() / (1024 * 1024)


def reset_peak_vram() -> None:
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.synchronize()


def percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    index = (len(sorted_values) - 1) * p / 100
    lower = int(index)
    fraction = index - lower
    if lower + 1 < len(sorted_values):
        return sorted_values[lower] + fraction * (sorted_values[lower + 1] - sorted_values[lower])
    return sorted_values[lower]


def latency_summary(measurements: list[dict[str, Any]]) -> dict[str, float | int]:
    wall_times = sorted(measurement["wall_ms"] for measurement in measurements)
    cuda_times = sorted(measurement["cuda_ms"] for measurement in measurements)
    return {
        "wall_p50_ms": round(percentile(wall_times, 50), 2),
        "wall_p95_ms": round(percentile(wall_times, 95), 2),
        "wall_p99_ms": round(percentile(wall_times, 99), 2),
        "cuda_p50_ms": round(percentile(cuda_times, 50), 2),
        "cuda_p95_ms": round(percentile(cuda_times, 95), 2),
        "cuda_p99_ms": round(percentile(cuda_times, 99), 2),
        "n_samples": len(measurements),
    }


def driver_version() -> str:
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True,
            check=True,
            text=True,
        )
        return completed.stdout.strip().splitlines()[0].strip()
    except Exception:
        return ""


def git_revision() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, check=True, text=True
        ).stdout.strip()
    except Exception:
        return ""


def validate_selection(selection: dict[str, Any]) -> list[str]:
    """Reject legacy or quota-invalid selections before a GPU model is loaded."""
    errors: list[str] = []
    if selection.get("selection_contract_version") != SELECTION_CONTRACT_VERSION:
        errors.append(
            f"selection_contract_version must be {SELECTION_CONTRACT_VERSION!r}; "
            "v2 selections are intentionally not profileable"
        )
    records = selection.get("records", [])
    if selection.get("n_profiling_actions") != 128 or len(records) != 128:
        errors.append(f"selection must contain exactly 128 records, found {len(records)}")
    event_ids = [record.get("event_id") for record in records]
    if len(set(event_ids)) != len(event_ids):
        errors.append("selection has duplicate event IDs")
    if any(record.get("eligible_for_profiling") is not True for record in records):
        errors.append("selection contains a record not eligible for profiling")
    required = {
        "profiling_prompt_sha256",
        "profiling_input_tokens",
        "input_length_tercile",
        "selection_role",
    }
    for record in records:
        missing = sorted(required - set(record))
        if missing:
            errors.append(f"{record.get('event_id')}: missing v3 metadata {missing}")
    stratification = selection.get("stratification", {})
    target_lengths = stratification.get("length_quotas", {})
    actual_lengths = Counter(record.get("input_length_tercile") for record in records)
    if target_lengths and any(actual_lengths.get(length, 0) != expected for length, expected in target_lengths.items()):
        errors.append(f"length quota mismatch: actual={dict(actual_lengths)}, target={target_lengths}")
    source_counts = Counter(record.get("source") for record in records)
    if source_counts.get("safetoolbench", 0) != stratification.get("safetoolbench_quota"):
        errors.append("SafeToolBench calibration-latency quota mismatch")
    tau_hard_count = sum(
        record.get("source") == "tau2-bench" and bool(record.get("hard_required"))
        for record in records
    )
    if tau_hard_count < stratification.get("tau_hard_minimum", 0):
        errors.append("τ-bench hard-action minimum is not met")
    if len({record.get("profiling_prompt_sha256") for record in records}) != len(records):
        errors.append("selection has duplicate model-ready prompt hashes")
    return errors


def run_profiling_tier(
    tier: str,
    selection_path: Path,
    output_path: Path,
    profiling_seed: int,
) -> dict[str, Any]:
    """Profile one frozen verifier tier and write raw JSONL plus a summary."""
    if not torch.cuda.is_available():
        return {"tier": tier, "error": "CUDA not available", "passed": False}

    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    selection_errors = validate_selection(selection)
    if selection_errors:
        return {
            "tier": tier,
            "error": "invalid v3 selection: " + "; ".join(selection_errors),
            "passed": False,
        }
    records = selection["records"]
    spec = MODELS[tier]
    policy = Path("experiments/prompts/policy-v1.txt").read_text(encoding="utf-8")
    template = Path("experiments/prompts/verifier-v1.txt").read_text(encoding="utf-8")
    policy_sha256 = sha256_text(policy)
    template_sha256 = hashlib.sha256(template.encode("utf-8")).hexdigest().upper()

    try:
        tokenizer = AutoTokenizer.from_pretrained(spec["model_id"], revision=spec["revision"])
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        constraint = SingleTokenLabelConstraint.from_tokenizer(tokenizer)
    except Exception as exc:
        return {"tier": tier, "error": f"tokenizer/constraint setup failed: {exc}", "passed": False}

    # Validate the exact chat strings and token counts before allocating GPU memory.
    prepared_prompts: dict[str, str] = {}
    input_mismatches: list[str] = []
    for record in records:
        prompt = render_chat_prompt(record, template, policy, tokenizer)
        actual_hash = sha256_text(prompt)
        actual_tokens = len(tokenizer.encode(prompt, add_special_tokens=False))
        prepared_prompts[record["event_id"]] = prompt
        if actual_hash != record["profiling_prompt_sha256"]:
            input_mismatches.append(f"{record['event_id']}: chat prompt hash mismatch")
        if actual_tokens != record["profiling_input_tokens"]:
            input_mismatches.append(
                f"{record['event_id']}: input token mismatch "
                f"({actual_tokens} != {record['profiling_input_tokens']})"
            )
        if actual_tokens > MAX_INPUT_TOKENS:
            input_mismatches.append(f"{record['event_id']}: input exceeds {MAX_INPUT_TOKENS} tokens")
    if input_mismatches:
        return {
            "tier": tier,
            "error": "selection/chat rendering mismatch: " + "; ".join(input_mismatches[:10]),
            "passed": False,
        }

    gpu_info = {
        "name": torch.cuda.get_device_name(0),
        "memory_total_mb": torch.cuda.get_device_properties(0).total_memory // (1024 * 1024),
        "cuda_version": torch.version.cuda,
        "torch_version": torch.__version__,
        "transformers_version": transformers.__version__,
        "driver_version": driver_version(),
        "tokenizer_revision": spec["revision"],
        "selection_sha256": selection["selection_sha256"],
        "policy_sha256": policy_sha256,
        "template_sha256": template_sha256,
    }
    print(
        f"Provenance: GPU={gpu_info['name']}, Driver={gpu_info['driver_version']}, "
        f"CUDA={gpu_info['cuda_version']}, PyTorch={gpu_info['torch_version']}, "
        f"Transformers={gpu_info['transformers_version']}"
    )

    print(f"Loading {spec['label']} (revision={spec['revision']})...")
    reset_peak_vram()
    load_started = time.time()
    try:
        model = AutoModelForCausalLM.from_pretrained(
            spec["model_id"],
            revision=spec["revision"],
            torch_dtype=spec["dtype"],
            device_map="auto",
        )
        model.eval()
    except Exception as exc:
        del tokenizer
        return {"tier": tier, "error": f"model load failed: {exc}", "passed": False}
    load_time_s = time.time() - load_started
    load_peak_vram_mb = get_peak_vram_mb()
    generation_kwargs = {
        "max_new_tokens": MAX_NEW_TOKENS,
        "do_sample": False,
        "pad_token_id": tokenizer.pad_token_id,
        "logits_processor": constraint.logits_processor(),
        "return_dict_in_generate": True,
        "output_scores": True,
    }

    def inputs_for(record: dict[str, Any]) -> tuple[Any, int]:
        inputs = tokenizer(
            prepared_prompts[record["event_id"]],
            add_special_tokens=False,
            return_tensors="pt",
        ).to(model.device)
        return inputs, int(inputs.input_ids.shape[1])

    # Warm up the exact constrained generation path without adding measurements.
    rng = random.Random(profiling_seed)
    try:
        for record in rng.sample(records, WARMUP_COUNT):
            inputs, _ = inputs_for(record)
            with torch.no_grad():
                model.generate(**inputs, **generation_kwargs)
    except Exception as exc:
        del model
        del tokenizer
        torch.cuda.empty_cache()
        return {"tier": tier, "error": f"constrained warm-up failed: {exc}", "passed": False}

    all_measurements: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    order = list(records)
    rng.shuffle(order)
    for input_index, record in enumerate(order, start=1):
        for repetition in range(REPETITIONS):
            reset_peak_vram()
            inputs, input_tokens = inputs_for(record)
            start_event = torch.cuda.Event(enable_timing=True)
            end_event = torch.cuda.Event(enable_timing=True)
            wall_started = time.time()
            start_event.record()
            try:
                with torch.no_grad():
                    outputs = model.generate(**inputs, **generation_kwargs)
            except torch.cuda.OutOfMemoryError:
                errors.append({"event_id": record["event_id"], "repetition": repetition, "error": "OOM"})
                torch.cuda.empty_cache()
                all_measurements.append(
                    {
                        "event_id": record["event_id"],
                        "repetition": repetition,
                        "status": "oom",
                        "input_length_tercile": record["input_length_tercile"],
                        "selection_role": record["selection_role"],
                        "input_tokens": input_tokens,
                        "output_tokens": 0,
                        "label": None,
                        "wall_ms": round((time.time() - wall_started) * 1000, 4),
                        "cuda_ms": 0.0,
                        "peak_vram_mb": round(get_peak_vram_mb(), 2),
                    }
                )
                continue
            except Exception as exc:
                errors.append({"event_id": record["event_id"], "repetition": repetition, "error": str(exc)})
                all_measurements.append(
                    {
                        "event_id": record["event_id"],
                        "repetition": repetition,
                        "status": "runtime_error",
                        "input_length_tercile": record["input_length_tercile"],
                        "selection_role": record["selection_role"],
                        "input_tokens": input_tokens,
                        "output_tokens": 0,
                        "label": None,
                        "wall_ms": round((time.time() - wall_started) * 1000, 4),
                        "cuda_ms": 0.0,
                        "peak_vram_mb": round(get_peak_vram_mb(), 2),
                    }
                )
                continue

            end_event.record()
            torch.cuda.synchronize()
            wall_ms = (time.time() - wall_started) * 1000
            cuda_ms = start_event.elapsed_time(end_event)
            generated = outputs.sequences[0][input_tokens:]
            label, raw_output = constraint.decode(tokenizer, generated)
            probabilities = constraint.probabilities(outputs.scores[0][0])
            gpu_interference = abs(wall_ms - cuda_ms) / max(wall_ms, 0.001) > 0.10
            valid = label is not None
            if not valid:
                errors.append(
                    {
                        "event_id": record["event_id"],
                        "repetition": repetition,
                        "error": f"constraint decode violation: {raw_output!r}",
                    }
                )
            all_measurements.append(
                {
                    "event_id": record["event_id"],
                    "repetition": repetition,
                    "status": "ok" if valid else "constraint_error",
                    "input_length_tercile": record["input_length_tercile"],
                    "selection_role": record["selection_role"],
                    "profiling_prompt_sha256": record["profiling_prompt_sha256"],
                    "input_tokens": input_tokens,
                    "output_tokens": int(generated.shape[0]),
                    "raw_output": raw_output,
                    "label": label,
                    "constrained_label_probabilities": probabilities,
                    "risk_score": round(probabilities["1"] + probabilities["2"], 8),
                    "wall_ms": round(wall_ms, 4),
                    "cuda_ms": round(cuda_ms, 4),
                    "peak_vram_mb": round(get_peak_vram_mb(), 2),
                    "gpu_interference": gpu_interference,
                }
            )
        if input_index % 20 == 0:
            print(f"Progress: {input_index}/{len(order)}")

    del model
    del tokenizer
    torch.cuda.empty_cache()

    ok_measurements = [measurement for measurement in all_measurements if measurement["status"] == "ok"]
    expected_total = len(records) * REPETITIONS
    interference_count = sum(bool(measurement.get("gpu_interference")) for measurement in ok_measurements)
    per_length: dict[str, dict[str, float | int]] = {}
    for length in ("short", "medium", "long"):
        per_length[length] = latency_summary(
            [measurement for measurement in ok_measurements if measurement["input_length_tercile"] == length]
        )
    summary: dict[str, Any] = {
        "tier": tier,
        "model_id": spec["model_id"],
        "revision": spec["revision"],
        "dtype": "bfloat16",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "selection_contract_version": SELECTION_CONTRACT_VERSION,
        "selection_sha256": selection["selection_sha256"],
        "code": {
            "git_revision": git_revision(),
            "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
        "stratification": selection["stratification"],
        "gpu": gpu_info,
        "policy_sha256": policy_sha256,
        "template_sha256": template_sha256,
        "decoding_constraint": constraint.metadata,
        "load": {"time_s": round(load_time_s, 2), "peak_vram_mb": round(load_peak_vram_mb, 2)},
        "profiling": {
            "warmup_count": WARMUP_COUNT,
            "inputs": len(records),
            "repetitions": REPETITIONS,
            "total_expected": expected_total,
            "total_ok": len(ok_measurements),
            "oom_count": sum(measurement["status"] == "oom" for measurement in all_measurements),
            "constraint_error_count": sum(
                measurement["status"] == "constraint_error" for measurement in all_measurements
            ),
            "runtime_error_count": sum(
                measurement["status"] == "runtime_error" for measurement in all_measurements
            ),
            "completion_rate": round(len(ok_measurements) / expected_total, 4),
            "gpu_interference_count": interference_count,
            "gpu_interference_rate": round(interference_count / max(len(ok_measurements), 1), 4),
        },
        "latency": latency_summary(ok_measurements),
        "latency_by_input_length_tercile": per_length,
        "errors": errors[:20],
        "error_count": len(errors),
    }
    profiling = summary["profiling"]
    summary["passed"] = (
        profiling["total_ok"] == expected_total
        and profiling["oom_count"] == 0
        and profiling["constraint_error_count"] == 0
        and profiling["runtime_error_count"] == 0
        and profiling["gpu_interference_rate"] <= MAX_GPU_INTERFERENCE_RATE
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for measurement in all_measurements:
            handle.write(json.dumps(measurement, ensure_ascii=False) + "\n")
    summary_path = output_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(all_measurements)} measurements to {output_path}")
    print(f"Summary written to {summary_path}")
    print(
        f"Wall p95={summary['latency']['wall_p95_ms']}ms; "
        f"constraint errors={profiling['constraint_error_count']}; "
        f"interference={profiling['gpu_interference_rate'] * 100:.1f}%"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", choices=["light", "strong"], required=True)
    parser.add_argument(
        "--selection",
        type=Path,
        default=Path("data/processed/g2-profiling-selection.v3.json"),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=20260730)
    args = parser.parse_args()
    output = args.output or Path(f"artifact/cloud-gpu/profiling-{args.tier}.v3.jsonl")
    summary = run_profiling_tier(args.tier, args.selection, output, args.seed)
    if summary.get("error"):
        print(f"ERROR: {summary['error']}")
    return 0 if summary.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
