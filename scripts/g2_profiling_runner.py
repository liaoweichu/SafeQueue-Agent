#!/usr/bin/env python3
"""G2 verifier profiling runner — per-tier, 10 warmup + 128×3 measurements.

Loads one model tier at a time in a fresh process.  Reads the stratified
profiling selection, runs warmup, then measures each input in 3 independent
forward passes (no caching).  Records wall-clock time, CUDA event time,
input/output tokens, peak VRAM, OOM, and parsed label.

Outputs per-measurement JSONL and summary (p50/p95/p99).

Usage:
    python scripts/g2_profiling_runner.py \
        --tier light \
        --selection data/processed/g2-profiling-selection.json \
        --output artifact/cloud-gpu/profiling-light.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

import torch
import transformers
from transformers import AutoModelForCausalLM, AutoTokenizer

# ── Model definitions ──────────────────────────────────────────────────
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

MAX_INPUT_TOKENS = 4096
MAX_NEW_TOKENS = 4
WARMUP_COUNT = 10
REPETITIONS = 3


def get_peak_vram_mb() -> float:
    if not torch.cuda.is_available():
        return 0.0
    return torch.cuda.max_memory_allocated() / (1024 * 1024)


def reset_peak_vram() -> None:
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()


def render_prompt(record: dict, policy: str) -> str:
    """Render a prompt from a materialized record. The record already
    has the full rendered_prompt_sha256, but we reconstruct it from
    fields to ensure consistency."""
    template = record.get("_template", "")
    if not template:
        # Use the fields to reconstruct
        pass
    # Use stored rendered fields directly where possible
    return record.get("rendered_prompt", "")


def run_profiling_tier(
    tier: str,
    selection_path: Path,
    output_path: Path,
    profiling_seed: int,
) -> dict:
    """Run profiling for one tier. Returns summary dict."""
    spec = MODELS[tier]

    if not torch.cuda.is_available():
        return {"tier": tier, "error": "CUDA not available", "passed": False}

    # ── Load selection ──────────────────────────────────────────────
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    records = selection["records"]
    total_inputs = len(records)

    # Filter: only profile eligible records
    eligible_records = [r for r in records if r.get("eligible_for_profiling", True)]
    skipped = len(records) - len(eligible_records)
    if skipped:
        print(f"Skipping {skipped} ineligible records (no call-time action)")
    records = eligible_records
    total_inputs = len(records)
    print(f"Profiling {total_inputs} eligible inputs")

    # ── Load policy and template ─────────────────────────────────────
    policy = Path("experiments/prompts/policy-v1.txt").read_text(encoding="utf-8")
    template = Path("experiments/prompts/verifier-v1.txt").read_text(encoding="utf-8")
    policy_sha256 = hashlib.sha256(policy.encode()).hexdigest()
    template_sha256 = hashlib.sha256(template.encode()).hexdigest().upper()

    # ── GPU provenance ───────────────────────────────────────────────
    driver_version = ""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, check=True
        )
        driver_version = result.stdout.strip().split("\n")[0].strip()
    except Exception:
        pass

    gpu_info = {
        "name": torch.cuda.get_device_name(0),
        "memory_total_mb": torch.cuda.get_device_properties(0).total_memory // (1024 * 1024),
        "cuda_version": torch.version.cuda,
        "torch_version": torch.__version__,
        "transformers_version": transformers.__version__,
        "driver_version": driver_version,
        "tokenizer_revision": spec["revision"],
        "selection_sha256": selection.get("selection_sha256", ""),
        "policy_sha256": policy_sha256,
        "template_sha256": template_sha256,
    }
    print(f"Provenance: GPU={gpu_info['name']}, Driver={driver_version}, "
          f"CUDA={gpu_info['cuda_version']}, PyTorch={gpu_info['torch_version']}, "
          f"Transformers={gpu_info['transformers_version']}")

    # ── Load model ──────────────────────────────────────────────────
    print(f"\nLoading {spec['label']} (revision={spec['revision']})...")
    reset_peak_vram()
    load_start = time.time()

    try:
        tokenizer = AutoTokenizer.from_pretrained(
            spec["model_id"], revision=spec["revision"]
        )
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        model = AutoModelForCausalLM.from_pretrained(
            spec["model_id"],
            revision=spec["revision"],
            torch_dtype=spec["dtype"],
            device_map="auto",
        )
        model.eval()
    except Exception as exc:
        return {"tier": tier, "error": f"Model load failed: {exc}", "passed": False}

    load_time_s = time.time() - load_start
    peak_vram_load_mb = get_peak_vram_mb()
    print(f"  Loaded in {load_time_s:.1f}s, peak VRAM: {peak_vram_load_mb:.0f} MiB")

    # ── Helper: render one prompt ────────────────────────────────────
    def _render(rec: dict) -> str:
        rendered = template.replace("{{policy}}", policy)
        rendered = rendered.replace("{{state_summary}}", rec.get("state_summary", ""))
        rendered = rendered.replace("{{user_intent}}", rec.get("user_intent", ""))
        rendered = rendered.replace("{{source}}", rec.get("source", ""))
        rendered = rendered.replace("{{tool_name}}", rec.get("tool_name", ""))
        rendered = rendered.replace("{{tool_arguments}}", rec.get("tool_arguments", ""))
        rendered = rendered.replace(
            "{{hard_required}}", "true" if rec.get("hard_required") else "false"
        )
        messages = [{"role": "user", "content": rendered}]
        return tokenizer.apply_chat_template(
            messages, tokenize=False, enable_thinking=False, add_generation_prompt=True
        )

    # ── Warmup ───────────────────────────────────────────────────────
    print(f"\nRunning {WARMUP_COUNT} warmup passes...")
    random.seed(profiling_seed)
    warmup_records = random.sample(records, min(WARMUP_COUNT, len(records)))
    for i, rec in enumerate(warmup_records):
        prompt = _render(rec)
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            model.generate(
                **inputs,
                max_new_tokens=MAX_NEW_TOKENS,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
            )
        if (i + 1) % 5 == 0:
            print(f"  Warmup {i+1}/{WARMUP_COUNT}")
    print("  Warmup complete")

    # ── Profiling measurements ───────────────────────────────────────
    print(f"\nProfiling {total_inputs} inputs × {REPETITIONS} repetitions...")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    all_measurements: list[dict] = []
    errors: list[dict] = []
    oom_count = 0
    parse_failures = 0

    # Shuffle order (fixed seed)
    rng = random.Random(profiling_seed)
    indices = list(range(total_inputs))
    rng.shuffle(indices)

    for idx, input_idx in enumerate(indices):
        rec = records[input_idx]

        for rep in range(REPETITIONS):
            reset_peak_vram()
            torch.cuda.synchronize()

            prompt = _render(rec)
            inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
            input_tokens = int(inputs.input_ids.shape[1])

            if input_tokens > MAX_INPUT_TOKENS:
                measurement = {
                    "event_id": rec["event_id"],
                    "repetition": rep,
                    "status": "overflow",
                    "input_tokens": input_tokens,
                    "output_tokens": 0,
                    "label": None,
                    "wall_ms": 0.0,
                    "cuda_ms": 0.0,
                    "peak_vram_mb": 0.0,
                }
                all_measurements.append(measurement)
                continue

            # CUDA event timing
            start_event = torch.cuda.Event(enable_timing=True)
            end_event = torch.cuda.Event(enable_timing=True)

            wall_t0 = time.time()
            start_event.record()
            try:
                with torch.no_grad():
                    outputs = model.generate(
                        **inputs,
                        max_new_tokens=MAX_NEW_TOKENS,
                        do_sample=False,
                        pad_token_id=tokenizer.pad_token_id,
                    )
            except torch.cuda.OutOfMemoryError:
                oom_count += 1
                measurement = {
                    "event_id": rec["event_id"],
                    "repetition": rep,
                    "status": "oom",
                    "input_tokens": input_tokens,
                    "output_tokens": 0,
                    "label": None,
                    "wall_ms": (time.time() - wall_t0) * 1000,
                    "cuda_ms": 0.0,
                    "peak_vram_mb": get_peak_vram_mb(),
                }
                all_measurements.append(measurement)
                errors.append({"event_id": rec["event_id"], "rep": rep, "error": "OOM"})
                torch.cuda.empty_cache()
                continue
            except Exception as exc:
                measurement = {
                    "event_id": rec["event_id"],
                    "repetition": rep,
                    "status": "cuda_error",
                    "error": str(exc),
                    "input_tokens": input_tokens,
                    "output_tokens": 0,
                    "label": None,
                    "wall_ms": (time.time() - wall_t0) * 1000,
                    "cuda_ms": 0.0,
                    "peak_vram_mb": get_peak_vram_mb(),
                }
                all_measurements.append(measurement)
                errors.append(
                    {"event_id": rec["event_id"], "rep": rep, "error": str(exc)}
                )
                continue

            end_event.record()
            torch.cuda.synchronize()
            wall_ms = (time.time() - wall_t0) * 1000
            cuda_ms = start_event.elapsed_time(end_event)

            # Decode label — STRICT: only 0, 1, or 2 accepted
            new_tokens = outputs[0][input_tokens:]
            label_text = tokenizer.decode(
                new_tokens, skip_special_tokens=True
            ).strip()
            output_tokens = int(new_tokens.shape[0])

            # Strict label enforcement: must be exactly 0, 1, or 2
            valid = label_text in ("0", "1", "2")
            if not valid:
                parse_failures += 1
                label = None
            else:
                label = label_text

            # GPU interference check: wall vs cuda diff > 10% indicates background GPU activity
            gpu_interference = (abs(wall_ms - cuda_ms) / max(wall_ms, 0.001)) > 0.10

            measurement = {
                "event_id": rec["event_id"],
                "repetition": rep,
                "status": "ok" if valid else "parse_error",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "raw_output": label_text[:20],
                "label": label,
                "wall_ms": round(wall_ms, 4),
                "cuda_ms": round(cuda_ms, 4),
                "peak_vram_mb": round(get_peak_vram_mb(), 2),
                "gpu_interference": gpu_interference,
            }
            all_measurements.append(measurement)

            if not valid:
                errors.append({
                    "event_id": rec["event_id"],
                    "rep": rep,
                    "error": f"Parse failure: '{label_text[:50]}'",
                })

        if (idx + 1) % 20 == 0:
            print(f"  Progress: {idx+1}/{total_inputs}")

    # ── Cleanup ──────────────────────────────────────────────────────
    del model
    del tokenizer
    torch.cuda.empty_cache()

    # ── Compute statistics ───────────────────────────────────────────
    ok_measurements = [m for m in all_measurements if m["status"] == "ok"]
    wall_times = sorted([m["wall_ms"] for m in ok_measurements])
    cuda_times = sorted([m["cuda_ms"] for m in ok_measurements])

    def percentile(sorted_vals: list[float], p: float) -> float:
        if not sorted_vals:
            return 0.0
        k = (len(sorted_vals) - 1) * p / 100
        f = int(k)
        c = k - f
        if f + 1 < len(sorted_vals):
            return sorted_vals[f] + c * (sorted_vals[f + 1] - sorted_vals[f])
        return sorted_vals[f]

    n_ok = len(ok_measurements)
    n_expected = total_inputs * REPETITIONS
    summary = {
        "tier": tier,
        "model_id": spec["model_id"],
        "revision": spec["revision"],
        "dtype": "bfloat16",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "gpu": gpu_info,
        "policy_sha256": policy_sha256,
        "template_sha256": template_sha256,
        "load": {
            "time_s": round(load_time_s, 2),
            "peak_vram_mb": round(peak_vram_load_mb, 2),
        },
        "profiling": {
            "warmup_count": WARMUP_COUNT,
            "inputs": total_inputs,
            "repetitions": REPETITIONS,
            "total_expected": n_expected,
            "total_ok": n_ok,
            "oom_count": oom_count,
            "parse_failures": parse_failures,
            "completion_rate": round(n_ok / n_expected, 4) if n_expected else 0,
            "gpu_interference_count": sum(1 for m in ok_measurements if m.get("gpu_interference")),
            "gpu_interference_rate": round(
                sum(1 for m in ok_measurements if m.get("gpu_interference")) / max(n_ok, 1), 4
            ),
        },
        "latency": {
            "wall_p50_ms": round(percentile(wall_times, 50), 2),
            "wall_p95_ms": round(percentile(wall_times, 95), 2),
            "wall_p99_ms": round(percentile(wall_times, 99), 2),
            "cuda_p50_ms": round(percentile(cuda_times, 50), 2),
            "cuda_p95_ms": round(percentile(cuda_times, 95), 2),
            "cuda_p99_ms": round(percentile(cuda_times, 99), 2),
            "n_samples": n_ok,
        },
        "errors": errors[:20],  # Truncate for summary
        "error_count": len(errors),
    }

    # Compute passed before writing
    passed = (n_ok == n_expected) and oom_count == 0 and parse_failures == 0
    summary["passed"] = passed

    # Write per-measurement JSONL
    with output_path.open("w", encoding="utf-8") as f:
        for m in all_measurements:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    print(f"\nWrote {len(all_measurements)} measurements to {output_path}")

    # Write summary
    summary_path = output_path.with_suffix(".summary.json")
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Summary written to {summary_path}")

    # Print key metrics
    passed = summary["passed"]
    print(f"\n  Wall:  p50={summary['latency']['wall_p50_ms']}ms  "
          f"p95={summary['latency']['wall_p95_ms']}ms  "
          f"p99={summary['latency']['wall_p99_ms']}ms")
    print(f"  CUDA:  p50={summary['latency']['cuda_p50_ms']}ms  "
          f"p95={summary['latency']['cuda_p95_ms']}ms  "
          f"p99={summary['latency']['cuda_p99_ms']}ms")
    print(f"  OK: {n_ok}/{n_expected}  OOM: {oom_count}  "
          f"Parse failures: {parse_failures}")
    gpu_interference = summary["profiling"]["gpu_interference_count"]
    print(f"  GPU interference: {gpu_interference}/{n_ok} "
          f"({summary['profiling']['gpu_interference_rate']*100:.1f}%)")

    print(f"  Valid: {'PASS' if passed else 'FAIL'} "
          f"(requires 100% completion, 0 OOM, 0 parse failures)")

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="G2 verifier profiling runner — one tier at a time."
    )
    parser.add_argument(
        "--tier",
        choices=["light", "strong"],
        required=True,
        help="Which tier to profile (must be run separately).",
    )
    parser.add_argument(
        "--selection",
        type=Path,
        default=Path("data/processed/g2-profiling-selection.json"),
        help="Path to stratified profiling selection.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSONL path for per-measurement data.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20260730,
    )
    args = parser.parse_args()

    if args.output is None:
        args.output = Path(f"artifact/cloud-gpu/profiling-{args.tier}.jsonl")

    summary = run_profiling_tier(
        tier=args.tier,
        selection_path=args.selection,
        output_path=args.output,
        profiling_seed=args.seed,
    )

    if "error" in summary and summary.get("passed") is False:
        print(f"\nERROR: {summary.get('error', 'Unknown error')}")
        return 1

    return 0 if summary.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
