# Experiments

实验目录由实验设计与真实运行填充。本脚手架不创建协议结论或结果数值。

- `configs/`：实验配置快照。
- `protocols/`：冻结前后的实验协议与空结果模板。
- `prompts/`：冻结候选 prompt 及其哈希来源。
- `profiling/`：硬件 profiling runbook；不存放预填结果。
- `results/`：真实运行输出及其 provenance。

任何结果都应记录代码版本、配置、数据版本、随机种子、运行环境和时间。

当前 G2 协议、配置、prompt 与 profiling runbook 的状态均为 `designed_not_frozen` 或 `candidate_not_run`；没有实验结果，也未授权五方法主重放。
