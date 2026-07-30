# Handoff 02 — G2 conditional minimal falsification

状态：`parameters_confirmed_cloud_profile_pending`  
Gate：`G2_conditional`  
Owner：`ccf-experiment-designer`  
模式：`standard / design-only`

## 编排决策

G1 的 `conditional_pass` 已被编排器接收，项目进入 `experiment_planning`。该转换只授权设计最小证伪实验，不代表 G2 已冻结，也不授权实验实现、运行、完整训练、在线部署、论文写作或结果主张。

## 已接收输入

- `literature-search-20260728-verification-scheduling/papers.md`
- `literature-search-20260728-verification-scheduling/papers.csv`
- `literature-search-20260728-verification-scheduling/search-notes.md`
- 单张 NVIDIA RTX 4090D、24 GB 显存约束
- G1 收窄边界：验证服务排队、校准路由、不可绕过硬集合与租户公平的交叉问题

## 本阶段唯一允许的任务

设计一个能快速否定以下任一前提的 trace-replay 协议：

1. 强验证器排队是中高负载下的实质性尾延迟瓶颈；
2. 在硬动作零降级、危险执行不增加的条件下，调度能带来至少 20% 的 p95 改善；
3. 收益不是简单 FinHarness 风格级联、静态风险优先或公平队列即可达到；
4. 突发负载下不存在小租户饥饿。

## 输出工件

- 协议：`experiments/protocols/g2-minimal-falsification.md`
- 配置草案：`experiments/configs/g2-minimal-falsification.yaml`
- 数据来源清单：`data/source-manifest.g2.yaml`
- 固定事件清单：`data/g2-event-selection.json`
- 硬能力注册表：`experiments/configs/hard-capability-registry.v1.json`
- 验证器 prompt：`experiments/prompts/verifier-v1.txt`
- profiling runbook：`experiments/profiling/g2-verifier-profiling-runbook.md`
- 冻结准备状态：`docs/g2-freeze-readiness.md`
- 硬映射预审计：`docs/audits/g2-hard-capability-pre-audit.md`
- SafeToolBench review packet：`docs/audits/g2-safetoolbench-review.md`
- profiling 输入 contract：`docs/g2-profiling-input-contract.md`
- 云 GPU 执行清单：`docs/cloud-gpu-execution-checklist.md`
- 结果状态：`none`

## G2 冻结前必填项

以下任一项缺失，Gate 保持 `G2_conditional`：

1. ~~τ-bench、AgentDojo 与 SafeToolBench 的精确 commit、任务快照和许可记录~~：已完成；
2. 验证器候选、版本、prompt 哈希和精度：已填写，仍待 4090D smoke/profile；
3. 版本化 `policy_text` 与 source-to-prompt materializer 的 owner 决策、实现和字段泄漏审计；
4. ~~用户确认风险预算候选 `epsilon=0.02` 与最大等待公式~~：已于 2026-07-30 确认；
5. 版本化硬能力注册表的人工映射审计；
6. ~~1,000 条事件数量门与危险校准支持门~~：已通过；拆分为 50 良性 + 150 危险校准、500 Retail + 300 AgentDojo 评估；
7. AgentDojo 目标动作 envelope 与可观测硬映射复核；
8. SafeToolBench 150 条校准标签的 100% 复核与论文/压缩包数量差异签核；
9. 云端完成与冻结硬件一致的 preflight、两层 smoke test 与真实服务时间 profiling；前提是第 3 项已经关闭。

## 冻结判定

只有在上述必填项完整、所有方法共享相同到达流、服务时间样本、硬集合、风险阈值与失败关闭语义时，编排器才能把 Gate 改为 `G2_frozen`。

## 失败或返回

- 数据/标签/许可不满足：返回 G1，更换环境或缩小事件集合。
- 模型无法在 4090D 上稳定 profiling：缩小验证器或改为经核验 API 服务时间，但必须重新冻结预算。
- 不能构造同预算比较：G2 不通过，不进入实现。
- 用户要求扩大为完整实验：需另行通过编排 Gate；本交接不提供该授权。
