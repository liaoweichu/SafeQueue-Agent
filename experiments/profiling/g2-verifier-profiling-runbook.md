# G2 Verifier Profiling Runbook (v3)

状态：`cloud_reprofile_complete_v3_audit_passed`
作用：冻结 v3 的输入、解码和测量语义，并索引已审计的 latency 工件；本文件不预填主重放结果。

## 冻结候选

| Tier | Model | Revision | Precision | Mode |
| --- | --- | --- | --- | --- |
| Light | `Qwen/Qwen3-1.7B` | `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e` | BF16 | non-thinking |
| Strong | `Qwen/Qwen3-8B` | `b968826d9c46dd6066d109eabc6255188de91218` | BF16 | non-thinking |

两个模型必须在独立进程中顺序加载；不可同时驻留，也不可把模型加载时间计入单 job 服务时间。

## 固定输入与解码

- Prompt 由 `src/verifier_prompting.py` 以 `policy-v1.txt`、`verifier-v1.txt` 和 materialized fields 渲染，再应用 Qwen 的 non-thinking chat template；
- 输入上限为 4,096 token。任何 hash、token 数或模板版本不匹配都必须在加载模型前失败；
- `SingleTokenLabelConstraint` 在唯一生成步对 logits mask，只允许 tokenizer 中精确表示 `0`、`1`、`2` 的三个 token；
- `enable_thinking=false`、`do_sample=false`、batch size 1、`max_new_tokens=1`；
- 记录受约束 logits 上的 `P(0)`、`P(1)`、`P(2)` 与 `P(1)+P(2)`；这是后续 replay 的风险分数语义；
- CUDA、驱动、PyTorch、Transformers、tokenizer revision、GPU 型号、selection hash 与 constraint hash 必须写入 summary。

## v3 选择契约

`scripts/stratify_and_audit_g2_prompts.py` 只接受 `g2-profiling-v3`：

| 层 | 唯一输入数 | 语义 |
| --- | ---: | --- |
| short | 43 | 完整 chat prompt token 三分位 |
| medium | 43 | 完整 chat prompt token 三分位 |
| long | 42 | 完整 chat prompt token 三分位 |
| SafeToolBench | 32 | `calibration_latency_only`；不进入评估或阈值拟合 |
| τ-bench hard | ≥32 | evaluation action；其余 τ-bench 输入填满至 96 条 |

选择器先对所有 model-visible fields 做泄漏与 hash 审计，再以完整 prompt 的实际 tokenizer token 计算边界；不得使用字段词数近似。AgentDojo 仍不进入有效 latency profiling，因为固定快照没有调用前实际 action。

## 测量顺序

1. 在同一 4090D 云机运行 v3 preflight；
2. 生成 selection v3 并保存其 SHA-256；
3. 对每个 tier 运行受约束解码 smoke test；
4. 每 tier 运行 10 个不计统计的 warm-up；
5. 每个选中 action 按固定 seed 随机顺序测量 3 次；
6. 记录 wall/CUDA time、输入/输出 token、峰值显存、单 token label、约束概率、risk score、OOM、runtime/constraint error 与 GPU 干扰；
7. 层间退出进程并释放模型；
8. 回传 raw JSONL、summary、selection、preflight 与 smoke JSON，在本地运行独立审计器。

## 有效性门

- 两 tier 均为 128 个唯一输入 × 3，且每个 length bin 有 43/43/42 个唯一 prompt；
- 每个 raw output 恰为一个允许 token，概率在允许标签集内归一化；
- OOM、runtime error、constraint error 均为 0；
- 至少 95% 测量不受 GPU 干扰；
- summary 的 p50/p95/p99 与 raw JSONL 可重算一致；
- `scripts/audit_g2_profiling_artifacts.py` 必须通过。

已完成结果：同一 RTX 4090D、代码 `df66c25` 上 Light/Strong 各 384 条有效测量，零 OOM/runtime/constraint error；wall p95 分别为 37.68 / 140.01 ms。详见 `artifact/cloud-gpu/g2-v3-audit.json`。

任一后续复跑失败时不得以旧 v2 服务时间或临时 prompt 作为替代；应重新回到编排器审核。
