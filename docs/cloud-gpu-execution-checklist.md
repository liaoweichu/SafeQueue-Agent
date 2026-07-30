# SafeQueue G2 v3 云端重跑清单

状态：`completed_v3_audit_passed_2026-07-30`
执行范围已完成：v3 preflight、受约束解码 smoke test、两个 tier 的真实 `128 × 3` latency profiling 与工件审计。该完成不授权五方法主重放、训练、线上部署、结果表或论文结论。

## 0. 不变条件

- 同一台云机：`NVIDIA GeForce RTX 4090 D`、至少 23.5 GiB VRAM、BF16；
- 同一份固定数据压缩包、policy-v1、verifier-v1 与模型 revision；
- 只在仓库根目录运行；不要覆盖或删除旧 v2 工件，v3 使用独立文件名；
- 任意命令非零退出即停止，保留 stdout/stderr 和已生成工件，不启动 G3。

## 1. 更新代码并确认环境

```bash
git pull --ff-only
git rev-parse HEAD
git status --short
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
python -c "import torch, transformers; print(torch.__version__, torch.version.cuda, torch.cuda.get_device_name(0), torch.cuda.is_bf16_supported(), transformers.__version__)"
```

如果最后两行不是 4090D、CUDA 可用和 BF16 可用，停止并回传输出。

## 2. 生成 v3 预检与选择集

```bash
python scripts/g2_cloud_preflight.py --output artifact/cloud-gpu/preflight.v3.json
python scripts/stratify_and_audit_g2_prompts.py \
  --output data/processed/g2-profiling-selection.v3.json \
  --n-profiling 128 \
  --length-quotas 43,43,42 \
  --safetoolbench-quota 32 \
  --tau-hard-minimum 32 \
  --seed 20260730
```

第二条命令必须报告 `FIELD / PROVENANCE AUDIT: PASS` 和 `QUOTA AUDIT: PASS`。保存 selection SHA-256；不要改写为 v2 的 `g2-profiling-selection.json`。

## 3. 验证受约束解码

```bash
python scripts/g2_smoke_test.py \
  --tier both \
  --output artifact/cloud-gpu/smoke-test-results.v3.json
```

两个 tier 都必须通过，且每个 case 的输出为单个 `0`、`1` 或 `2` token；JSON 中必须包含 `decoding_constraint.version = single_token_label_logits_mask_v1`。

## 4. 两档真实 profiling

依次运行，模型不会同时驻留：

```bash
python scripts/g2_profiling_runner.py \
  --tier light \
  --selection data/processed/g2-profiling-selection.v3.json \
  --output artifact/cloud-gpu/profiling-light.v3.jsonl \
  --seed 20260730
```

```bash
python scripts/g2_profiling_runner.py \
  --tier strong \
  --selection data/processed/g2-profiling-selection.v3.json \
  --output artifact/cloud-gpu/profiling-strong.v3.jsonl \
  --seed 20260730
```

每档预期为 384 行：43/43/42 个唯一 prompt × 3。runner 会拒绝旧 v2 selection、prompt/hash/token 不匹配、无约束输出或超限输入。

## 5. 云端独立审计与回传

```bash
python scripts/audit_g2_profiling_artifacts.py \
  --selection data/processed/g2-profiling-selection.v3.json \
  --preflight artifact/cloud-gpu/preflight.v3.json \
  --smoke artifact/cloud-gpu/smoke-test-results.v3.json \
  --light artifact/cloud-gpu/profiling-light.v3.jsonl \
  --strong artifact/cloud-gpu/profiling-strong.v3.jsonl \
  --output artifact/cloud-gpu/g2-v3-audit.json
```

只有 JSON 顶层为 `"passed": true` 且 `derived_maximum_wait_ms: 5000` 时，回传以下新增文件：

```text
data/processed/g2-profiling-selection.v3.json
artifact/cloud-gpu/preflight.v3.json
artifact/cloud-gpu/smoke-test-results.v3.json
artifact/cloud-gpu/profiling-light.v3.jsonl
artifact/cloud-gpu/profiling-light.v3.summary.json
artifact/cloud-gpu/profiling-strong.v3.jsonl
artifact/cloud-gpu/profiling-strong.v3.summary.json
artifact/cloud-gpu/g2-v3-audit.json
```

回传的八个 v3 工件已通过独立审计：`passed: true`、`derived_maximum_wait_ms: 5000`。因此 `ccfa.yaml` 已升为 `G2_frozen`；任何重新执行本清单的变体都须使用新的版本化文件名并再次过 Gate。
