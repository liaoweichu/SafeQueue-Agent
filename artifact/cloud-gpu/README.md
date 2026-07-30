# Cloud GPU Artifact Status

`preflight.json`, `profiling-light.jsonl`, and `profiling-strong.jsonl` are v2 diagnostic artifacts. They demonstrate that the recorded 4090D environment could execute both models, but their selection has an invalid 123/128 short/non-hard allocation and no logits-mask decoding. They are retained for provenance only and must not be used by G3 replay.

The only candidate freeze artifacts are the separately named v3 files produced by `docs/cloud-gpu-execution-checklist.md`:

- `preflight.v3.json`
- `smoke-test-results.v3.json`
- `profiling-light.v3.jsonl` and `profiling-light.v3.summary.json`
- `profiling-strong.v3.jsonl` and `profiling-strong.v3.summary.json`
- `g2-v3-audit.json`

`g2-v3-audit.json` 已报告 `passed: true`，并确认 `derived_maximum_wait_ms=5000`；因此项目 Gate 为 `G2_frozen`。这些是服务时间证据，不是五方法主重放或论文结果。

G3 已获单独的最小 replay 授权。下一批 cloud artifact 必须由 `docs/cloud-gpu-g3-score-cache-checklist.md` 产生：两个 700 行、无 oracle 的 score cache、各自 summary，以及 `g3-score-cache-audit.json`。它们仍不是完整 G3 Go/No-Go 结果；tau-only replay 的 F5 matched-danger 必须保持 `not_evaluable`。
