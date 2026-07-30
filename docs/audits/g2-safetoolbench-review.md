# G2 SafeToolBench Calibration Review Packet

日期：2026-07-30  
状态：`source_row_integrity_passed_owner_semantic_signoff_pending`

## 静态完整性结论

固定 SafeToolBench 压缩包 `ffdef6e782b0b05f579316003f3b084b549f1366` 的 SHA-256 为 `0F0BA04880DA6C5DE3C36FE7590D5C17976C54E984E020A2A9C15FC1FB696444`。`scripts/generate_g2_safetoolbench_review_ledger.py` 对全部 150 个选中行重新读取原始 JSON，并逐行核对：规范化 instruction SHA-256、质量分、风险类别、工具列表、非空 instruction 与非空 API 列表。

静态核验均应为 `PASS`。按来源风险类别的固定数量为：

| 风险类别 | 选中数 |
| --- | ---: |
| Bias & Offensiveness | 37 |
| Physical Injury | 38 |
| Privacy Leak | 37 |
| Property Damage | 38 |

质量分范围为 7–10；150 个 instruction hash 和 source locator 均唯一。该检查支持“来源行与固定清单一致”，但不替代 owner 对每条风险语义的判断。

## Owner 的 100% 语义签核流程

1. 在受控副本中打开 `docs/audits/g2-safetoolbench-label-review.csv`；
2. 按每行 `source_file` 与 `source_row_index` 在固定压缩包中读取原始记录；
3. 确认该记录确实属于危险/需审批的工具计划，且适合标作 `unsafe_for_light_allow`；
4. 填写 `semantic_label_review` 为 `PASS` 或 `REJECT`，以及 reviewer、日期和必要备注；
5. 任一 `REJECT`、source hash 不符、行重复或风险不清晰时，停止冻结；重新选择或收窄校准集，不得放宽 `epsilon=0.02`；
6. 最后显式签核：论文报告 1,200 条样本、固定公开压缩包仅含 1,000 行；本项目从质量分至少 7 且规范化 instruction 唯一的 898 条候选中确定性选择 150 条。

## 复建命令

在项目根目录运行：

```powershell
& <python> scripts/generate_g2_safetoolbench_review_ledger.py
```

该命令只生成带 source locator 的 review ledger，不复制原始危险指令，也不下载模型或运行实验。
