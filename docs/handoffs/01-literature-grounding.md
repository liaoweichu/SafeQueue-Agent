# Handoff 01 — literature grounding

状态：`ready`  
Gate：`G1`  
Owner：`ccf-literature-searcher`  
模式：`standard`

## 任务目标

为 SafeQueue 的第一次投资决策完成近期近邻、数据、代码、许可和基线可实施性核验。重点不是泛泛整理 Agent 安全文献，而是判断以下组合是否仍有可发表差异：

1. 多租户验证资源排队与突发负载；
2. 分布外校准的风险上界；
3. 不可被学习调度器覆写的硬验证集合；
4. 尾延迟、良性成功、成本与租户公平的联合评价。

## 可用输入

- `ccfa.yaml`
- `docs/scaffold-decisions.md`
- `docs/pipeline-roadmap.md`
- 用户提供的 C1 综合分析及其中已列出的 Verifier Tax、FinHarness、RTC-Bench/RedTeamCUA、OffTopicEval、τ-bench 等候选

内部综合分析和 C1 方向属于未公开私有材料。不得把完整标题、原始假设、内部路径或未公开文本直接提交给搜索服务。

## 公共安全检索边界

使用拆分后的公开概念查询，不搜索项目简称或完整未公开标题。查询应覆盖：

- agent action verification overhead and verifier cascades；
- verifier workload scheduling, queueing and tail latency；
- calibrated risk or conformal risk control for agent actions；
- multi-tenant fairness under heterogeneous service times；
- stateful tool-agent safety benchmarks and executable end-state evaluation。

优先使用论文原文、作者/项目页、官方 benchmark 仓库和官方 venue 页面。二手摘要只能用于发现线索，不能支撑最终差异性结论。

## 必答问题

1. 是否存在已联合解决四个核心机制的直接近邻？
2. Verifier Tax、FinHarness 及其后续工作分别覆盖了什么，未覆盖什么？
3. 哪些公开环境提供状态化终态评分、动作级轨迹和可审计危险标签？
4. 数据、代码、模型权重和许可证是否允许研究复现与匿名 artifact？
5. 哪些最近邻与经典调度基线有公开实现或可明确复现的算法描述？
6. 若原始差异不足，最小可守住的收窄版本是什么？

## 输出工件要求

保存一份可追踪报告，至少包括：

- 直接近邻矩阵：问题、机制、负载模型、安全约束、校准、公平、实验环境、代码状态；
- 数据/benchmark 可用性表：链接、许可、获取状态、终态评分、动作 trace、安全标签、主要缺口；
- 基线可实施性表：实现来源、复现成本、同预算比较方式；
- 新颖性结论：`pass`、`conditional_pass` 或 `fail`，并列出证据和未检索不确定性；
- 推荐的 G2 输入包：可用环境、压力测试、基线和必须保留的差异边界；
- 经核验的引用候选与完整元数据，但不直接改写论文参考文献库。

## G1 通过条件

- 没有发现已经联合覆盖四个核心机制的直接近邻；若有局部覆盖，差异边界可被操作化和实验验证；
- 至少一个状态化 Agent 环境与一个安全压力来源可合法获取；
- 全量强验证、FinHarness 风格级联、FIFO、EDF、静态风险优先和公平队列均有可实现路径；
- 对数据许可、代码状态和未核验项有明确标记；
- 能给 `ccf-experiment-designer` 一个不依赖虚构数据或结果的 G2 输入包。

## 失败分支

- `fail — direct overlap`：转 `ccf-idea-optimizer`，优先收窄到并发队列、硬约束或公平性中的可验证缺口。
- `fail — unavailable evidence`：替换环境、数据或基线后重跑 G1。
- `conditional_pass`：只允许设计最小证伪实验，不启动完整训练或论文写作。

