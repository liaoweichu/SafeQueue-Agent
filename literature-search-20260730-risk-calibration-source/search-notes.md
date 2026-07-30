# Search Notes

Date: 2026-07-30  
Mode: standard, narrowly scoped benchmark repair  
Purpose: find one public source that supplies at least 149 auditable unsafe-for-light-allow tool records without expanding the 1,000-event MVE.

## Safe Queries Used

- `LLM agent tool use safety benchmark harmful benign tool calls dataset action-level labels`
- `tool agent safety benchmark harmful tool calls benign tasks dataset official paper`
- `R-Judge agent safety benchmark dataset tool action risk`
- `SafeToolBench prospective tool utilization safety`
- `step-level tool invocation safety benchmark TS-Bench`
- Exact public titles were used only for official paper, repository, dataset, and license verification.

No private project text, local paths, or unpublished result claims were sent to search services.

## Sources Checked

- Official proceedings: ACL Anthology, NeurIPS proceedings, OpenReview.
- Stable paper records: arXiv.
- Official artifacts: project pages, GitHub repositories, Hugging Face dataset pages.
- Local artifact audit: immutable SafeToolBench archive at commit `ffdef6e782b0b05f579316003f3b084b549f1366`.

## Screening Ledger

| # | Candidate | Disposition | Reason |
| --- | --- | --- | --- |
| 1 | SafeToolBench | Selected | Prospective risky tool plans, MIT, enough rows for the 2% zero-error bound |
| 2 | ToolSafe / TS-Bench | Final caution | Closest step-level format; no visible repository license |
| 3 | R-Judge | Final caution | Human safe/unsafe labels but retrospective and no visible repository license |
| 4 | TraceSafe-Bench | Final future source | Strong trace-level fit; new preprint and unnecessary for minimal split |
| 5 | AgentHarm | Final alternative | Public harmful/benign tasks; restricted safety-only use and broader content |
| 6 | Agent-SafetyBench | Final alternative | MIT and broad; heavier end-to-end environments |
| 7 | ToolAlignBench | Final auxiliary | Mirrored safe/wrongdoing cases; only 64 risky scenarios |
| 8 | ToolSafety | Final background | Large training corpus; artifact terms not frozen |
| 9 | OS-Harm | Final future source | High-quality end-to-end benchmark; infrastructure-heavy |
| 10 | AgentHazard | Screened | New computer-use benchmark; not needed for minimum calibration repair |
| 11 | Agent Security Bench | Screened | Broad attack-tool benchmark already represented inside TS-Bench |
| 12 | MCPTox | Screened | Tool poisoning focus does not supply the required benign/risky calibration pair |
| 13 | OS-Blind | Screened | Computer-use context harms are valuable later but operationally heavy |
| 14 | SafeArena | Screened | End-to-end misuse setting is broader than pre-action verifier calibration |
| 15 | OffTopicEval | Screened | OOD labels but no tool action semantics |

## Artifact Audit Notes

- SafeToolBench official repository exposes an MIT license.
- Exact pinned commit: `ffdef6e782b0b05f579316003f3b084b549f1366`.
- Archive SHA-256: `0F0BA04880DA6C5DE3C36FE7590D5C17976C54E984E020A2A9C15FC1FB696444`.
- LICENSE SHA-256: `E1CC0E22D17018AC1FAB7ACA3B3D0DF785875512BFBE5D283A971CD54462EF3D`.
- Paper: 1,200 samples, 150 in each of eight strata.
- Pinned public archive: 1,000 rows; four multi-app strata have 100 rows and four single-app strata have 150 rows.
- Local filter: 16 score-6 rows excluded; 86 normalized-instruction duplicates excluded; 898 unique rows with score at least 7 remain.
- Deterministic G2 selection: 150 cases, 18 or 19 per stratum.

## Excluded Sources

- MDPI and other policy-excluded venues were not searched, cited, or scored.
- Search snippets, secondary summaries, Reddit, and commercial pages were not used for final evidence.
- Candidates without a stable primary paper or official artifact were excluded.

## Unknowns

- The reason for SafeToolBench's paper/archive row-count mismatch is unknown.
- ToolSafe/TS-Bench and R-Judge repository licensing was not visible at inspection time.
- TraceSafe-Bench artifact and redistribution terms were not frozen in this pass.

## Handoff Notes

- For experiment design: use SafeToolBench for calibration only; do not import paper results or expand it into a third replay environment.
- For pipeline orchestration: keep `G2_conditional` until the selected 150 labels, hard-function mappings, candidate risk budget, timeout formula, and 4090D profiling are signed off.
- For review: challenge any claim that treats SafeToolBench's fixed-split Clopper–Pearson bound as a deployment guarantee.

