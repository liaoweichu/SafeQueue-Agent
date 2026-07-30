# G2 Freeze Readiness

更新日期：2026-07-30  
当前 Gate：`G2_frozen`  
判定：`frozen — v2 reprofiling complete, all blockers closed`

## 摘要

| 修复项 | 变更 |
|---|---|
| stratify 脚本 | 真实 Qwen3 tokenizer, 精确 128 条, 排除重复 prompt, SafeToolBench 校准层独立记录 |
| AgentDojo materializer | 禁止 target_functions 输入泄漏, 300 事件标记 eligible_for_profiling=false |
| profiling runner | 强制 0/1/2 标签, Driver/Transformers/tokenizer revision/selection hash 等完整 provenance, GPU 干扰监测 |

## Profiling 结果 (v2)

| 指标 | Light (1.7B) | Strong (8B) |
|---|---|---|
| 测量 | 384/384 | 384/384 |
| OOM | 0 | 0 |
| Parse failures | 0 | 0 (strict 0/1/2 enforcement) |
| GPU interference | 0/384 (0.0%) | 0/384 (0.0%) |
| Wall p50 | 54.16ms | 148.85ms |
| Wall p95 | 55.26ms | 151.98ms |
| Wall p99 | 57.90ms | 160.63ms |
| AgentDojo events | 0 (correctly excluded) | 0 (correctly excluded) |

## 冻结参数

- `epsilon = 0.02`
- `maximum_wait_ms = ceil(max(5000, 4 × 151.98)) = 5000ms`
- GPU: NVIDIA GeForce RTX 4090 D, 24 GiB, Driver 550.120, CUDA 12.4
- PyTorch 2.5.1+cu124, Transformers 5.14.1, BF16
- Selection SHA-256: `e7e637a5a7d8f1052941e287f3503b885b7f026a7e6d6a6f88e92a5196104bc7`

## 全部签核项

- policy-v1.txt + materializers: owner_signed
- hard-capability registry pre-audit: owner_signed
- AgentDojo envelope review: owner_signed
- SafeToolBench 150/150 label review: owner_signed
- Cloud GPU profiling: RTX 4090D, 384/384×2 tiers, all gates passed

Gate 已升级为 `G2_frozen`，可进入 G3 MVE 实现。
