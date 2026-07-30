# G3-R1 云 GPU 执行清单

R1 必须在通过 G2 v3 audit 的同一 RTX 4090D 云机上完成一套新的 `128 x 3` service profile，然后才可进行 score cache。原因是 R1 新增了 300 条危险 SafeToolBench evaluation 输入；不得把旧 G2 service sample 静默外推到这个新输入集。全流程不训练、不部署、不执行 benchmark tool。

## 0. 本地 owner 签核后拉取

先完成 `docs/handoffs/04-g3r1-light-abstain-repair.md` 的 300 行 review，在本地运行 signoff 脚本并提交/推送 signed copies。云机执行：

```bash
git pull --ff-only
git rev-parse HEAD
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
python -c "import torch, transformers; print(torch.__version__, transformers.__version__, torch.cuda.get_device_name(0))"
python -c "import json; d=json.load(open('data/g3r1-event-selection.owner-signed.json')); print(d['status'], len(d['events']), d['selection_sha256'])"
python -c "import json; d=json.load(open('experiments/configs/g3r1-serial-abstain-escalation.owner-signed.json')); print(d['status'], d['maximum_wait_ms'])"
```

停止条件：GPU 不是预期 4090D、signed 文件缺失、manifest 不是 `owner_signed`、总事件数不是 1000、或 config 状态不是 `owner_signed_pending_service_profile`。不要用 pending candidate 文件绕过签核。

## 1. 重物化与危险 holdout 审计

云机需要固定 tau2 与 SafeToolBench archive（不需要 AgentDojo）：

```bash
python scripts/materialize_g2_prompts.py \
  --manifest data/g3r1-event-selection.owner-signed.json \
  --output data/processed/g3r1-materialized-records.jsonl \
  --output-summary data/processed/g3r1-materialization-summary.json

python scripts/stratify_and_audit_g2_prompts.py \
  --records data/processed/g3r1-materialized-records.jsonl \
  --manifest data/g3r1-event-selection.owner-signed.json \
  --audit-only

python scripts/audit_g3r1_dangerous_holdout.py \
  --manifest data/g3r1-event-selection.owner-signed.json \
  --output artifact/cloud-gpu/g3r1-dangerous-holdout-audit.json
```

预期：1000 条成功物化（550 tau2、450 SafeToolBench），字段审计 `PASS`，dangerous-holdout audit 为 `passed`。任一 source error、hash 不匹配或泄漏都停止；不要继续使用部分 records。

## 2. 新建并冻结 R1 的 128 x 3 service profile

这一步先用固定 tokenizer 选择 128 个唯一 evaluation prompts，再对每个 verifier 测量 3 次。选择预先固定为 short/medium/long=`43/43/42`、tau2=80、SafeToolBench dangerous=48、tau2 hard≥24；calibration 输入不进入 latency sample。

```bash
python scripts/build_g3r1_profiling_selection.py \
  --manifest data/g3r1-event-selection.owner-signed.json \
  --records data/processed/g3r1-materialized-records.jsonl \
  --output data/processed/g3r1-profiling-selection.v1.json

python scripts/g3r1_profiling_runner.py --tier light \
  --selection data/processed/g3r1-profiling-selection.v1.json \
  --output artifact/cloud-gpu/profiling-light.g3r1.jsonl

python scripts/g3r1_profiling_runner.py --tier strong \
  --selection data/processed/g3r1-profiling-selection.v1.json \
  --output artifact/cloud-gpu/profiling-strong.g3r1.jsonl

python scripts/audit_g3r1_profiling_artifacts.py \
  --selection data/processed/g3r1-profiling-selection.v1.json \
  --output artifact/cloud-gpu/g3r1-profiling-audit.json

python scripts/freeze_g3r1_service_profile.py \
  --config experiments/configs/g3r1-serial-abstain-escalation.owner-signed.json \
  --output experiments/configs/g3r1-serial-abstain-escalation.owner-signed.profile-frozen.json
```

停止条件：selection 不是 128 条唯一输入、任一 length/source/hard quota 失败、任一 tier 不是 384 条成功 constrained 输出、OOM、decode 错误、GPU interference 超阈值、或 profile audit 不是 `passed`。freeze 脚本只接受 passed audit，并把 service-profile hash 写入新 config。

## 3. 生成两份 score cache

只使用 profile-frozen config；每个 tier 应恰好产生 1000 行：

```bash
python scripts/g3r1_score_cache_runner.py --tier light \
  --config experiments/configs/g3r1-serial-abstain-escalation.owner-signed.profile-frozen.json \
  --output artifact/cloud-gpu/g3r1-scores-light.jsonl

python scripts/g3r1_score_cache_runner.py --tier strong \
  --config experiments/configs/g3r1-serial-abstain-escalation.owner-signed.profile-frozen.json \
  --output artifact/cloud-gpu/g3r1-scores-strong.jsonl
```

停止条件：模型 revision 不符、constrained decode 失败、单条输入超过 4096 tokens、materialized-record hash 失败或输出不是 1000 行。不要将 benchmark label / `ground_truth_safety` 写入 score cache。

## 4. 审计、重放、再审计

```bash
python scripts/audit_g3r1_score_cache.py \
  --config experiments/configs/g3r1-serial-abstain-escalation.owner-signed.profile-frozen.json \
  --output artifact/cloud-gpu/g3r1-score-cache-audit.json

python scripts/g3r1_repair_replay.py \
  --config experiments/configs/g3r1-serial-abstain-escalation.owner-signed.profile-frozen.json \
  --output experiments/results/g3r1-serial-abstain-escalation-replay.json

python scripts/audit_g3r1_replay_artifacts.py \
  --config experiments/configs/g3r1-serial-abstain-escalation.owner-signed.profile-frozen.json \
  --output experiments/results/g3r1-serial-abstain-escalation-replay-audit.json
```

结构 audit 均应为 `passed`；科学 gate 可以是 `no_go`，这正是最小证伪实验的有效结果。无论 gate 如何，都不得自动修改 `ccfa.yaml` 或启动 G4。

## 5. 回传并版本化真实产物

回传以下文件，而不是只回传终端摘要：

```text
data/processed/g3r1-profiling-selection.v1.json
artifact/cloud-gpu/profiling-light.g3r1.jsonl
artifact/cloud-gpu/profiling-light.g3r1.summary.json
artifact/cloud-gpu/profiling-strong.g3r1.jsonl
artifact/cloud-gpu/profiling-strong.g3r1.summary.json
artifact/cloud-gpu/g3r1-profiling-audit.json
artifact/cloud-gpu/g3r1-dangerous-holdout-audit.json
experiments/configs/g3r1-serial-abstain-escalation.owner-signed.profile-frozen.json
artifact/cloud-gpu/g3r1-scores-light.jsonl
artifact/cloud-gpu/g3r1-scores-light.summary.json
artifact/cloud-gpu/g3r1-scores-strong.jsonl
artifact/cloud-gpu/g3r1-scores-strong.summary.json
artifact/cloud-gpu/g3r1-score-cache-audit.json
experiments/results/g3r1-serial-abstain-escalation-replay.json
experiments/results/g3r1-serial-abstain-escalation-replay-audit.json
```

owner 审阅后，如需入库，显式强制添加被 `.gitignore` 排除的 profile/cache/replay artifact，并单独提交，保留产生它们的 `git rev-parse HEAD`。不要把 R1 的结构 audit 通过解释为原 G3 或完整 SafeQueue 主张通过。
