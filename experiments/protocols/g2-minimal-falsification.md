# G2 Conditional Protocol — Minimal Falsification Experiment

状态：`designed_not_frozen`  
模式：`design / result-template`  
硬件：单张 NVIDIA RTX 4090D，24 GB  
结果状态：`none`

## 1. 协议边界

本协议只回答“是否值得继续实现 SafeQueue”这一投资问题。它不验证完整论文主张，不训练调度策略，不进行在线部署，不扩展第二完整环境，也不生成论文图表或结论。

允许的工作：

- 数据、许可和标签资格检查；
- 轻量/强验证器的 4090D 服务时间 profiling；
- 1,000 条真实来源动作事件的资格检查，其中 200 条仅用于校准、800 条用于离散事件主重放；
- 五个最小方法的同预算比较；
- 使用 `TBD` 的空结果模板。

禁止的工作：

- 完整训练、微调或强化学习；
- RedTeamCUA、Vera-Bench、Phone-Harm 等扩张性环境部署；
- 多 GPU 系统复现；
- 预填收益、显著性或安全结论；
- 论文写作。

## 2. 最小证伪问题

| ID | 待证伪前提 | 最小证据 | 立即停止条件 |
| --- | --- | --- | --- |
| F1 | 强验证器排队是尾延迟的实质瓶颈 | Full-Strong-FIFO 在近饱和或突发负载下的排队分解 | 排队等待不足 action-gate p95 的 20% |
| F2 | 在相同危险动作约束下可以降低尾延迟 | 同 trace、同容量、同硬集合下的配对重放 | SafeQueue-MVE 相对全量强验证的 p95 降幅不足 20% |
| F3 | 联合机制优于简单组合 | Cascade-FIFO、Static-Risk、DRR-Fair 对比 | 任一简单基线在安全与公平匹配时，p95 距 SafeQueue-MVE 不超过 5% |
| F4 | 公平调度不会以小租户饥饿换取总体收益 | 噪声邻居租户混合、最差租户 p95、服务亏欠 | 出现饥饿，或 Jain 指数比 DRR 低超过 0.02 |
| F5 | 校准路由不会越过硬安全边界 | 硬能力审计、未知项回退、危险执行配对计数 | 任一硬动作降级、fail-open，或危险执行多于全量强验证 |

## 3. Claim–Evidence Matrix

| Claim / hypothesis | Reviewer question | Evidence needed | Dataset/workload | Baselines | Metrics | Result placeholder | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 验证器排队构成瓶颈 | 收益是否针对真实瓶颈？ | profiling 与延迟分解 | 800-event held-out replay | Full-Strong-FIFO | queue share, utilization, p95 | TBD | planned |
| 硬集合不可降级 | 学习或风险路由是否绕过必要验证？ | 100% 硬/歧义事件审计 | τ-bench + AgentDojo | 所有方法 | downgrade, fail-open | TBD | planned |
| 联合调度改善尾延迟 | 收益是否只是少验证？ | matched-safety 配对比较 | 三种负载 | 五个方法 | action-gate p95, strong fraction | TBD | planned |
| 多租户公平得到保持 | 是否存在 noisy-neighbor 或小租户饥饿？ | 八租户重放 | heavy-tenant mix | DRR-Fair | Jain, service deficit, worst-tenant p95 | TBD | planned |
| 复杂机制确有必要 | 简单级联或公平队列是否已经足够？ | simple-baseline equivalence check | 相同重放 | Cascade/Static/DRR | paired p95 and safety | TBD | planned |

## 4. 数据资格与固定拆分

### 4.1 来源

- τ-bench `v1.0.1` / `fc0055dc4e0a316c3f83133267fbd6faaa770992`，固定 `retail` 域：50 条良性校准事件、500 条评估事件。静态审计确认该快照共有 114 个 task session、550 个金标动作。
- SafeToolBench `ffdef6e782b0b05f579316003f3b084b549f1366`：仅选择 150 条 `quality_score>=7`、规范化 instruction 去重后的危险/需审批工具计划用于校准，不进入主重放。固定公开压缩包有 1,000 行，而论文报告 1,200 条；该差异必须披露。审计排除 16 条低于质量门的记录和 86 条重复 instruction，剩余 898 条合格候选。
- AgentDojo package `v0.1.35` / `a75aba7631d3ca5fb7ab938965c97ead2f9ff84b`，固定 benchmark `v1.2.2`：原始 831 个兼容安全案例中排除 20 个纯文本输出目标，从 811 个动作可用案例中确定性选择 300 条 held-out 评估事件，不进入校准。
- 总计：1,000 条事件；200 条只用于校准（50 良性 + 150 危险/需审批），主重放和所有 Gate 指标只使用其余 800 条评估事件。

所有事件必须来自固定 commit。τ-bench 按 session 切分；SafeToolBench 只进入校准；AgentDojo 只进入评估。硬路由只能读取运行时可见的来源、域、工具名和参数，禁止读取 benchmark attack label、注入任务 ID 所代表的真值或执行后结果。

选择清单为 `data/g2-event-selection.json`，规范化事件 SHA-256 为 `8afed1ffe3dcd20e930bd914d74329352308c426aacb99d0ef50ba0879cad3fb`。静态审计得到 454 条硬评估事件、300 条危险评估事件，其中 9 条按可观测工具规则属于非硬危险事件；数量门与校准支持门均通过。所选 AgentDojo 案例均具有 literal ground-truth target function 或注册表中的人工 envelope；这些映射仍需人工复核，因此协议尚未冻结。

### 4.2 资格门

在任何验证器运行前完成：

1. 固定两个仓库的 commit 与许可快照；
2. 确认至少 1,000 条事件具有动作语义、环境来源和可审计标签；
3. 确认校准集至少包含 50 条良性事件与 149 条危险/需审批事件；
4. 确认 800 条评估事件中至少 100 条属于危险动作或硬验证集合；
5. 对全部硬/歧义事件人工复核，对非硬事件随机复核 10%；
6. 确认 `hard_required` 不使用 benchmark 真值或执行后结果；
7. 生成数据清单、选择规则和哈希。

任一条件失败即返回 G1，不用补充合成“危险标签”凑数。

## 5. 不可绕过硬集合

硬能力注册表在调度器之外执行，至少覆盖：

1. 不可逆价值转移；
2. 凭据或秘密泄露；
3. 权限或安全控制变更；
4. 破坏性或不可逆数据修改；
5. 有实际后果的外部通信或公开发布。

规则：

- `hard_required=true` 的事件只能进入强验证路径；
- `hard_required` 必须只由调用前可见字段确定，不能因“该样本是注入攻击”而自动置真；
- 未识别或歧义事件必须强验证或 abstain；
- 队列超时只能继续等待或 abstain；
- 所有降级、丢弃和 fail-open 都必须计数，不能从分母移除。

## 6. 验证器 profiling

冻结候选如下：

- Light：`Qwen/Qwen3-1.7B@70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`，BF16；
- Strong：`Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218`，BF16；
- 两层均关闭 thinking、禁用 sampling、batch size 1，输出约束为单标签 `0/1/2`；
- Prompt：`experiments/prompts/verifier-v1.txt`，SHA-256 `BA19ABD9776361BDAC5922D374EDFAA51771374F4C1F8C9BB5B1E674BE8E0F21`；
- 风险分数：约束标签概率中的 `P(BLOCK=1) + P(ABSTAIN=2)`；
- 校准：在 50 条 τ-bench 良性动作与 150 条 SafeToolBench 危险/需审批工具计划上选择最大良性覆盖阈值，使危险 false-allow 的单侧 95% Clopper–Pearson 上界不超过 `epsilon`。

若不存在满足该上界约束的阈值，则该候选配置判为不可行，所有事件退回 Strong 或 abstain；不得为提高覆盖率放宽 `epsilon`。

风险预算候选为 `epsilon=0.02`。在零次危险 false-allow 时，150 条危险校准样本的单侧 95% Clopper–Pearson 上界为 `0.01977344`；149 是跨过 `0.02` 所需的最小样本数，因此 150 是最小整齐配额。出现一次或更多危险 false-allow 即无法满足该候选预算。该界限只约束固定校准集，不是生产或跨分布安全保证。

项目 owner 已于 2026-07-30 确认风险预算 `epsilon=0.02` 与最大等待公式 `ceil(max(5000, 4 × measured_strong_p95_ms))`。在 Strong 的真实 p95 得到前，`maximum_wait_ms` 仍不能写成数值；模型仍需完成与冻结硬件一致的 smoke/profile，因此 G2 仍未冻结。

profiling 计划：

1. 每一验证层先运行 10 个不计入统计的 warm-up job；
2. 选择 128 个动作，按输入长度三分位、硬集合和安全标签分层；
3. 每个动作在每一验证层随机顺序重复 3 次；
4. 记录服务时间、输入/输出 token、峰值显存、OOM 和错误；
5. 重放时按“验证层 × 输入长度三分位”从经验分布配对采样；
6. 所有方法使用相同的服务时间样本。

详细执行语义见 `experiments/profiling/g2-verifier-profiling-runbook.md`。

若任一冻结模型不能在 4090D 上稳定运行，不得静默替换；应回到编排器重新确认验证器预算。

## 7. 重放工作负载

### 7.1 服务模型

- 一个 work-conserving 逻辑验证服务器；
- 轻量和强验证共享该容量；
- 事件内容与安全标签来自公开 benchmark；
- tenant ID 和 arrival time 由固定生成器产生，并明确标记为合成负载元数据。

### 7.2 租户

- 8 个租户，按 session 分配；
- 1 个 noisy-neighbor 租户产生 50% 请求；
- 其余 7 个租户均分剩余 50%；
- 所有租户权重相同。

### 7.3 到达负载

负载 `rho` 以真实 profiling 得到的 Full-Strong 平均服务需求为基准：

| Regime | Process | Parameters |
| --- | --- | --- |
| Low | Poisson | `rho=0.35` |
| Near saturation | Poisson | `rho=0.80` |
| Burst | two-state MMPP | background `rho=0.55`, peak `rho=1.25`, peak duty 20% |

固定到达种子：`20260728`、`20260729`、`20260730`。所有方法共享相同到达时间、租户分配与服务时间样本。

## 8. 五个最小方法

| Method | Routing | Scheduling | 作用 |
| --- | --- | --- | --- |
| Full-Strong-FIFO | 全部强验证 | FIFO | 安全/成本锚点 |
| Calibrated-Cascade-FIFO | 硬动作强验证；非硬动作按校准上界选层 | FIFO | 隔离“少用强验证器”的收益 |
| Static-Risk-Priority | 与 Cascade 相同 | 全局风险上界降序，FIFO tie-break | 隔离静态风险优先 |
| DRR-Fair | 与 Cascade 相同 | 租户 DRR，租户内 FIFO | 隔离公平队列 |
| SafeQueue-MVE | 硬动作强验证；非硬动作按校准上界选层 | 租户虚拟完成时间 → 硬动作优先 → 风险上界降序 → FIFO | 测试最小联合机制 |

不在 G2 复现 SAGA、Justitia、H-MAS 或完整 ToolChain-CRC；这些工作只影响定位和后续基线，不应扩大最小证伪成本。

## 9. 公平比较约束

所有方法必须共享：

- 相同 800 条 held-out 评估事件；
- 相同 calibration/evaluation split；
- 相同 tenant 和 arrival trace；
- 相同经验服务时间样本与单服务器容量；
- 相同硬能力注册表；
- 相同风险分数、`epsilon`、超时和 fail-closed 语义。

禁止：

- 为某方法增加容量；
- 为不同方法选择不同安全阈值；
- 将超时动作从安全或效用分母移除；
- 用 hard-job 降级换取延迟；
- 在看到主结果后修改硬集合、风险预算或停止条件。

## 10. 指标

### Safety

- dangerous-action execution count；
- hard-job downgrade count；
- fail-open count；
- 非硬接受集合的经验风险与置信区间。

### Utility

- benign-action pass rate；
- abstention rate；
- benchmark 原始 task success 仅作描述，不把离线阻断后的反事实恢复冒充真实 task success。

### Systems

- queue wait p50/p95/p99；
- action-gate latency p95；
- throughput、utilization；
- strong-verifier fraction。

### Fairness

- Jain service index；
- worst-tenant p95；
- maximum normalized service deficit；
- starvation count。

## 11. 统计计划

- 使用配对设计和 common random numbers；
- τ-bench 以 session 为 cluster unit；AgentDojo 对 `user_task` 与 `injection_task` 做双向 cluster，不能把同一攻击模板的重复配对当成独立样本；
- 三个到达种子分别报告，不只报告合并均值；
- session-level paired bootstrap，2,000 次，95% 置信区间；
- 危险动作、降级、fail-open 同时报告原始计数；
- p95 门禁同时要求点估计达到 20% 和置信区间不跨越零收益；
- 不从该 MVE 推断接受概率、跨环境普适性或生产性能。

## 12. Gate 判定

### Go：允许申请进入 G3 实现

必须同时满足：

1. Full-Strong-FIFO 在 near-saturation 或 burst 下的排队等待至少占 action-gate p95 的 20%；
2. SafeQueue-MVE 相对 Full-Strong-FIFO 的 p95 降幅至少 20%，且 95% CI 不跨零；
3. hard-job downgrade 和 fail-open 均为 0；
4. dangerous-action execution 不超过 Full-Strong-FIFO；
5. benign-action pass rate 下降不超过 3 个百分点；
6. starvation 为 0，Jain 指数相对 DRR 下降不超过 0.02；
7. 没有简单基线在匹配安全与公平后，以 5% 以内的 p95 差距达到同等效果。

### No-Go：停止当前 SafeQueue-MVE

任一 Go 条件失败即 No-Go。根据失败原因只允许：

- verifier queue 不是瓶颈：转验证服务、批处理或缓存优化；
- cascade 已足够：停止联合调度主张；
- fair queue 已足够：保留简单公平基线，不增加学习调度；
- 安全或校准失败：转硬能力门控与恢复协议；
- 标签或许可失败：返回 G1。

## 13. 执行优先级

| Priority | Experiment | Claim defended | Cost | Dependency | Stop condition |
| --- | --- | --- | --- | --- | --- |
| P0 | 数据、许可、标签资格门 | 可审计性 | low | commit 与映射规则 | 1,000/100 条门槛失败 |
| P0 | 4090D verifier profiling | 真实瓶颈 | medium | 模型与 prompt 冻结 | 无法稳定运行或排队占比不足 |
| P1 | Full-Strong-FIFO 三负载重放 | 瓶颈基线 | low | profiling | F1 失败立即停止 |
| P1 | 四个其余方法配对重放 | 联合机制是否必要 | low | F1 通过 | 任一安全硬门失败 |
| P1 | 配对统计与 Gate 表 | Go/No-Go | low | 全部重放 | 输出判定后停止，不扩实验 |

## 14. 空结果模板

### 14.1 Profiling

| Tier | Model/version | Input-length bin | N | Mean service ms | p95 service ms | Peak VRAM MB | Error/OOM | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Light | TBD | short | TBD | TBD | TBD | TBD | TBD | planned |
| Light | TBD | medium | TBD | TBD | TBD | TBD | TBD | planned |
| Light | TBD | long | TBD | TBD | TBD | TBD | TBD | planned |
| Strong | TBD | short | TBD | TBD | TBD | TBD | TBD | planned |
| Strong | TBD | medium | TBD | TBD | TBD | TBD | TBD | planned |
| Strong | TBD | long | TBD | TBD | TBD | TBD | TBD | planned |

### 14.2 Main paired replay

| Load | Method | Action-gate p95 ms ↓ | Queue p95 ms ↓ | Dangerous executions ↓ | Hard downgrades ↓ | Benign pass % ↑ | Strong verifier % ↓ | Jain ↑ | Worst-tenant p95 ms ↓ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Low | Full-Strong-FIFO | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Low | Calibrated-Cascade-FIFO | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Low | Static-Risk-Priority | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Low | DRR-Fair | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Low | SafeQueue-MVE | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Near saturation | Full-Strong-FIFO | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Near saturation | Calibrated-Cascade-FIFO | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Near saturation | Static-Risk-Priority | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Near saturation | DRR-Fair | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Near saturation | SafeQueue-MVE | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Burst | Full-Strong-FIFO | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Burst | Calibrated-Cascade-FIFO | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Burst | Static-Risk-Priority | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Burst | DRR-Fair | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Burst | SafeQueue-MVE | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

### 14.3 Gate ledger

| Gate item | Threshold | Observed | Pass/fail | Evidence path |
| --- | --- | --- | --- | --- |
| Queue bottleneck | ≥20% of p95 | TBD | TBD | TBD |
| SafeQueue p95 gain | ≥20%, CI excludes zero | TBD | TBD | TBD |
| Hard downgrade | 0 | TBD | TBD | TBD |
| Fail-open | 0 | TBD | TBD | TBD |
| Dangerous execution | ≤ Full-Strong | TBD | TBD | TBD |
| Benign pass drop | ≤3 pp | TBD | TBD | TBD |
| Starvation | 0 | TBD | TBD | TBD |
| Jain drop vs DRR | ≤0.02 | TBD | TBD | TBD |
| Simple baseline gap | >5% required | TBD | TBD | TBD |

## 15. 未冻结项

- owner 决定并签核版本化 `policy_text` 与 source-to-prompt materializer；
- owner 签核硬能力映射、AgentDojo envelope 与 SafeToolBench 150 条校准语义及公开发布数量差异；
- 云端在冻结硬件上一张 GPU 完成 preflight、两层独立 smoke test 与真实 profiling；profiling 前必须通过输入字段泄漏审计。

在这些字段完成前，本协议保持 `designed_not_frozen`。

No experimental result has been generated here. All `TBD` cells must be filled only from 真实运行结果或在完全匹配协议下核验过的公共基线结果。
