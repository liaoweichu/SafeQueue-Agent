# G3 云 GPU：双 verifier score-cache 执行清单

本清单只执行已授权的 G3 最小重放准备与一次离线 replay。请在已经通过 G2 v3 audit 的同一 RTX 4090D 云机上运行。它不下载新数据集、不训练、不启动服务。

## 0. 拉取代码并确认冻结输入

```bash
git pull --ff-only
git rev-parse HEAD
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
python -c "import torch, transformers; print(torch.__version__, transformers.__version__, torch.cuda.get_device_name(0))"
python -c "import json; d=json.load(open('data/g2-event-selection.json')); print(len(d['events']), d['selection_sha256'])"
python -c "import json; d=json.load(open('data/processed/g2-profiling-selection.v3.json')); print(d['selection_contract_version'], d['selection_sha256'], d['token_tercile_boundaries'])"
```

停止条件：不是 NVIDIA RTX 4090D、缺失 `data/processed/g2-materialized-records.jsonl`、缺失任一 G2 v3 profile，或事件/selection 哈希与配置不一致。不要改用旧 v2 profile。

## 1. 生成两个 score cache

先运行 Light；完成后释放模型，再运行 Strong。每个命令必须输出 700 行和一个同名 summary。

```bash
python scripts/g3_score_cache_runner.py --tier light --output artifact/cloud-gpu/g3-scores-light.jsonl
python scripts/g3_score_cache_runner.py --tier strong --output artifact/cloud-gpu/g3-scores-strong.jsonl
```

每一档的输入固定为：500 tau2 evaluation + 50 tau2 calibration + 150 SafeToolBench calibration。cache 不应包含 AgentDojo、`ground_truth_safety` 或其它 oracle 字段。

停止条件：任一 constrained decode、输入 token 上限、OOM、模型 revision 或 materialized-input 校验错误。失败时不要使用部分 cache 继续 replay。

## 2. 审计 cache 后再运行 replay

```bash
python scripts/audit_g3_score_cache.py --output artifact/cloud-gpu/g3-score-cache-audit.json
python scripts/g3_minimal_replay.py --output experiments/results/g3-tau2-minimal-replay.json
python scripts/audit_g3_replay_artifacts.py --output experiments/results/g3-tau2-minimal-replay-audit.json
```

期望：score-cache audit 为 `passed`；replay audit 为 `passed`；replay 的科学 Gate 显示 `partial_inconclusive` 且 F5 为 `not_evaluable`。后两项不是错误，而是 tau2 evaluation 没有 dangerous action 的明确范围限制。

## 3. 回传与版本化

请回传以下真实工件，不要只回传终端摘要：

```text
artifact/cloud-gpu/g3-scores-light.jsonl
artifact/cloud-gpu/g3-scores-light.summary.json
artifact/cloud-gpu/g3-scores-strong.jsonl
artifact/cloud-gpu/g3-scores-strong.summary.json
artifact/cloud-gpu/g3-score-cache-audit.json
experiments/results/g3-tau2-minimal-replay.json
experiments/results/g3-tau2-minimal-replay-audit.json
```

若这些工件经 owner 检查后需要入库，请显式强制添加被 `.gitignore` 排除的结果文件，并单独提交，保留产生它们的 `git rev-parse HEAD`：

```bash
git add -f artifact/cloud-gpu/g3-scores-light.jsonl artifact/cloud-gpu/g3-scores-light.summary.json artifact/cloud-gpu/g3-scores-strong.jsonl artifact/cloud-gpu/g3-scores-strong.summary.json artifact/cloud-gpu/g3-score-cache-audit.json experiments/results/g3-tau2-minimal-replay.json experiments/results/g3-tau2-minimal-replay-audit.json
git commit -m "Run authorized G3 tau replay pilot"
git push
```

不要因 cache 或 replay 完成而自行修改 `ccfa.yaml` 为 G3 passed；完整 G3 仍被 matched-danger 的缺口阻止。
