# G2 Freeze Readiness

更新日期：2026-07-30  
当前 Gate：`G2_conditional`  
判定：`not_ready_to_freeze`

## 已完成

- τ-bench 固定到 `v1.0.1` / `fc0055dc4e0a316c3f83133267fbd6faaa770992`；
- AgentDojo 固定到 package `v0.1.35` / `a75aba7631d3ca5fb7ab938965c97ead2f9ff84b`，benchmark `v1.2.2`；
- SafeToolBench 固定到 `ffdef6e782b0b05f579316003f3b084b549f1366`，仅作为危险校准来源；
- 三个源码许可证均核验为 MIT，并记录源码压缩包与 LICENSE 哈希；
- 验证器候选固定为 Qwen3-1.7B / Qwen3-8B、BF16、non-thinking、分层单独加载；
- 统一 verifier prompt、风险分数定义和 profiling runbook 已落盘；
- 硬能力注册表候选已覆盖 Retail 精确工具名与 AgentDojo 可观测目标函数；已删除“样本属于注入目标即 hard”的 oracle 规则；
- 静态资格审计采用最小混合校准：50 条 Retail 良性动作 + 150 条 SafeToolBench 危险/需审批工具计划；评估为 500 条 Retail 动作 + 300 条 AgentDojo held-out 案例；
- 150 条危险校准样本在零 false-allow 时的单侧 95% Clopper–Pearson 上界为 `0.01977344`，刚好支持候选 `epsilon=0.02`；一次 false-allow 即判不可行；
- 固定清单共有 1,000 条事件、800 条评估事件、454 条硬评估事件、300 条危险注入目标和 9 条非硬危险事件；数量门与校准支持门通过；
- AgentDojo 排除了 20 个纯文本输出目标；300 个选中案例均已获得 literal target function 或注册表人工 envelope；
- SafeToolBench 固定压缩包有 1,000 行而论文报告 1,200 条；审计排除 16 条低于质量门的记录和 86 条重复 instruction，得到 898 条合格唯一候选。该差异已记录，但仍需人工签核；
- 事件清单 SHA-256：`8afed1ffe3dcd20e930bd914d74329352308c426aacb99d0ef50ba0879cad3fb`。
- 项目 owner 已确认 `epsilon=0.02` 与 `ceil(max(5000, 4 × measured_strong_p95_ms))`；
- 已生成 AgentDojo 硬映射预审计、SafeToolBench 150 行 review ledger 与云 GPU 执行清单；它们保留 owner 语义签核与真实 profiling 两类阻塞项。

## 仍未完成

1. 项目 owner 决定并签核版本化 `policy_text` 与 source-to-prompt materializer；
2. 项目 owner 签核硬能力注册表的人工映射预审计；
3. 项目 owner 签核 AgentDojo 人工 envelope 与其余 literal target function 的最终复核；
4. 项目 owner 完成 `docs/audits/g2-safetoolbench-label-review.csv` 的 150 条风险语义复核，并签核论文/公开压缩包数量差异；
5. 云端在与冻结硬件一致的一张 GPU 上完成 preflight、两层 smoke test 与真实 profiling；profiling 前必须先完成输入渲染审计。

## 编排约束

上述六项关闭前：

- `ccfa.yaml` 保持 `experiment_planning / G2_conditional`；
- 协议状态保持 `designed_not_frozen`；
- 不运行五方法主重放；
- 不训练、微调、在线部署或写论文；
- 不产生任何性能、安全或显著性结论。

云端操作顺序、传输清单、停止条件和回传文件见 `docs/cloud-gpu-execution-checklist.md`。

完成后由 `ccf-pipeline-orchestrator` 复核并决定是否升级为 `G2_frozen`。升级只授权按冻结协议进入 G3 MVE 实现，不代表实验结果通过。
