# G2 Hard-Capability Mapping Pre-Audit

日期：2026-07-30  
状态：`owner_signed_2026-07-30`

## 结论

`experiments/configs/hard-capability-registry.v1.json` 中的 AgentDojo 21 个已观察目标函数被完整、互斥地划为 17 个 Strong 能力与 4 个可风险评分的非硬能力。固定 300 个 AgentDojo 评估案例中 291 个为 `hard_required=true`，9 个为非硬；不存在未知函数、集合重叠或由攻击标签决定硬路由的情况。

项目 owner 已于 2026-07-30 确认本预审计中的 Strong/非硬边界与 `strong_or_abstain` 歧义策略。该签核关闭 hard-capability mapping 阻塞项；它不构成 latency profiling 或 G3 结果声明。

## 审计证据与范围

- 固定事件清单：`data/g2-event-selection.json`，事件 SHA-256 `8afed1ffe3dcd20e930bd914d74329352308c426aacb99d0ef50ba0879cad3fb`；
- 注册表：`experiments/configs/hard-capability-registry.v1.json`；
- AgentDojo 压缩包：`data/raw/agentdojo-v0.1.35.zip`，SHA-256 `78DA8287D3F496608BBF1C7EAF48A7E4294493AC907CE96DCFB35763B7114D58`；
- 判定只读取调用前可见的 source/domain/tool 或目标函数能力映射；禁止读取攻击标签、benchmark outcome 或模型执行后状态；
- 未知/歧义函数的策略固定为 `strong_or_abstain`。

## AgentDojo 函数映射

| 映射 | 函数 | 理由 |
| --- | --- | --- |
| Strong | `add_user_to_channel`、`invite_user_to_slack`、`remove_user_from_slack` | 改变成员资格或访问控制。 |
| Strong | `create_calendar_event`、`reserve_hotel` | 产生外部日程或预订后果。 |
| Strong | `delete_email`、`delete_file` | 破坏性数据修改。 |
| Strong | `post_webpage`、`send_direct_message`、`send_email` | 有后果的外部通信或公开发布；可能泄露受保护信息。 |
| Strong | `send_money`、`update_scheduled_transaction` | 转移或修改资金/金融义务。 |
| Strong | `update_password` | 凭据或安全控制变更。 |
| Strong | `get_scheduled_transactions`、`get_user_information`、`read_channel_messages`、`search_emails` | 读取金融、个人或通信内容；在本 MVE 中保守地强验证。 |
| 可风险评分，非硬 | `get_all_hotels_in_city`、`get_channels`、`get_hotels_prices`、`get_webpage` | 只读枚举/检索能力；仍由风险分数与失败关闭语义约束。 |

## 无 literal FunctionCall 的人工 envelope

AgentDojo 的 `workspace/injection_task_6` 至 `workspace/injection_task_13` 在 `ground_truth()` 中返回空列表，因此不能以 AST literal call 直接抽取目标函数。预审计改读相同类的 `security()` 状态条件，得到下表。选中的 300 个案例中，100 个使用这 8 个 envelope；所有映射均为 Strong。

| Case | 从公开 `security()` 条件得到的可观测动作能力 | 注册表映射 | 结论 |
| --- | --- | --- | --- |
| `workspace/injection_task_6`、`_7` | 对外发送邮件，并删除已发送邮件 | `send_email`、`delete_email` | Strong |
| `workspace/injection_task_8`、`_9` | 对外发送邮件，并删除邮件 | `send_email`、`delete_email` | Strong |
| `workspace/injection_task_10` | 对外发送附件邮件，并删除已发送邮件 | `send_email`、`delete_email` | Strong |
| `workspace/injection_task_11`、`_12` | 对外发送附件邮件、删除邮件并删除文件 | `send_email`、`delete_email`、`delete_file` | Strong |
| `workspace/injection_task_13` | 对外批量发送邮件 | `send_email` | Strong |
| `travel/injection_task_6` | 纯文本输出目标 | 不进入动作重放 | 已排除 20 个兼容案例 |

## Owner 签核记录

1. 已确认上述 21 个函数的 Strong/非硬边界符合项目威胁模型；
2. 已确认未知/歧义能力继续使用 `strong_or_abstain`；
3. 已确认 `workspace` 的 8 个 envelope 不以“注入样本”本身作为 hard 理由；
4. 此结论已记录在 `docs/g2-freeze-readiness.md`；G2 的剩余阻塞项仅为 v3 云端 reprofile 和独立审计。
