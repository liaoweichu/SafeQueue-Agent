# Literature Search: Minimal Risk-Calibration Source

Date: 2026-07-30  
Search purpose: repair the G2 calibration split with a public, auditable dangerous tool-plan source while preserving the 1,000-event MVE budget  
Target venue/family: undecided Systems / Security / AI Systems  
Source-quality policy: primary paper, official project, repository, or dataset pages only; MDPI and untraceable artifacts excluded

## Summary

- The prior split was invalid for risk calibration: its 200 calibration events were all benign τ-bench actions.
- SafeToolBench is the smallest usable repair among the inspected artifacts: it is prospective, includes tool plans and risk explanations, and its official repository is MIT-licensed.
- The pinned SafeToolBench public archive contains 1,000 rows although the paper reports 1,200. Local static audit also found 16 rows below the paper's stated score-7 quality floor and 86 duplicate normalized instructions. The design therefore selects only from 898 unique rows with score at least 7 and must disclose the mismatch.
- Recommended split: 50 τ-bench benign calibration events + 150 SafeToolBench unsafe-for-light-allow calibration events; 500 τ-bench + 300 AgentDojo held-out evaluation events.
- At candidate `epsilon=0.02`, 149 unsafe samples are the minimum for a zero-error one-sided 95% Clopper–Pearson upper bound below the budget; 150 gives `0.01977344`. Any observed unsafe false-allow makes the candidate threshold infeasible.
- AgentDojo remains evaluation-only. Hard routing must use observable tool/function fields, never the benchmark's injection label.

## Paper Table

| # | Title | Year | Venue/source | Link | Type | Insight | Completeness | Numeric evidence | Overall | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | SafeToolBench: Pioneering a Prospective Benchmark to Evaluating Tool Utilization Safety in LLMs | 2025 | Findings of EMNLP | [ACL Anthology](https://aclanthology.org/2025.findings-emnlp.958/) | method + benchmark | 4 | 3 | 3 | Risk | Best calibration fit and MIT repository; paper/archive count and quality-floor mismatches require disclosure |
| 2 | ToolSafe: Enhancing Tool Invocation Safety of LLM-based Agents via Proactive Step-level Guardrail and Feedback | 2026 | Findings of ACL | [ACL paper](https://aclanthology.org/2026.findings-acl.1850/) | method + benchmark | 5 | 4 | 4 | Risk | TS-Bench has step-level safe/controversial/unsafe labels, but no repository license was visible |
| 3 | R-Judge: Benchmarking Safety Risk Awareness for LLM Agents | 2024 | Findings of EMNLP | [ACL Anthology](https://aclanthology.org/2024.findings-emnlp.79/) | pure benchmark | 4 | 4 | N/A benchmark | B | Human safe/unsafe labels over interaction records; retrospective rather than pre-action, and repository license not visible |
| 4 | TraceSafe: A Systematic Assessment of LLM Guardrails on Multi-Step Tool-Calling Trajectories | 2026 | arXiv preprint | [arXiv](https://arxiv.org/abs/2604.07223) | method + benchmark | 5 | 4 | 4 | Risk | More than 1,000 localized trace mutations; attractive future stress test, but not needed for the minimal split and artifact terms need verification |
| 5 | AgentHarm: A Benchmark for Measuring Harmfulness of LLM Agents | 2024 | arXiv / UK AISI dataset | [Dataset](https://huggingface.co/datasets/ai-safety-institute/AgentHarm) | pure benchmark | 4 | 5 | N/A benchmark | A | Harmful and benign agent tasks are public; license adds safety-only use restrictions and content scope is broader than the current operational-risk MVE |
| 6 | Agent-SafetyBench: Evaluating the Safety of LLM Agents | 2024 | arXiv / official repository | [Repository](https://github.com/thu-coai/Agent-SafetyBench) | pure benchmark | 4 | 4 | N/A benchmark | A | MIT code/data and broad risk coverage; heavier environments and end-to-end scoring make it less minimal than SafeToolBench |
| 7 | ToolAlignBench: Investigating Alignment Conflicts in Tool-Calling Enabled LLMs | 2026 | ICML workshop / OpenReview | [Project](https://toolalignbench.github.io/) | pure benchmark | 4 | 3 | N/A benchmark | B | 64 wrongdoing and 64 mirrored safe scenarios; useful later for contextual false positives, but too small for the 2% calibration bound |
| 8 | ToolSafety: A Comprehensive Dataset for Enhancing Safety in LLM-Based Agent Tool Invocations | 2025 | EMNLP | [ACL Anthology](https://aclanthology.org/2025.emnlp-main.714/) | method + benchmark | 4 | 4 | 4 | B | Large direct/indirect/multi-step safety-tuning corpus; training orientation and artifact/licensing uncertainty make it a poor frozen calibration dependency |
| 9 | OS-Harm: A Benchmark for Measuring Safety of Computer Use Agents | 2025 | NeurIPS Datasets & Benchmarks | [NeurIPS proceedings](https://papers.neurips.cc/paper_files/paper/2025/hash/4009bff0cd87ba2203c8e3a2f082aaec-Abstract-Datasets_and_Benchmarks_Track.html) | pure benchmark | 4 | 5 | N/A benchmark | B | Strong end-to-end harmful-action evidence, but OSWorld infrastructure is intentionally deferred beyond the single-4090D MVE |

## Closest Benchmark Clusters

### Prospective tool-risk plans

- Representative work: SafeToolBench, ToolSafe/TS-Bench.
- Already covered: pre-execution judgment over instructions, tool definitions, arguments, and tool plans.
- Remaining gap: artifact versioning and license clarity are inconsistent; SafeToolBench's released row count does not match the paper.
- G2 decision: use only a pinned, audited SafeToolBench subset; do not import its method or reported results.

### Interaction-record safety judges

- Representative work: R-Judge, TraceSafe-Bench.
- Already covered: safe/unsafe judgment over multi-turn or multi-step records.
- Remaining gap: R-Judge is retrospective; TraceSafe is a larger new benchmark whose artifact terms were not yet frozen.
- G2 decision: keep as verifier-input and future robustness references, not first-pass dependencies.

### End-to-end harmful agents

- Representative work: AgentHarm, Agent-SafetyBench, OS-Harm.
- Already covered: executable misuse, prompt injection, and environment-level safety outcomes.
- Remaining gap: they are heavier or broader than the queue-mechanics MVE and can confound verifier-service conclusions with agent execution capability.
- G2 decision: defer to later external validation if the minimal MVE passes.

## Opportunity Map

| Cluster | Status | Open gap | Possible direction | Evidence needed | Risk |
| --- | --- | --- | --- | --- | --- |
| Prospective tool-risk plans | benchmark gap | Reproducible release counts and immutable split contracts | Publish an audited calibration manifest rather than a new benchmark | Commit, archive/license hashes, row audit, deterministic selection | Medium |
| Step-level guardrails | crowded but open | Guard accuracy is rarely tied to finite shared verifier capacity | Use the same verifier scores as routing constraints in a queue replay | Matched traces, real service times, fail-closed overload behavior | High novelty overlap |
| End-to-end harmful agents | deployment/system gap | Heavy environments obscure whether verification compute is the bottleneck | Use only after the service-plane MVE passes | Second environment, recovery outcomes, real concurrent service | High cost |
| Negative calibration result | negative-result opportunity | A 2% budget may force all-strong routing on small or shifted calibration sets | Pre-register no-feasible-threshold fallback | 150 unsafe calibration cases, zero-error bound, held-out threats | Low scientific risk |

## Benchmark And Dataset Candidates

| Name | Access/license | Role considered | Fit | Decision |
| --- | --- | --- | --- | --- |
| SafeToolBench | Official GitHub, MIT | Dangerous/approval-required calibration only | High | Select 150 audited unique rows |
| τ-bench Retail | Official GitHub, MIT | Benign calibration and primary replay | High | Select 50 calibration + 500 held-out |
| AgentDojo | Official GitHub, MIT | Held-out adversarial evaluation | High | Select 300; no attack-label routing |
| TS-Bench | Public repository; no visible license | Step-level calibration/evaluation | Very high technical fit | Do not freeze as dependency |
| R-Judge | Public repository; no visible license | Verifier calibration | Medium | Do not freeze as dependency |
| AgentHarm | MIT plus safety-only clause | Harmful/benign calibration | Medium | Defer; broader harmful-content scope |

## Citation And Positioning Cautions

- SafeToolBench supports the existence of a prospective tool-risk benchmark, not the validity of SafeQueue's threshold or queueing claims.
- The 1,200-versus-1,000 release mismatch is an observed artifact fact and must be reported without guessing why it occurred.
- The 150-case calibration bound is an internal fixed-split guarantee only. It does not establish production, temporal, or cross-distribution safety.
- ToolSafe/TS-Bench is close prior art for step-level guards; SafeQueue must not claim novelty for action safety detection itself.
- No benchmark result from these papers is imported into the G2 result tables.

