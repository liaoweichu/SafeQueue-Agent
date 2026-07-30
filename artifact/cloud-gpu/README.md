# Cloud GPU Artifact Status

`preflight.json`, `profiling-light.jsonl`, and `profiling-strong.jsonl` are v2 diagnostic artifacts. They demonstrate that the recorded 4090D environment could execute both models, but their selection has an invalid 123/128 short/non-hard allocation and no logits-mask decoding. They are retained for provenance only and must not be used by G3 replay.

The only candidate freeze artifacts are the separately named v3 files produced by `docs/cloud-gpu-execution-checklist.md`:

- `preflight.v3.json`
- `smoke-test-results.v3.json`
- `profiling-light.v3.jsonl` and `profiling-light.v3.summary.json`
- `profiling-strong.v3.jsonl` and `profiling-strong.v3.summary.json`
- `g2-v3-audit.json`

Until `g2-v3-audit.json` reports `passed: true`, the project gate is `G2_conditional`.
