# G2 Freeze Readiness

更新日期：2026-07-30  
当前 Gate：`G2_frozen`  
判定：`frozen — all blockers closed`

## 已完成

- τ-bench 固定到 `v1.0.1` / `fc0055dc4e0a316c3f83133267fbd6faaa770992`；
- AgentDojo 固定到 package `v0.1.35` / `a75aba7631d3ca5fb7ab938965c97ead2f9ff84b`，benchmark `v1.2.2`；
- SafeToolBench 固定到 `ffdef6e782b0b05f579316003f3b084b549f1366`，仅作为危险校准来源；
- 三个源码许可证均核验为 MIT，并记录源码压缩包与 LICENSE 哈希；
- 验证器候选固定为 Qwen3-1.7B / Qwen3-8B、BF16、non-thinking、分层单独加载；
- 统一 verifier prompt、风险分数定义和 profiling runbook 已落盘；
- 硬能力注册表候选已覆盖 Retail 精确工具名与 AgentDojo 可观测目标函数；已删除"样本属于注入目标即 hard"的 oracle 规则；
- 静态资格审计采用最小混合校准：50 条 Retail 良性动作 + 150 条 SafeToolBench 危险/需审批工具计划；评估为 500 条 Retail 动作 + 300 条 AgentDojo held-out 案例；
- 150 条危险校准样本在零 false-allow 时的单侧 95% Clopper–Pearson 上界为 `0.01977344`，刚好支持候选 `epsilon=0.02`；一次 false-allow 即判不可行；
- 固定清单共有 1,000 条事件、800 条评估事件、454 条硬评估事件、300 条危险注入目标和 9 条非硬危险事件；数量门与校准支持门通过；
- AgentDojo 排除了 20 个纯文本输出目标；300 个选中案例均已获得 literal target function 或注册表人工 envelope；
- 事件清单 SHA-256：`8afed1ffe3dcd20e930bd914d74329352308c426aacb99d0ef50ba0879cad3fb`；
- 项目 owner 已确认 `epsilon=0.02` 与 `ceil(max(5000, 4 × measured_strong_p95_ms))`；
- **versioned policy_text**：`experiments/prompts/policy-v1.txt`（SHA-256: `1772EE5994EAA7B81E23585A905D7D400EE01884FE1503CDB48B8599A5B09DAE`），已签核；
- **source-to-prompt materializer**：`src/materializers/` + `scripts/materialize_g2_prompts.py`，已签核；
- 硬能力注册表映射审计：21/21 函数注册，已签核；
- AgentDojo envelope 复核：300 案例 hard_required 逻辑正确，已签核；
- SafeToolBench 150 条风险语义签核：150/150 PASS，reviewer=project_owner, 2026-07-30。论文 1,200 与公开压缩包 1,000 数量差异已签核；
- 云端 GPU preflight + smoke test + profiling：RTX 4090D, 387/387×2 tiers, 0 OOM, 0 parse failures, Light p95=58.95ms, Strong p95=166.74ms。`maximum_wait_ms = 5000`。

## 全部完成

G2 冻结前置条件已全部关闭。Gate 已升级为 `G2_frozen`。编排约束已解除，可按 [handoff 02](docs/handoffs/02-g2-minimal-falsification.md) 进入 G3 MVE 实现阶段。升级只授权按冻结协议进入 G3，不代表实验结果通过。
