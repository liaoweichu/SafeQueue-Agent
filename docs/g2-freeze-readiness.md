# G2 Freeze Readiness

更新日期：2026-07-30  
当前 Gate：`G2_frozen`
判定：`同一台 RTX 4090D 的 v3 constrained reprofile 已完成；云端回传与本地独立审计均通过。`

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
| 最大等待 | `ceil(max(5000, 4 × 140.01 ms)) = 5000 ms` | v3 audit confirmed |

## v2 工件的处置

v2 的 4090D 预检和两档 384 条原始测量可保留为诊断记录，但 **不能** 用作 G3 的服务时间分布：其 128 条选择中有 123 条落在同一 short/non-hard stratum，medium 与 long 各只有 2 个唯一 prompt。任何 G3 重放不得读取 v2 的 `profiling-*.jsonl` 或 summary。

## G2_frozen 证据（均已完成）

1. 4090D preflight 通过：24,564 MiB、BF16、CUDA 12.4、驱动 550.120；数据、policy、prompt 与事件清单哈希均匹配；
2. selection 为 128 个唯一 prompt：43/43/42；SafeToolBench 32 条 `calibration_latency_only`，τ-bench 96 条，其中 hard 52 条；
3. Light 与 Strong constrained smoke 均通过；每档各有 384 条有效测量、零 OOM/runtime/constraint error、零 GPU-interference 标记；
4. Light/Strong wall p95 分别为 37.68 / 140.01 ms；`g2-v3-audit.json` 的 33 项检查和本地独立复审均为 `passed: true`；
5. 所有工件使用同一代码版本 `df66c25`，并确认 `derived_maximum_wait_ms=5000`。

数值注记：24/768 条序列化的 `risk_score` 因浮点求和显示为最高 1.00000004；概率和的最大误差为 1.12e-7，处于审计的 1e-6 容差内且仅会保守路由。G3 消费这些分数时须将其裁剪到 [0, 1]，但这不改变本次 G2 profiling 的延迟或 fail-closed 语义。

G2 已冻结；五方法主重放、训练、线上部署和论文结论仍需要 G3 的单独授权。
