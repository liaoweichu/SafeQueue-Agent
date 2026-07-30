# G2 Cloud GPU Execution Checklist

状态：`completed_gate_frozen`  
更新日期：2026-07-30

## 范围与停止线

该清单只授权云端完成两个候选验证器的环境预检、模型 smoke test 与真实服务时间 profiling。它**不**授权五方法主重放、训练/微调、在线部署、结果填表或论文结论。所有数值保持 `TBD`，直到云端原始工件回传并通过本地审计。

当前冻结参数：

- `epsilon=0.02`；
- `maximum_wait_ms = ceil(max(5000, 4 × measured_strong_p95_ms))`；
- Light：`Qwen/Qwen3-1.7B@70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`，BF16；
- Strong：`Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218`，BF16；
- 两模型必须分进程、单独加载，不能同时常驻显存。

## 云端执行清单

### 0. 先确认硬件，不匹配则暂停

- [ ] 记录云实例提供商、区域、实例型号、操作系统、CPU/RAM、GPU 名称、显存、NVIDIA driver、CUDA 与 PyTorch 版本；
- [ ] 使用一张 NVIDIA GPU，显存不少于 24 GiB；建议预留至少 80 GiB 可用磁盘和 32 GiB RAM；
- [ ] 若 GPU 不是 RTX 4090D，**先不要开始 profiling**。回传 `nvidia-smi` 与 preflight JSON；该硬件变体需要重新记录并由编排器确认，不能静默套用 4090D 结论；
- [ ] 不在 shell history、仓库、日志或回传包中写入云账号密钥、SSH 私钥或 Hugging Face token。

### 1. 传输并校验冻结输入

- [ ] 传输整个项目目录，以及三个未跟踪的原始压缩包：
  - `data/raw/tau2-bench-v1.0.1.zip`；
  - `data/raw/agentdojo-v0.1.35.zip`；
  - `data/raw/safetoolbench-ffdef6e782b0b05f579316003f3b084b549f1366.zip`；
- [ ] 在云端项目根目录运行：

  ```bash
  python3 scripts/g2_cloud_preflight.py --output artifact/cloud-gpu/preflight.json
  ```

- [ ] 仅当 preflight 对三个 source archive、事件清单、prompt、确认参数、磁盘、GPU、CUDA 和 BF16 都返回 `passed: true` 时继续；
- [ ] 若只想在无 GPU 机器上检查输入，可使用 `--skip-gpu-check`。该模式不能证明云端可运行。

### 2. 建立隔离运行环境并取得固定模型版本

- [ ] 在项目外或项目内隔离目录建立 Python 环境；按云端 driver/CUDA 组合使用 [PyTorch 官方安装选择器](https://pytorch.org/get-started/locally/) 安装 CUDA 兼容的 PyTorch；
- [ ] 安装 `transformers`、`huggingface_hub`、`safetensors` 及 profiling runner 所需的最小依赖，并把精确版本写入环境 provenance；
- [ ] 检查 `hf --help`；Hugging Face 当前 CLI 支持 `hf download` 和 `--revision` 固定下载版本。[官方 CLI 文档](https://huggingface.co/docs/huggingface_hub/guides/cli)
- [ ] 将模型下载到云端专用缓存，不要下载到项目版本库：

  ```bash
  hf download Qwen/Qwen3-1.7B --revision 70d244cc86ccca08cf5af4e1e306ecf908b1ad5e
  hf download Qwen/Qwen3-8B --revision b968826d9c46dd6066d109eabc6255188de91218
  ```

- [ ] 若需要身份认证，使用云端交互式 `hf auth login` 或受控密钥管理；不把 token 写入配置、命令记录或回传日志。

### 3. Smoke test：逐模型、无主重放

- [ ] 先启动 Light，再完全退出进程并释放显存；然后对 Strong 重复；
- [ ] 固定 `experiments/prompts/verifier-v1.txt` 的 SHA-256 为 `BA19ABD9776361BDAC5922D374EDFAA51771374F4C1F8C9BB5B1E674BE8E0F21`；
- [ ] 强制 BF16、`enable_thinking=false`、`do_sample=false`、batch size 1、`max_new_tokens=4`；
- [ ] 检查输出只能解析为 `0`、`1` 或 `2`，并记录加载峰值显存、CUDA 错误和 OOM；
- [ ] 任一模型 OOM、输出无法受限或版本不符：停止，回传日志；不得量化、替换模型或继续主重放。

### 4. 真实 profiling：仅在可审计的输入 materializer 就绪后

- [ ] 当前项目没有已签核的 `policy_text` 或追踪的 source-to-prompt materializer；因此在它们冻结前，云端只能完成第 0–3 步，不能把任何临时 prompt 测量称为有效 profiling；
- [ ] 先按 `docs/g2-profiling-input-contract.md` 关闭 policy 与 materializer 决策，并对 128 条 rendered input 做字段泄漏审计；
- [ ] profiling runner 必须先将固定来源事件渲染为完整 prompt 输入；输入中只能包含 policy、state summary、user intent、proposed action 和 `hard_required`，不得包含 `ground_truth_safety`、攻击标签、benchmark outcome 或事后状态；
- [ ] 固定选择 128 个动作，按来源、实际输入长度三分位、`hard_required`（校准专用为 `N/A`）与离线安全标签分层；安全标签只用于离线抽样，绝不写入模型输入；
- [ ] 每层运行 10 个 warm-up，再对 128 条输入以固定种子随机顺序各重复 3 次；总计每层 384 个计入统计的测量；
- [ ] 每次记录 wall-clock service time、CUDA event time、输入/输出 token、峰值显存、OOM、解析错误与标签；模型加载时间不计入单 job 服务时间；
- [ ] 有效性门：每层完成 384 次、OOM=0、解析失败=0、至少 95% 测量无后台 GPU 干扰；
- [ ] 不启动 arrival trace、五个排队方法、校准阈值搜索或任何 `experiments/results/` 主结果写入。

### 5. 回传且不改写协议

- [ ] 回传 `artifact/cloud-gpu/preflight.json`、每层环境与加载 provenance、原始逐次测量文件、汇总的 p50/p95/p99、GPU 监测日志和错误日志；
- [ ] 保留 source archive、事件清单、prompt、模型 revision、profiling seed 与脚本 commit/hash；
- [ ] 不要根据云端结果直接编辑 `g2-minimal-falsification.yaml`、协议或结果表。先把原始工件回传；
- [ ] 由编排器检查 profiling 有效性，计算确认后的 `maximum_wait_ms`，并结合 owner 对映射和 150 条校准语义的签核决定是否进入 `G2_frozen`。

## 仍需在本地完成的非云端签核

- [ ] 项目 owner 签核 `docs/audits/g2-hard-capability-pre-audit.md`；
- [ ] 项目 owner 完成 `docs/audits/g2-safetoolbench-label-review.csv` 的 150 条语义复核，并签核 1,200 vs 1,000 的公开发布差异；
- [ ] 项目 owner 签核 `docs/g2-profiling-input-contract.md` 中的 policy payload 与 source-to-prompt materializer；
- [ ] 将云端 preflight 与 profiling 原始工件带回本项目后，再改变任何 Gate 或结果状态。
