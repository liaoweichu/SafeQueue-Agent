# SafeQueue

论文项目：**SafeQueue: Risk-Calibrated Scheduling of Verification Workloads for Multi-Tenant Edge Agents**

当前状态：`experiment_planning`（`G2_conditional`）  
目标会议：`TBD`  
模板状态：中性 LaTeX 占位模板；尚未绑定具体会议。

## Scope lock

本项目按用户给定的 C1 方向初始化：将有限的安全验证算力建模为多租户排队资源，联合考虑硬安全约束、风险校准、尾延迟与公平性。

脚手架不包含新生成的研究主张、摘要、实验结果或引用。后续内容必须来自用户确认、公开证据或真实实验。

## 目录

| 路径 | 用途 |
| --- | --- |
| `ccfa.yaml` | CCFA 项目状态与工件索引 |
| `manuscript/` | 中性 LaTeX 稿件骨架与参考文献占位 |
| `docs/` | 项目决策与非论文说明 |
| `src/` | SafeQueue 实现 |
| `tests/` | 自动化测试 |
| `configs/` | 可复现实验配置 |
| `data/` | 数据说明、原始数据、处理中间件和 trace |
| `experiments/` | 实验入口、配置镜像与真实结果 |
| `figures/`、`tables/` | 论文图表工件 |
| `reviews/` | 评审材料与修订台账 |
| `submission/` | 投稿检查与最终包状态 |
| `artifact/` | 可复现性与发布工件 |

## 当前管线

- [完整路线图](docs/pipeline-roadmap.md)
- [G1 文献落地报告](literature-search-20260728-verification-scheduling/papers.md)
- [风险校准来源补检](literature-search-20260730-risk-calibration-source/papers.md)
- [G2 最小证伪协议](experiments/protocols/g2-minimal-falsification.md)
- [G2 冻结准备状态](docs/g2-freeze-readiness.md)
- [Profiling 输入 contract](docs/g2-profiling-input-contract.md)
- [云 GPU 执行清单](docs/cloud-gpu-execution-checklist.md)
- [下一阶段交接包](docs/handoffs/02-g2-minimal-falsification.md)

G0“范围与脚手架”已通过；G1 结论为 `conditional_pass`。G2 已形成无 oracle 泄漏的 1,000 条固定事件设计：50 条 τ-bench 良性校准、150 条 SafeToolBench 危险校准、500 条 τ-bench 评估与 300 条 AgentDojo 评估。用户已确认风险预算与超时公式；仍需 owner 决定 policy/materializer、完成映射/标签签核及云 GPU profiling。协议仍未冻结，尚未授权五方法主重放、完整训练、在线部署或论文写作。

## 下一步所有权

1. `ccf-literature-searcher`：已完成 G1 近期近邻、数据许可和基线可实施性核验。
2. `ccf-experiment-designer`：仅设计并冻结最小证伪协议、指标、对比和统计计划。
3. 研究实现执行者：只有在 G2 冻结后才能按协议实现并运行 MVE；不得由计划文档预填结果。
4. `ccf-pipeline-orchestrator`：在每个 Go/No-Go 点更新阶段与下一 owner。
5. `ccf-paper-writer`、`ccf-paper-reviewer`、`ccf-integrity-auditor`：证据冻结后进入写作—评审—审计闭环。
6. `ccf-submission-checker`：选定目标会议后核验官方模板、匿名性、构建与 artifact。
