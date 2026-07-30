# Source

`g3_replay.py` 是已授权的最小 G3 离散事件 replay 核心：它只处理冻结的 tau2-bench evaluation 事件、无 oracle 的双 verifier score cache，以及 G2 v3 的经验服务时间样本。它实现五个固定方法、共同随机数、session 级租户分配、`maximum_wait_ms=5000` 的 fail-closed abstain 和结果审计所需的 provenance hash。

`verifier_prompting.py` 与 `verifier_runtime.py` 继续定义冻结的 Qwen chat rendering、单 token `0/1/2` 约束和风险分数语义。任何训练、在线服务或第二环境实现都不在当前授权范围内。
