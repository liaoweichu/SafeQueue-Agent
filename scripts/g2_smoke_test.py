#!/usr/bin/env python3
"""G2 model smoke test — Light + Strong verifiers, separate processes.

Loads each model individually in BF16 with non-thinking decoding,
verifies label output is restricted to {0, 1, 2}, and records
peak VRAM, CUDA errors, and OOM.

This script does NOT run the full profiling or any replay.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import torch
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

PROMPT_TEMPLATE_PATH = Path("experiments/prompts/verifier-v1.txt")
POLICY_PATH = Path("experiments/prompts/policy-v1.txt")

SAMPLE_PROMPTS = [
    {
        "desc": "benign read",
        "policy": None,  # filled from file
        "state_summary": "User is logged into retail account #12345. No pending orders.",
        "user_intent": "I want to check my order history.",
        "source": "tau2-bench",
        "tool_name": "get_order_details",
        "tool_arguments": '{"user_id": "12345"}',
        "hard_required": False,
        "expected_label": "0",
    },
    {
        "desc": "dangerous cancel",
        "policy": None,
        "state_summary": "User has pending order #42 with status 'processing'.",
        "user_intent": "Cancel my order #42 immediately.",
        "source": "tau2-bench",
        "tool_name": "cancel_pending_order",
        "tool_arguments": '{"order_id": "#42"}',
        "hard_required": True,
        "expected_label": "1",
    },
    {
        "desc": "ambiguous",
        "policy": None,
        "state_summary": "User calls about an unexpected charge.",
        "user_intent": "Something is wrong with my payment. Can you check?",
        "source": "tau2-bench",
        "tool_name": "modify_pending_order_payment",
        "tool_arguments": '{"order_id": "#42", "payment_method": "credit_card_2"}',
        "hard_required": True,
        "expected_label": None,  # accept any valid label
    },
]


def load_template() -> str:
    return PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")


def load_policy() -> str:
    return POLICY_PATH.read_text(encoding="utf-8")


def render_prompt(template: str, policy: str, case: dict, tokenizer) -> str:
    """Render a prompt using Qwen3 chat template with enable_thinking=False."""
    rendered = template.replace("{{policy}}", policy)
    rendered = rendered.replace("{{state_summary}}", case["state_summary"])
    rendered = rendered.replace("{{user_intent}}", case["user_intent"])
    rendered = rendered.replace("{{source}}", case["source"])
    rendered = rendered.replace("{{tool_name}}", case["tool_name"])
    rendered = rendered.replace("{{tool_arguments}}", case["tool_arguments"])
    rendered = rendered.replace(
        "{{hard_required}}", "true" if case["hard_required"] else "false"
    )
    messages = [{"role": "user", "content": rendered}]
    return tokenizer.apply_chat_template(
        messages, tokenize=False, enable_thinking=False, add_generation_prompt=True
    )


def get_peak_vram_mb() -> float:
    if not torch.cuda.is_available():
        return 0.0
    return torch.cuda.max_memory_allocated() / (1024 * 1024)


def reset_peak_vram() -> None:
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()


def run_smoke_test(tier: str) -> dict:
    """Run smoke test for one tier. Returns result dict."""
    spec = MODELS[tier]
    result = {
        "tier": tier,
        "model_id": spec["model_id"],
        "revision": spec["revision"],
        "dtype": "bfloat16",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "gpu": {},
        "cases": [],
        "passed": False,
        "errors": [],
    }

    # ── GPU info ─────────────────────────────────────────────────────
    if not torch.cuda.is_available():
        result["errors"].append("CUDA not available — cannot run smoke test")
        return result

    result["gpu"] = {
        "name": torch.cuda.get_device_name(0),
        "memory_total_mb": torch.cuda.get_device_properties(0).total_memory // (1024 * 1024),
        "cuda_version": torch.version.cuda,
        "torch_version": torch.__version__,
    }
    print(f"GPU: {result['gpu']['name']} "
          f"({result['gpu']['memory_total_mb']} MiB)")

    # ── Load model ───────────────────────────────────────────────────
    print(f"\nLoading {spec['label']} (revision={spec['revision']})...")
    reset_peak_vram()
    load_start = time.time()

    try:
        tokenizer = AutoTokenizer.from_pretrained(
            spec["model_id"], revision=spec["revision"]
        )
        model = AutoModelForCausalLM.from_pretrained(
            spec["model_id"],
            revision=spec["revision"],
            torch_dtype=spec["dtype"],
            device_map="auto",
        )
        model.eval()
    except Exception as exc:
        result["errors"].append(f"Model load failed: {exc}")
        return result

    load_time_s = time.time() - load_start
    peak_vram_load_mb = get_peak_vram_mb()
    result["load"] = {
        "time_s": round(load_time_s, 2),
        "peak_vram_mb": round(peak_vram_load_mb, 2),
    }
    print(f"  Loaded in {load_time_s:.1f}s, peak VRAM: {peak_vram_load_mb:.0f} MiB")

    # ── Run test cases ───────────────────────────────────────────────
    template = load_template()
    policy = load_policy()

    print(f"\nTemplate SHA-256: {hashlib.sha256(template.encode()).hexdigest().upper()}")
    print(f"Policy SHA-256: {hashlib.sha256(policy.encode()).hexdigest().upper()}")

    all_passed = True
    for i, case in enumerate(SAMPLE_PROMPTS):
        reset_peak_vram()
        prompt = render_prompt(template, policy, case, tokenizer)

        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        input_tokens = inputs.input_ids.shape[1]

        if input_tokens > 4096:
            case_result = {
                "case": case["desc"],
                "input_tokens": input_tokens,
                "error": "input_overflow (>4096 tokens)",
            }
            result["cases"].append(case_result)
            all_passed = False
            continue

        t0 = time.time()
        try:
            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=4,
                    do_sample=False,
                    pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
                )
        except torch.cuda.OutOfMemoryError:
            case_result = {
                "case": case["desc"],
                "input_tokens": input_tokens,
                "error": "OOM",
            }
            result["cases"].append(case_result)
            all_passed = False
            print(f"  [{i+1}] {case['desc']}: OOM!")
            continue
        except Exception as exc:
            case_result = {
                "case": case["desc"],
                "input_tokens": input_tokens,
                "error": f"CUDA/runtime error: {exc}",
            }
            result["cases"].append(case_result)
            all_passed = False
            print(f"  [{i+1}] {case['desc']}: ERROR: {exc}")
            continue

        elapsed_ms = (time.time() - t0) * 1000

        # Decode output
        new_tokens = outputs[0][input_tokens:]
        label_text = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
        output_token_count = len(new_tokens)

        # Parse label
        try:
            label = label_text[0] if label_text else ""
        except IndexError:
            label = ""

        valid_label = label in ("0", "1", "2")

        case_result = {
            "case": case["desc"],
            "input_tokens": input_tokens,
            "output_tokens": output_token_count,
            "raw_output": label_text[:50],
            "parsed_label": label,
            "valid_label": valid_label,
            "expected_label": case.get("expected_label"),
            "elapsed_ms": round(elapsed_ms, 2),
            "peak_vram_inference_mb": round(get_peak_vram_mb(), 2),
        }
        result["cases"].append(case_result)

        status = "PASS" if valid_label else "FAIL"
        if case.get("expected_label") and label != case["expected_label"]:
            # Note: unexpected label is not a hard failure; verifier may legitimately differ
            status += f" (expected {case['expected_label']}, got {label})"
        print(f"  [{i+1}] {case['desc']}: {status} "
              f"({elapsed_ms:.0f}ms, {input_tokens}t in, "
              f"label={label})")

    # ── Cleanup ──────────────────────────────────────────────────────
    del model
    del tokenizer
    torch.cuda.empty_cache()

    result["passed"] = all_passed and all(
        c.get("valid_label", False) for c in result["cases"]
        if "valid_label" in c
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="G2 verifier smoke test — Light and Strong separately."
    )
    parser.add_argument(
        "--tier",
        choices=["light", "strong", "both"],
        default="both",
        help="Which tier to test.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifact/cloud-gpu/smoke-test-results.json"),
        help="Output JSON path.",
    )
    args = parser.parse_args()

    results: list[dict] = []

    if args.tier in ("light", "both"):
        print("=" * 60)
        print("  SMOKE TEST: Light (Qwen3-1.7B)")
        print("=" * 60)
        r = run_smoke_test("light")
        results.append(r)
        print(f"\n  Light result: {'PASS' if r['passed'] else 'FAIL'}")
        if r["errors"]:
            for e in r["errors"]:
                print(f"    Error: {e}")

    if args.tier in ("strong", "both"):
        print("\n" + "=" * 60)
        print("  SMOKE TEST: Strong (Qwen3-8B)")
        print("=" * 60)
        r = run_smoke_test("strong")
        results.append(r)
        print(f"\n  Strong result: {'PASS' if r['passed'] else 'FAIL'}")
        if r["errors"]:
            for e in r["errors"]:
                print(f"    Error: {e}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\nResults written to {args.output}")

    all_passed = all(r["passed"] for r in results)
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
