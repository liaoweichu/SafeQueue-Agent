# SafeQueue CCFA pipeline roadmap

更新日期：2026-07-30  
模式：`standard`  
范围诊断：`multi-stage`

## 1. 项目决策简报

| 字段 | 当前决定 |
| --- | --- |
| 项目目标 | 验证 SafeQueue 是否能在硬安全边界下，把有限验证算力作为多租户排队资源进行调度，并改善尾延迟与成本而不牺牲危险动作控制和租户公平 |
| 当前阶段 | `experiment_planning` |
| 当前门禁 | `G2_conditional` |
| 当前受众 | 研究团队内部；尚未绑定投稿受众 |
| 目标 venue | `TBD`；首轮系统证据后在 Systems / Security / AI Systems 家族中收敛 |
| 时间基线 | 采用综合分析中的相对 14 周研究节奏；尚无固定投稿截止日期 |
| 计算约束 | 单张 NVIDIA RTX 4090D，24 GB 显存；优先 trace 重放、缓存强验证器输出和轻量模型 |
| 隐私边界 | C1 方向、内部报告和未来未公开结果按私有材料处理；检索只使用公开安全查询，不粘贴私有原文或本地路径 |
| 当前决定 | G1 已条件通过；只允许完成 G2 v3 的同机 constrained profiling 与审计。G2 冻结前不启动主重放、训练或论文写作 |

## 2. 当前工件与缺口

### 已有工件

- `ccfa.yaml`：项目状态与工件索引。
- `docs/scaffold-decisions.md`：范围、标题和 venue 待定决策。
- `manuscript/main.tex`：中性结构占位，不是投稿模板。
- `data/`、`experiments/`、`figures/`、`tables/`：空工件目录。
- 用户提供的 C1 综合分析：给出工作假设、三阶段实验节奏、基线、消融、阈值和失败分支。
- `literature-search-20260728-verification-scheduling/`：G1 近邻矩阵、许可核验、评分和条件结论。
- `literature-search-20260730-risk-calibration-source/`：危险/良性校准来源的定向补检与 SafeToolBench 选择依据。
- `experiments/protocols/g2-minimal-falsification.md`：G2 最小证伪协议草案，无实验结果。
- `experiments/configs/g2-minimal-falsification.yaml`：机器可读配置草案。
- `data/source-manifest.g2.yaml` 与 `data/g2-event-selection.json`：固定版本、许可哈希和 1,000 条确定性事件清单。
- `experiments/configs/hard-capability-registry.v1.json`：候选硬能力注册表。
- `experiments/prompts/verifier-v1.txt` 与 `experiments/profiling/g2-verifier-profiling-runbook.md`：验证器输入语义与 4090D 测量计划。
- `docs/g2-freeze-readiness.md`：当前冻结准备与阻塞项。
- `docs/audits/`：硬能力预审计与 SafeToolBench owner review ledger。
- `docs/cloud-gpu-execution-checklist.md`：云 GPU preflight、smoke/profile、停止线与回传要求。

### 当前缺口

1. `epsilon=0.02`、policy/materializer、hard registry、SafeToolBench 150/150 语义 ledger 与最大等待公式均已签核；v3 审计须重新确认公式导出的 `maximum_wait_ms=5000`。
2. v2 profiling selection 的 123/128 单一 stratum 失衡已作废；v3 必须以完整 chat prompt token 生成 43/43/42 的新 selection。
3. Qwen3-1.7B / Qwen3-8B 必须在同一 4090D 上以单 token logits mask 重跑 smoke 与真实 `128×3` profiling；不得复用 v2 服务时间。
4. 回传 v3 raw JSONL、summary、preflight、smoke 和 selection 后，独立审计器必须通过。
6. 无真实实验结果；不得进入五方法主重放、实现结论、完整训练、论文写作或特定会议模板迁移。

## 3. 门禁链

| Gate | 相对周次 | Owner | 必需输入 | 输出工件 | 通过条件 | 失败或阻塞处理 |
| --- | --- | --- | --- | --- | --- | --- |
| G0 范围与脚手架 | W0 | `ccf-project-scaffolder`、`ccf-pipeline-orchestrator` | C1 综合分析、项目目录 | 脚手架、scope lock、路线图 | 项目范围固定；venue 待定有依据；状态文件和工件路径有效 | 已通过 |
| G1 新颖性、数据与基线落地 | W0–W1 | `ccf-literature-searcher` | C1 范围、已知近邻和候选 benchmark | 近期近邻矩阵、可用性/许可表、差异性结论、经核验文献候选 | 未发现已联合覆盖四个核心机制的直接近邻，或存在可明确收窄的差异；至少一个状态化环境和一个安全压力来源可合法获取；关键基线有可实现路径 | **2026-07-28 条件通过**；只允许进入最小证伪协议设计 |
| G2 MVE 协议冻结 | W1 | `ccf-experiment-designer` | G1 工件、4090D 约束、C1 预注册门槛 | trace schema、协议、指标、统计计划、配置矩阵、空结果表 | 1k–3k trace 路径可执行；全量强验证、FIFO、静态风险和 SafeQueue 在相同 trace、容量和安全阈值下比较；服务时间来自 profiling；停止条件预先写入 | 协议无法公平比较或标签不可审计时，不进入实现；返回 G1 或缩小 MVE |
| G3 MVE Go/No-Go | W1–W3 | 研究实现执行者；`ccf-experiment-designer` 管理证据形状 | 冻结协议、实现、运行日志 | 可复现 MVE 结果、profiling、失败样例、门禁结论 | 在相同危险漏放约束下，相对全量强验证的 p95 至少下降 20%；收益不是跳过必要验证造成；验证器排队经 profiling 确认为瓶颈 | 未达门槛则停止当前 SafeQueue 版本；按证据转“硬能力门控 + 恢复协议”或验证器服务优化，不直接堆更复杂 RL |
| G4 方法与完整离线证据 | W4–W8 | `ccf-experiment-designer`；研究实现执行者 | G3 通过结果、近邻实现、第二环境 | 风险校准、硬门、多租户调度、核心基线/消融、Pareto 与统计结果 | 相对全量强验证：危险执行无显著增加；良性成功下降不超过 3 个百分点；中高负载 p95 下降至少 25%；至少两个独立环境成立 | 任一安全或跨环境条件失败则回退机制、收窄主张或停止；不得用平均值掩盖尾部与租户饥饿 |
| G5 鲁棒性与系统证据 | W9–W13 | `ccf-experiment-designer`；研究实现执行者 | G4 方法冻结、在线沙箱 | OOD/时间外、突发负载、验证器故障、在线小规模实测、能耗/成本、公平性、错误 taxonomy | 三类负载、三随机种子和置信区间齐全；报告 p50/p95/p99、危险执行、良性成功、恢复、能耗/成本与 Jain 公平；仿真结论有系统实测支撑 | 证据不足时定位为阶段性技术报告，不包装成完整安全调度论文 |
| G6 Venue 与证据叙事冻结 | G5 后 | `ccf-pipeline-orchestrator`，随后 `ccf-paper-writer` | G1–G5 真实工件 | 目标 venue/year、页数预算、主张—证据矩阵、写作 handoff | venue 与贡献形态匹配；主张不超过证据；取得当年官方规则和模板 | 在线系统证据不足时不强投系统/安全叙事；继续保持中性模板或选择更匹配家族 |
| G7 写作、评审与完整性闭环 | Venue 冻结后 | `ccf-paper-writer` → `ccf-paper-reviewer` → `ccf-paper-writer` → `ccf-integrity-auditor` | 冻结证据、真实图表、已核验引用 | 完整稿件、评审报告、修订稿、完整性审计 | 核心主张均有证据；数字/图表/引用一致；主要 reviewer 风险有明确处理 | 重大证据缺口返回 G4/G5；文字问题返回 writer；不得由审计或评审技能静默重写稿件 |
| G8 投稿就绪 | 明确截止日期后 | `ccf-submission-checker` | 目标会议、最终稿、artifact | 官方模板构建、匿名性/页数/字体/伦理/许可/artifact 检查 | 所有阻断项关闭且 PDF、补充材料和发布计划可复现 | 任一官方规则或构建阻断项未关闭，不提交 |

## 4. 阶段节奏

```text
W0–W1   G1 近期证据、数据与基线落地
W1      G2 MVE 协议冻结
W1–W3   G3 MVE 实现与第一次 Go/No-Go
W4–W8   G4 风险校准、硬约束、多租户调度与完整离线证据
W9–W13  G5 鲁棒性、第二环境、在线小规模实测与统计闭环
W14+    G6–G8 选会、写作、评审、完整性与投稿检查
```

上述周次是相对规划，不等于已承诺的日历 deadline。任何阶段只有在前一 Gate 通过后才扩张资源投入。

## 5. Venue 决策规则

- 有在线原型、真实并发、系统瓶颈 profiling、尾延迟/能耗/故障恢复和完整 artifact：优先评估 Systems / Security 家族。
- 主要贡献是风险校准与受约束调度算法，系统实测较轻：优先评估 AI Systems、Trustworthy AI 或服务计算方向。
- 只有离线分类准确率、单数据集或随机划分：不进入完整安全调度论文叙事。
- 具体会议、年份、页限和模板只在 G6 使用当年官方页面核验后写入 `ccfa.yaml`。

## 6. 硬停止与转向规则

1. 新近直接工作已联合覆盖核心机制且没有可验证差异：停止原版本，转 `ccf-idea-optimizer`。
2. p95 收益来自少验证或危险漏放上升：G3 失败，禁止继续包装为安全调度收益。
3. 验证器排队不是主要瓶颈：转验证器服务优化、批处理或缓存，不升级 RL 复杂度。
4. 风险模型在环境外失去校准：扩大保守区间、按能力分层校准或回退全量验证。
5. 小租户饥饿或总体指标掩盖不公平：增加虚拟队列/等待债务后重过 G4。
6. 无第二环境、真实服务时间、三种负载、三随机种子或置信区间：只能定位为阶段性技术报告。

## 7. 当前交接

下一 owner：`ccf-experiment-designer`  
交接工件：`docs/g2-freeze-readiness.md`  
当前状态：`G2_conditional`，v3 本地协议已冻结但云端重跑未完成。
交接条件：按 `docs/cloud-gpu-execution-checklist.md` 生成 43/43/42 selection、完成同机 constrained smoke/profile，并使 `scripts/audit_g2_profiling_artifacts.py` 通过后，才能申请 G2 冻结；冻结前不启动五方法主重放、训练或论文写作。
