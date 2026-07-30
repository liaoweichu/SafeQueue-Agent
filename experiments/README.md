# Experiments

实验目录由实验设计与真实运行填充。本脚手架不创建协议结论或结果数值。

- `configs/`：实验配置快照。
- `protocols/`：冻结前后的实验协议与空结果模板。
- `prompts/`：冻结候选 prompt 及其哈希来源。
- `profiling/`：硬件 profiling runbook；不存放预填结果。
- `results/`：真实运行输出及其 provenance。

任何结果都应记录代码版本、配置、数据版本、随机种子、运行环境和时间。

当前 G2 为 `G2_frozen`：同机 RTX 4090D 的 v3 `128×3` profiling 与独立审计已完成，服务时间证据可供后续离散事件重放使用。尚无五方法主重放结果，也未授权训练、线上部署或论文结论。
