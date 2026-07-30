# G2 Profiling Input Contract

状态：`policy_and_materializer_signed`  
更新日期：2026-07-30

## 为什么这是冻结前条件

`experiments/prompts/verifier-v1.txt` 是模板，其中包含 `{{policy}}`、`{{state_summary}}`、`{{user_intent}}`、`{{tool_name}}` 与 `{{tool_arguments}}`。当前项目尚未固定 `{{policy}}` 的具体内容，也没有追踪的 source-to-prompt materializer。任意临时填写或手工拼接都会改变验证器输入分布、风险校准和服务时间，因此不能被视为可复现实验。

本文件只定义必须冻结的接口，不替项目 owner 擅自选择安全 policy 或实现适配器。

## 必须冻结的输入记录

每个送入 Light 或 Strong 的 profiling 记录必须有下列字段：

```text
event_id
source / source_version
policy_text / policy_sha256
prompt_template_sha256
state_summary
user_intent
tool_name
tool_arguments
hard_required
rendered_prompt_sha256
```

不得将 `ground_truth_safety`、攻击/注入标签、benchmark security outcome、后执行环境状态、方法 ID、负载 regime 或期待标签写入模型输入。离线抽样阶段可使用安全标签与 hard 标签分层，但它们不属于 rendered prompt。

## Source-specific materialization requirements

| 来源 | 必须从固定快照读取 | 可用于模型输入 | 不得用于模型输入 |
| --- | --- | --- | --- |
| τ-bench Retail | task 的用户请求、调用前状态、金标 action 名与参数 | 用户请求、调用前 state summary、proposed action | action 是否被 benchmark 判对、事后状态 |
| SafeToolBench | instruction、`used_api` 工具计划、质量分/风险类别 | instruction 与工具计划的调用前表示 | 风险类别、quality score、校准标签 |
| AgentDojo | user task、调用前环境可见状态、实际 proposed action | 用户任务、未受信 state/tool output、proposed action | injection case ID、target-function 真值、security outcome |

AgentDojo 的 `target_functions` 可以用于离线 hard-capability 映射审计，但不能代替实际 proposed action，更不能作为模型输入。若不能从固定公开环境中渲染调用前可见的 action，则该事件不能进入有效 profiling，必须记录并重新选择；不得用 injection label 或事后 security 条件填补。

## Owner 需要决定的内容

1. 批准一个版本化、可公开审计的 `policy_text`，并将其保存为单独文件及 SHA-256；
2. 批准每个来源的 source-to-prompt materializer，实现必须从固定压缩包/环境读取字段并输出上述记录；
3. 对 128 条 profiling 输入先做一次字段泄漏审计，再允许云端加载模型进行真实 profiling；
4. 如果 AgentDojo 无法提供调用前实际 action，则把它保留为 held-out security evidence，不纳入 verifier latency profile，且更新分层与协议。

## 与云端的关系

云端现在可以完成 `scripts/g2_cloud_preflight.py` 和两个模型的独立 smoke test。真实 128×3 profiling 必须等待上述 policy 与 materializer 冻结；不得用临时 prompt 或人工改写的 benchmark 内容替代。
