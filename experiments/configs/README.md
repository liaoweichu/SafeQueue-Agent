# Experiment configurations

存放冻结后的实验配置快照；公共配置源文件可维护在项目根目录的 `configs/`。

`g3-minimal-tau-replay.json` 是已授权但尚未运行的最小 G3 配置。它固定 700×2 score-cache 输入、G2 v3 服务时间、到达过程、五个比较方法和 `maximum_wait_ms=5000`，并明确 tau-only 结果不能升级为完整 G3 Go/No-Go。
