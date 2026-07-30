# G2 Verifier Profiling Runbook

状态：`cloud_profile_pending`  
作用：只冻结 4090D profiling 的执行语义，不产生或预填任何延迟结果。

## 冻结候选

| Tier | Model | Revision | Precision | Mode |
| --- | --- | --- | --- | --- |
| Light | `Qwen/Qwen3-1.7B` | `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e` | BF16 | non-thinking |
| Strong | `Qwen/Qwen3-8B` | `b968826d9c46dd6066d109eabc6255188de91218` | BF16 | non-thinking |

两个模型均为 Apache-2.0。它们分别单独加载、单独 profiling；不要求在 24 GB 显存中同时常驻。主重放只读取缓存的验证输出和实测服务时间。

## 固定输入与解码

- Prompt：`experiments/prompts/verifier-v1.txt`，运行前核对 SHA-256。
- 输入上限：4,096 tokens；超限事件记为 `abstain/input_overflow`，不得截断关键策略或动作字段。
- 输出只能为单个标签 token：`0`、`1` 或 `2`。
- `enable_thinking=false`、`do_sample=false`、batch size 1、最多 4 个生成 token。
- 风险分数为约束标签集合上的归一化概率：`P(1) + P(2)`。
- 运行时、CUDA、驱动、PyTorch、Transformers、tokenizer revision 和 GPU 型号全部写入 provenance。

### 输入冻结前置条件

当前 prompt 仍是字段模板，尚无 owner 签核的 `policy_text` 与 source-to-prompt materializer。详细接口见 `docs/g2-profiling-input-contract.md`。因此云端可先做环境 preflight 与模型 smoke test，但不得用临时或手工拼接的 prompt 进行有效 profiling。

## 测量顺序

1. 每层单独启动新进程并记录模型加载峰值显存；
2. 运行 10 个不计入统计的 warm-up job；
3. 仅在输入 contract 关闭后，从固定事件清单中按来源、输入长度三分位、`hard_required`（含校准专用 `N/A`）和安全标签抽取 128 个动作；安全标签只用于离线分层，绝不写入 verifier 输入；
4. 每个动作随机顺序重复 3 次，固定 profiling seed；
5. 每次记录 wall-clock service time、CUDA event time、输入/输出 token、峰值显存、OOM、解析错误和标签；
6. 层间释放模型并清空进程，不把模型交换时间计入单 job 服务时间；
7. 主重放按“tier × 输入长度三分位”进行经验重采样，所有方法共享同一服务时间样本。

## 有效性门

- 两层均能完成全部 128 × 3 次测量；
- OOM 为 0；标签解析失败率为 0；
- 每层至少 95% 测量不受后台 GPU 任务影响；
- 记录 p50、p95、p99，但当前文件全部保持 `TBD`；
- 任一门失败：保持 `G2_conditional`，缩短输入或更换模型后重新冻结，不静默改配置。

## 已确认的超时规则

项目 owner 已于 2026-07-30 确认：

`maximum_wait_ms = ceil(max(5000, 4 × measured_strong_p95_ms))`

风险预算 `epsilon=0.02` 也已确认。真实 Strong p95 仍未知，因此不得预填 `maximum_wait_ms` 数值。云端执行顺序和回传工件见 `docs/cloud-gpu-execution-checklist.md`。

No experimental result has been generated here.
