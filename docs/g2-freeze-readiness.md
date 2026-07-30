# G2 Freeze Readiness

更新日期：2026-07-30  
当前 Gate：`G2_conditional`
判定：`v3 本地协议已就绪；同一台 RTX 4090D 的真实 reprofile 与回传审计尚未完成。`

## 已确认的冻结决策

| 项目 | 决策 | 状态 |
| --- | --- | --- |
| policy-v1 与三个 source materializer | 使用当前版本与哈希；AgentDojo 无调用前 action 的 300 条不进入 latency profiling | owner-signed |
| hard-capability registry | 采用当前 `strong_or_abstain` 歧义策略 | owner-signed |
| SafeToolBench | 从 150 条校准集固定抽 32 条，角色为 `calibration_latency_only`；不得进入评估或阈值拟合 | frozen v3 |
| τ-bench | 96 条 evaluation action，其中至少 32 条 `hard_required=true` | frozen v3 |
| 长度分层 | 以完整 Qwen non-thinking chat prompt 的实际 token 数分为 short/medium/long，配额固定为 43/43/42 | frozen v3 |
| 解码 | 单步 logits mask，只允许精确单 token `0` / `1` / `2`；风险分数为该集合上的归一化 `P(1)+P(2)` | frozen v3 |
| 风险预算 | `epsilon=0.02` | owner-confirmed |
| 最大等待 | `ceil(max(5000, 4 × measured_strong_p95_ms))`；当前公式值为 `5000 ms`，须由 v3 审计回填确认 | pending cloud audit |

## v2 工件的处置

v2 的 4090D 预检和两档 384 条原始测量可保留为诊断记录，但 **不能** 用作 G3 的服务时间分布：其 128 条选择中有 123 条落在同一 short/non-hard stratum，medium 与 long 各只有 2 个唯一 prompt。任何 G3 重放不得读取 v2 的 `profiling-*.jsonl` 或 summary。

## 解除 G2_conditional 的唯一条件

1. 在同一台满足 4090D、24 GiB、BF16 条件的云机生成 `data/processed/g2-profiling-selection.v3.json`；
2. `preflight.v3.json`、两档受约束解码 smoke test、Light/Strong 各 `128 × 3` 原始 JSONL 与 summary 均回传；
3. 本地执行 `scripts/audit_g2_profiling_artifacts.py` 并得到 `passed: true`；该脚本会核验配额、哈希、3 次重复、单 token 约束、概率归一化、分长度样本数、GPU provenance 与 `maximum_wait_ms=5000`；
4. 将审计 JSON、v3 selection 与两档 summary 链接回本文件，并把 `ccfa.yaml`、配置、runbook、handoff 同步更新为 `G2_frozen`；
5. 在以上四项完成前，禁止五方法主重放、训练、线上部署或结果声明。

云端命令和回传清单见 `docs/cloud-gpu-execution-checklist.md`。
