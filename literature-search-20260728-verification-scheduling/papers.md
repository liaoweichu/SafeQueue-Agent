# Literature Search: Safety Verification Scheduling for Multi-Tenant Tool Agents

Date: 2026-07-28  
Search purpose: G1 novelty, benchmark, license, and baseline feasibility grounding for a scarce-compute safety-verification scheduler  
Target venue/family: Systems / Security / AI Systems, venue not yet fixed  
Source-quality policy: applied; final claims use official proceedings, stable arXiv records, official project pages, and official repositories

## Summary

- G1 verdict: **`conditional_pass`**.
- Closest-work clusters: runtime guardrails and verifier cascades; conformal action/trajectory risk control; multi-tenant agent serving and fair scheduling; executable agent-safety benchmarks.
- Direct-overlap result: no screened work jointly covers all four required mechanisms: multi-tenant verifier queues under bursts, calibrated action-risk control, an immutable non-bypass verification set, and joint tail-latency/benign-success/cost/fairness evaluation.
- Opportunity map: the defensible gap is a **safety-verification service problem**, not a generic agent scheduler, generic guardrail, verifier cascade, conformal gate, or fair queue.
- Strongest baselines: full strong verification; GuardAgent/ShieldAgent-style executable policy checks; FinHarness-style light/strong cascade; CORA/CRC-style calibrated execute-or-escalate; FIFO; EDF; static risk priority; VTC/DRR fair service; SAGA/Justitia-style agent-level fairness.
- Benchmark candidates: pin the current τ-bench lineage for stateful tool execution and use AgentDojo for security pressure. RedTeamCUA is a stronger but heavier second environment. Vera-Bench and Phone-Harm must not be dependencies until artifact licensing/release issues are resolved.
- Novelty risks: GuardAgent and ShieldAgent already cover executable action-policy verification; CORA covers conformal pre-action risk gating; FinHarness covers adaptive light/strong verifier routing; ToolChain-CRC covers trajectory-level conformal control under drift; SAGA, Justitia, H-MAS, MARS, VTC, and Autellix cover most generic scheduling, fairness, burst, and latency claims.
- Recommended next action: proceed only to a minimal falsification experiment. Do not start full training or paper writing before proving that verifier queueing is a real bottleneck and that any latency gain survives a matched dangerous-action constraint.

## G1 Verdict

### Verdict: `conditional_pass`

The direction remains testable, but only under a narrower contribution boundary.

Evidence supporting continuation:

1. The search found no paper that treats heterogeneous safety-verification jobs as a shared multi-tenant service while simultaneously enforcing a mandatory verification class, calibrated residual risk, and tenant fairness.
2. A stateful tool-agent environment and a security stress source are legally available: the current τ-bench repository and AgentDojo are both MIT-licensed.
3. All required G1 baselines have implementation paths. Classical queue policies are straightforward; VTC has an Apache-2.0 artifact; MARS provides an Apache-2.0 replay-oriented scheduler prototype that includes FCFS and an Autellix-style baseline; safety baselines can be reimplemented from public method descriptions.

Why this is not an unconditional pass:

1. The individual ingredients are already crowded. A broad claim about agent scheduling, fairness, cascaded verification, deterministic policy checking, or conformal action gating would be weak.
2. Several closest safety artifacts are unavailable or legally unclear: CORA is still a release placeholder; FinHarness and ToolChain-CRC have no verified official code link; Vera exposes code but its repository shows no license; GuardAgent exposes code but no repository license was visible.
3. The project has not yet shown that verifier service time, rather than agent inference or tool execution, creates the tail-latency bottleneck.
4. SAGA and Justitia substantially narrow any systems novelty claim by already providing agent-level fairness and worst-case service reasoning.

The minimal defensible contribution is therefore:

> Model prospective safety checks as heterogeneous, tenant-attributed verification jobs; keep a capability-defined hard class outside learned scheduling; apply calibrated routing only to the remaining jobs; and evaluate safety, recovery, tail latency, cost, and tenant service deficit under identical traces and verifier capacity.

This is a search-grounded scope boundary, not a claim of global firstness.

## Direct-Neighbor Matrix

Legend: **Yes** = directly covered; **Partial** = related mechanism without the required semantics; **No** = not covered.

| Work | Multi-tenant queue / burst | Calibrated action-risk bound | Hard non-bypass verification | Joint tail / success / cost / fairness | Action-safety environment | Artifact status | Effect on the direction |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GuardAgent | No | No | Partial: guard requests become executable checks, but an LLM generates the checking code | Partial: guard accuracy, not queue tails or fairness | EICU-AC, Mind2Web-SC | Code public; repository license not visible | Verification-by-executable-policy is not novel |
| ShieldAgent | No | No formal conformal bound | Partial: explicit verifiable rules and formal checking, but learned retrieval/probabilistic inference remain | Partial: accuracy, API queries, inference time | ShieldAgent-Bench | Project page public; reusable code/license not verified | Efficient formal policy verification is already covered |
| CORA | No | Yes: conformal execute/abstain boundary | Partial: Goal-Lock and intervention paths, not an immutable mandatory strong-verification class | Partial: safety/helpfulness/interruption, no queue fairness | Phone-Harm plus public GUI benchmarks | Official repository is a release placeholder | Calibrated pre-action gating is already covered |
| FinHarness | No shared queue | Partial: risk scoring and adaptive routing, no formal OOD risk guarantee | Partial: deterministic priors exist, but no external immutable class | Partial: ASR, benign approval, strong-judge calls; no tail/fairness | FinVault | No official code link verified | Light/strong verifier cascading is already covered |
| ToolChain-CRC | No | Yes: trajectory-level CRC, drift margin, anytime alarm | No | Partial: risk and intervention, no multi-tenant queue/fairness | Synthetic, RAG/tool stress, agentic QA | No official code link verified | Trajectory calibration under tool-use drift is already covered |
| The Verifier Tax | No | No | Partial: policy-mediated runtime enforcement | Partial: safety, success, recovery, horizon and compute; no queue/fairness | τ-bench Airline/Retail | Paper and τ-bench available; dedicated code not verified | Establishes the safety-success-compute tradeoff to beat |
| Vera / Vera-Bench | Parallel test workers, not a runtime verifier queue | No | Yes for case-specific deterministic test predicates | No runtime queue/fairness objective | Sandboxed mail, code, finance, messaging and search services | Code public; repository license not visible | Executable end-state verification is not a new benchmark principle |
| VTC | Yes: tenant-aware fair LLM service | No | No | Partial: fairness and service efficiency, no action safety | LLM serving workloads | Apache-2.0 artifact | Fair service accounting is established |
| SAGA | Yes: multi-tenant agent workflows and bursts | No | No | Partial: completion time, SLO, throughput and task-level fairness; no action safety | SWE-bench, WebArena, BurstGPT traces | HPDC 2026 paper; no official code link verified | Agent-level fairness and workflow-atomic scheduling are already covered |
| Justitia | Yes: task-parallel agents on shared GPUs | No | No | Partial: efficiency plus worst-case service degradation; no action safety | Diverse task-parallel agent workloads | Preprint; code/license not verified | Virtual-time fair queuing for agents is already covered |
| H-MAS | Yes: multi-tenant bursts, drift and heterogeneous SLOs | No | No; its “safety guards” protect scheduler adaptation, not agent actions | Partial: Goodput and QoS stability, no action-safety metrics | Azure trace replay | Findings ACL 2026; code not verified | Burst-aware adaptive multi-tenant scheduling is covered |
| MARS | Partial: heterogeneous GPU/CPU agent workloads and admission control | No | No | Partial: end-to-end latency and throughput, no tenant safety/fairness guarantee | Replay plus OpenHands | Apache-2.0 preview code; full reproduction pending | Heterogeneous agent co-scheduling is covered |
| Autellix | Agent-program scheduling, not explicitly safety-verifier tenants | No | No | Partial: end-to-end latency/throughput, no action safety | Agentic serving workloads | Paper public; official code not verified | Program-level scheduling is an established baseline |

### Direct-overlap conclusion

No row covers all required columns. However, the matrix also shows that each individual mechanism has strong prior art. The project must demonstrate value from the **intersection**, not from any component in isolation.

## What Verifier Tax, FinHarness, and Later Work Cover

### The Verifier Tax

Already covers:

- Runtime enforcement in multi-step tool agents.
- Horizon-dependent safety/success tradeoffs.
- Safe success, unsafe success, recovery after a block, and verifier compute burden.
- τ-bench Airline and Retail as a stateful evaluation substrate.

Does not cover:

- A shared verifier-capacity model or arrival process.
- Multi-tenant scheduling, burst handling, starvation, or service fairness.
- Calibrated action-risk upper bounds.
- A separation between an immutable hard verification class and learned routing.

### FinHarness

Already covers:

- Query-level and tool-level inline monitoring.
- Accumulated trajectory risk.
- Adaptive routing between lightweight and advanced LLM judges.
- Reduction in advanced-judge calls while tracking attack success and benign approval.

Does not cover:

- Contention among tenants for a finite verifier service.
- Queue waiting time, p95/p99 latency, or burst stability.
- Tenant-level fairness.
- A formal conformal/OOD risk guarantee.
- A hard verification class that no learned scheduler can downgrade.

### Later and adjacent work

- GuardAgent and ShieldAgent claim executable or formally checkable action-policy enforcement.
- CORA claims conformal action-conditional execute/abstain control.
- ToolChain-CRC claims trajectory-level conformal control under retrieval/tool drift and anytime intervention.
- Vera provides deterministic, evidence-grounded verification over executable end states.
- SAGA and Justitia claim agent-level fairness; H-MAS handles multi-tenant bursts and drift; MARS co-schedules heterogeneous GPU/CPU agent work.

Therefore the following claims should be avoided:

- “First risk-aware agent verifier.”
- “First verifier cascade.”
- “First conformal safety gate for agent actions.”
- “First fair scheduler for LLM agents.”
- “First executable safety verification benchmark.”

## Paper Table

| # | Title | Year | Venue/source | Link | Type | Insight | Completeness | Numeric evidence | Overall | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | GuardAgent: Safeguard LLM Agents via Knowledge-Enabled Reasoning | 2025 | ICML 2025 | [PMLR](https://proceedings.mlr.press/v267/xiang25a.html) | method + benchmark | 4 | 4 | 4 | Risk | Dynamic safety requests are compiled to executable guard code; code is public but no repository license was visible |
| 2 | ShieldAgent: Shielding Agents via Verifiable Safety Policy Reasoning | 2025 | ICML 2025 | [PMLR](https://proceedings.mlr.press/v267/chen25ae.html) | method + benchmark | 4 | 4 | 4 | Risk | Explicit policy rules, formal verification, and efficiency results directly constrain hard-verifier claims |
| 3 | CORA: Conformal Risk-Controlled Agents for Safeguarded Mobile GUI Automation | 2026 | arXiv | [arXiv](https://arxiv.org/abs/2604.09155) | method + benchmark | 5 | 3 | 4 | Risk | Strongest action-level calibration neighbor; official repository has not released code, benchmark, or model |
| 4 | FinHarness: An Inline Lifecycle Safety Harness for Finance LLM Agents | 2026 | arXiv | [arXiv](https://arxiv.org/abs/2605.27333) | pure method | 4 | 3 | 4 | Risk | Strongest verifier-cascade neighbor; no official code link verified |
| 5 | ToolChain-CRC: Conformal Risk Control for Agentic AI Under Retrieval and Tool-Use Drift | 2026 | arXiv | [arXiv](https://arxiv.org/abs/2606.18467) | theory/proof | 5 | 4 | 4 | Risk | Strongest trajectory-risk and drift neighbor; no official code link verified |
| 6 | The Verifier Tax: Horizon Dependent Safety Success Tradeoffs in Tool Using LLM Agents | 2026 | arXiv | [arXiv](https://arxiv.org/abs/2603.19328) | other: empirical diagnostic | 4 | 3 | 3 | Risk | Defines the safety-success-recovery burden that the proposed system must not hide |
| 7 | Conformal Risk Control | 2024 | ICLR 2024 | [ICLR proceedings](https://proceedings.iclr.cc/paper_files/paper/2024/hash/f3549ef9b5ff520a7e41ff3cc306ab2b-Abstract-Conference.html) | theory/proof | 5 | 5 | 4 | A | Formal anchor; guarantees require explicit loss monotonicity and calibration assumptions |
| 8 | Safety Testing LLM Agents at Scale: From Risk Discovery to Evidence-Grounded Verification | 2026 | arXiv | [arXiv](https://arxiv.org/abs/2607.01793) | system/tool | 4 | 4 | 4 | Risk | Vera-Bench offers deterministic end-state/tool-evidence verifiers; repository license is missing |
| 9 | Fairness in Serving Large Language Models | 2024 | OSDI 2024 | [USENIX](https://www.usenix.org/conference/osdi24/presentation/sheng) | pure method | 5 | 5 | 5 | A | VTC is the strongest implementable tenant-fairness anchor; artifact is Apache-2.0 |
| 10 | SAGA: Workflow-Atomic Scheduling for AI Agent Inference on GPU Clusters | 2026 | HPDC 2026 | [arXiv](https://arxiv.org/abs/2605.00528) | system/tool | 5 | 4 | 5 | Risk | Already combines multi-tenant agent workflows, bursts, completion time and task-level fairness; no action safety |
| 11 | Justitia: Fair and Efficient Scheduling of Task-parallel LLM Agents with Selective Pampering | 2026 | arXiv preprint | [arXiv](https://arxiv.org/abs/2510.17015) | pure method | 4 | 3 | 4 | Risk | Virtual-time agent fair queuing with worst-case service reasoning; code/license not verified |
| 12 | MARS: Efficient, Adaptive Co-Scheduling for Heterogeneous Agentic Systems | 2026 | arXiv preprint | [arXiv](https://arxiv.org/abs/2604.26963) | system/tool | 4 | 4 | 4 | Risk | GPU/CPU co-scheduling and admission are close systems priors; Apache-2.0 preview is not 4090D-ready |
| 13 | H-MAS: Hierarchical Multi-Agent Scheduling for Multi-Tenant LLM Serving | 2026 | Findings ACL 2026 | [ACL Anthology](https://aclanthology.org/2026.findings-acl.1946/) | pure method | 3 | 4 | 4 | Risk | Covers bursts, drift, heterogeneous SLOs and adaptive scheduling; “safety” is scheduler fallback, not action safety |
| 14 | τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains | 2024 | arXiv; current τ-bench lineage repository | [arXiv](https://arxiv.org/abs/2406.12045) | pure benchmark | 5 | 4 | N/A benchmark | A | Stateful policies, tools, tasks and action outcomes; use a pinned current repository version |
| 15 | AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents | 2024 | NeurIPS 2024 Datasets & Benchmarks | [NeurIPS proceedings](https://proceedings.neurips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract-Datasets_and_Benchmarks_Track.html) | pure benchmark | 5 | 5 | N/A benchmark | A | 97 realistic tasks and 629 security cases; MIT-licensed implementation |

Benchmark-quality notes:

- τ-bench: realistic stateful customer-service policies and tools; current repository is active and reproducible; explicit danger labels are limited; version drift must be pinned.
- AgentDojo: realistic tool/data interaction with adaptive attacks and defenses; strong security labels and reproducibility; task scale is smaller than general customer-service suites.

## Clusters

### Cluster 1: Runtime guardrails and executable policy verification

- Representative papers: GuardAgent, ShieldAgent, FinHarness, The Verifier Tax.
- What this cluster already solves: prospective action checks, policy-to-code verification, risk-aware light/strong judges, runtime blocking, recovery and safety-success accounting.
- Remaining gap: shared verifier capacity, tenant attribution, burst behavior, service-time heterogeneity, and fairness under a non-bypass hard class.
- Possible rescue or differentiation route: treat verification as a separate service plane whose queueing semantics and failure modes are auditable.
- How it affects the project: the verifier itself cannot be the primary novelty; the workload and constrained scheduling problem must be.

### Cluster 2: Calibrated action and trajectory risk

- Representative papers: CORA, ToolChain-CRC, Conformal Risk Control.
- What this cluster already solves: calibration of execute/abstain or accept/intervene rules, trajectory aggregation, drift extensions, and anytime alarms.
- Remaining gap: interaction between calibrated routing and finite shared verifier capacity, especially when hard jobs must never be downgraded.
- Possible rescue or differentiation route: separate statistical eligibility from queue service; calibration may decide only among permitted paths.
- How it affects the project: do not claim a new conformal method unless the mathematics materially differs; use existing CRC as a constraint or module.

### Cluster 3: Multi-tenant and agent-level serving

- Representative papers: VTC, SAGA, Justitia, H-MAS, MARS; supporting baseline: Autellix.
- What this cluster already solves: token/service fairness, workflow-atomic scheduling, task completion fairness, worst-case service degradation, burst/drift response, admission control, and heterogeneous GPU/CPU co-scheduling.
- Remaining gap: these systems optimize inference/tool workloads and do not model unsafe action execution as a constrained outcome.
- Possible rescue or differentiation route: define verifier service cost separately from agent inference cost and prove gains at matched safety constraints.
- How it affects the project: generic latency, burst, or fairness contributions will be judged incremental unless tied to safety-verification semantics.

### Cluster 4: Executable stateful safety evaluation

- Representative papers: Vera, AgentDojo, τ-bench; secondary candidates: RedTeamCUA, SafeArena, Agent Security Bench.
- What this cluster already solves: stateful tool use, attack cases, sandboxed execution, environment-state outcomes, and deterministic/evidence-grounded verifiers.
- Remaining gap: no standard benchmark exposes a multi-tenant verifier arrival trace with measured light/strong service times and hard-verification labels.
- Possible rescue or differentiation route: release a derived, license-compatible verifier-service trace and replay protocol rather than another broad safety benchmark.
- How it affects the project: benchmark contribution should be a workload/protocol artifact, not a new collection of generic unsafe prompts.

## Opportunity Map

| Cluster | Status | Open gap | Possible direction | Evidence needed | Risk |
| --- | --- | --- | --- | --- | --- |
| Runtime guardrails | covered central mechanisms; deployment/system gap | Finite verifier service and queue-induced harm/recovery failures | Safety-verification service plane with explicit capacity and backpressure | Measured service times, queue traces, recovery outcomes | High: GuardAgent, ShieldAgent and FinHarness own most mechanism claims |
| Conformal risk | covered central claim; theory/analysis gap at system boundary | Risk guarantees under queue delay, overload, and fallback | Use CRC as an eligibility constraint plus conservative overload fallback | Calibration split, coverage audit, OOD stress, failure bounds | High: CORA and ToolChain-CRC are direct |
| Agent scheduling | crowded but open | Safety semantics and immutable verification classes are absent | Constrained fair scheduling of verification jobs | Same-trace matched-safety comparison and starvation tests | High: SAGA/Justitia/H-MAS/MARS narrow generic systems novelty |
| Benchmarks | benchmark gap | No verifier-service workload with tenant arrivals and service tiers | Derive replayable workload from open stateful/security environments | License ledger, trace schema, deterministic labels | Medium: Vera already owns executable verification framing |
| Negative result | negative-result opportunity | Adaptive routing may fail when the verifier is not the bottleneck or calibration shifts | Falsification-first study of when safety scheduling helps | Bottleneck decomposition and preregistered stop rules | Low scientific risk; may produce a useful diagnostic even if the method fails |

## Benchmark And Dataset Candidates

| Name | Link | License / access | Stateful end-state | Action trace | Auditable safety labels | Fit | Main risks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Current τ-bench lineage (τ²/τ³ repository) | [Repository](https://github.com/sierra-research/tau2-bench) | MIT; code and data present | Yes | Yes | Policy/task outcomes; limited explicit danger taxonomy | Primary stateful workload source; start with Retail or Airline | July 2026 v1.0.1 changed `banking_knowledge` grading; pin tag/commit and avoid cross-version comparisons |
| AgentDojo | [Repository](https://github.com/ethz-spylab/agentdojo) | MIT; installable package and code | Yes | Yes | 629 security cases with attack/defense outcomes | Primary security-pressure source | Smaller domain coverage; API still evolving |
| RedTeamCUA / RTC-Bench | [Repository](https://github.com/OSU-NLP-Group/RedTeamCUA) | Apache-2.0; benchmark and code present | Yes, hybrid VM/web | Yes | 864 adversarial cases and end-to-end attack outcomes | Strong second environment after MVE | VMware/AWS, Docker services, credentials and infrastructure make it too heavy for first-pass 4090D work |
| Vera-Bench | [Repository](https://github.com/Yunhao-Feng/Vera) | Code/data public; **no repository license visible** | Yes | Yes | Case-specific deterministic state/tool predicates | Excellent verification-oracle reference | Do not redistribute or make it a required artifact until license is clarified; 12 containers per session are heavy |
| OffTopicEval | [Repository](https://github.com/declare-lab/OffTopicEval) | MIT; code/data present | No | No | ID, direct OOD and adaptive OOD labels | Auxiliary calibration/OOD stress only | Single-turn operational scope is not an action-scheduling environment |
| Phone-Harm | [CORA project](https://cora-agent.github.io/) | Paper public; benchmark/model/code not released | Intended yes | Intended step-level | Step-level harm labels | Strong future GUI validation source | Official repository says release is still being prepared |
| GuardAgent datasets | [Repository](https://github.com/guardagent/code) | Code and download path public; repository license not visible | Domain-dependent | Yes | Safety guard compliance | Baseline-development reference | License and dataset redistribution terms require clarification |
| ShieldAgent-Bench | [Project page](https://shieldagent-aiguard.github.io/) | Project page public; reusable code/license not verified | Trajectory-based | Yes | Explicit policy/rule violations | Baseline-development reference | Dataset count differs between project page and proceedings description; inspect artifact before use |

### Recommended environment choice

1. **MVE**: current τ-bench Retail or Airline, pinned to an exact tag/commit, combined with AgentDojo-derived security events or policy-violation labels.
2. **Second environment after MVE**: RedTeamCUA only if the first experiment passes and infrastructure time is justified.
3. **Auxiliary OOD check**: OffTopicEval or a held-out capability/policy split, but never as the only evidence.
4. **Do not depend on**: Phone-Harm, Vera-Bench, GuardAgent datasets, or ShieldAgent-Bench until license/release status is resolved.

## Baseline Feasibility

| Baseline | Public basis | Implementation path | 4090D feasibility | Same-budget comparison rule |
| --- | --- | --- | --- | --- |
| Full strong verification | Verifier Tax / FinHarness ablations | Route every eligible action to one fixed strong verifier; cache outputs for replay | Feasible in trace mode; expensive online | Same arrivals, hard-set definition, verifier service profile and safety threshold |
| Deterministic hard guard | GuardAgent / ShieldAgent / Vera | Implement a small capability-policy registry and deterministic predicates outside learned code | Feasible | Hard jobs always execute the same mandatory path for every scheduler |
| FinHarness-style cascade | FinHarness paper | Lightweight score plus thresholded advanced judge; sliding-window risk state | Feasible by reimplementation; official code absent | Same light/strong models, thresholds, memory window and cached outputs |
| CRC execute/escalate | CORA + Conformal Risk Control | Split calibration; use upper risk bound to allow light path or force strong path | Feasible | Same calibration set, target risk, hard-set override and OOD fallback |
| ToolChain-style trajectory control | ToolChain-CRC | Aggregate step scores; add anytime escalation | Feasible in replay; medium engineering cost | Same trajectory prefixes and intervention semantics |
| FIFO | Classical queueing | One queue ordered by arrival time | Trivial | Same service times and capacity |
| EDF | Classical real-time scheduling | Deadline derived from action SLO; deterministic tie-break | Trivial | Same deadlines; report misses and starvation |
| Static risk priority | Public risk-routing practice | Fixed bins from the same risk score; aging to expose starvation tradeoff | Trivial | No recalibration or hidden capacity changes |
| VTC / DRR fair queue | VTC artifact, Apache-2.0 | Tenant service counters using measured verifier time or normalized cost | Feasible | Same tenant weights and cost estimator; report service deficit and Jain index |
| SAGA/Justitia-style agent fairness | Public papers | Reimplement task-completion or virtual-time priority in replay only | Feasible as a simplified comparator | Do not claim equivalence to full cluster systems; use identical trace-level costs |
| MARS replay / Autellix PLAS comparator | MARS preview, Apache-2.0 | Reuse algorithm descriptions or adapt replay logic; MARS bundles FCFS and Autellix-style policies | Partial | The repository targets CUDA 12.8/datacenter GPUs and reports testing on H100/H200; compare only replay-level scheduling on 4090D |

## Recommended G2 Input Packet

This packet is ready for `ccf-experiment-designer` only as a minimal falsification protocol.

### Environment and trace

- Primary environment: pinned current τ-bench Retail or Airline.
- Security source: AgentDojo; map attacks and policy violations to prospective verification jobs.
- Initial scale: 1,000–5,000 replayed action events before any online agent run.
- Cache all light/strong verifier outputs and profile their service times separately on the single RTX 4090D.
- Record the exact repository commit, task split, model identifier, prompt/version hash, random seed, and license.

Minimum trace schema:

```text
tenant_id, session_id, step_id, arrival_time, action_type,
capability_class, hard_required, deadline, ground_truth_safety,
task_success_label, recovery_label, light_risk_score,
light_service_ms, strong_service_ms, verifier_outcome,
environment_id, dataset_version
```

### Immutable safety boundary

- Define the hard set from capabilities and action semantics before scheduling.
- Examples include irreversible financial transfer, credential disclosure, privilege change, destructive file operation, and external publication when the benchmark exposes such actions.
- Hard-set membership is evaluated outside the learned scheduler.
- Every hard job receives the mandatory verification path under every baseline and treatment.
- Under overload, the allowed fallback is queue, abstain, or request confirmation; downgrade or fail-open is not allowed.

### Workload regimes

- Low load: verifier utilization below 40%.
- Near saturation: 70–90% utilization.
- Overload/burst: short bursts above 100% offered load with recovery intervals.
- Tenant mixes: equal tenants; one heavy hitter; many small tenants; heterogeneous service-time tenants.
- Shift tests: held-out domain, changed attack family, and risk-score drift.

### Required baselines

1. Full strong verification.
2. Deterministic hard guard plus full strong verification for all remaining jobs.
3. FinHarness-style light/strong cascade.
4. FIFO.
5. EDF.
6. Static risk priority with aging.
7. VTC/DRR fair queue.
8. SAGA/Justitia-inspired agent-level fair priority.
9. Proposed constrained scheduler.

### Metrics

- Safety: dangerous-action execution rate, hard-set violation count, accepted-trajectory risk, calibration coverage.
- Utility: benign task success, approval rate, recovery after intervention.
- Systems: verifier queue wait, end-to-end p50/p95/p99, throughput, utilization, deadline misses.
- Cost: strong-verifier calls, total verifier milliseconds, energy/API proxy if available.
- Fairness: per-tenant normalized service deficit, Jain index, worst-tenant p95, starvation count.
- Audit: fail-open count, downgrade count, calibration violations, unknown-label count.

### Falsification and stop rules

Stop or reframe if any holds:

1. Verifier queueing is not a material contributor to end-to-end tail latency.
2. Apparent latency gains disappear when dangerous-action execution is matched.
3. Gains come from skipping, delaying beyond the action deadline, or downgrading hard-required checks.
4. A small tenant experiences starvation or unbounded service deficit under bursts.
5. Calibration fails under held-out domain shift and the conservative fallback erases the benefit.
6. A simple VTC/DRR or FinHarness-style baseline matches the proposed method.

## Citation And Positioning Cautions

- Phrase the negative search result as “no jointly covering work was found in the screened corpus as of 2026-07-28,” not “no prior work exists.”
- Treat SAGA as HPDC 2026 based on the paper metadata; its arXiv landing page still labels the record as a preprint.
- H-MAS uses “safety guards” for controller fallback; do not cite that phrase as evidence of unsafe-action verification.
- CORA’s arXiv page says code and benchmark are available, but the linked official repository states that code, benchmark and model will be released later. Use the repository state as the artifact-status truth.
- Vera’s code is visible, but absence of a repository license means visibility is not permission to reuse or redistribute.
- GuardAgent code and dataset links are public, but no repository license was visible. Reimplement or seek clarification before artifact inclusion.
- ShieldAgent’s project page and proceedings page report different benchmark counts. Cite the proceedings for paper claims and inspect the actual artifact before using it.
- FinHarness, ToolChain-CRC, Justitia, H-MAS, and Autellix had no verified official reusable code link in this search.
- τ-bench scores around the July 2026 `banking_knowledge` v1.0.1 change are not directly comparable. Pin a version and record it.
- Do not describe conformal control as unconditional safety. State the calibration, exchangeability/shift, loss and fallback assumptions.
- Papers that most weaken novelty: GuardAgent, ShieldAgent, CORA, FinHarness, ToolChain-CRC, SAGA, Justitia, H-MAS and MARS.
- Papers that primarily support background or baselines: Conformal Risk Control, VTC, Autellix, CCPO, FairServe and locality-aware fair scheduling.

## Verified Citation Candidates

These records are candidates for later bibliography construction; this search does not modify the manuscript bibliography.

1. Zhen Xiang, Linzhi Zheng, Yanjie Li, Junyuan Hong, Qinbin Li, Han Xie, Jiawei Zhang, Zidi Xiong, Chulin Xie, Carl Yang, Dawn Song, and Bo Li. “GuardAgent: Safeguard LLM Agents via Knowledge-Enabled Reasoning.” *Proceedings of the 42nd International Conference on Machine Learning*, PMLR 267, 2025. https://proceedings.mlr.press/v267/xiang25a.html
2. Zhaorun Chen, Mintong Kang, and Bo Li. “ShieldAgent: Shielding Agents via Verifiable Safety Policy Reasoning.” *Proceedings of the 42nd International Conference on Machine Learning*, PMLR 267, 2025. https://proceedings.mlr.press/v267/chen25ae.html
3. Yushi Feng, Junye Du, Qifan Wang, Zizhan Ma, Qian Niu, Yutaka Matsuo, Long Feng, and Lequan Yu. “CORA: Conformal Risk-Controlled Agents for Safeguarded Mobile GUI Automation.” arXiv:2604.09155, 2026. https://arxiv.org/abs/2604.09155
4. Haoxuan Jia, Yang Liu, Bin Chong, Yingguang Yang, Yancheng Chen, Jiayu Liang, Qian Li, Hanning Lu, Kefu Xu, Hao Zheng, Chongyang Zhang, Hao Peng, and Philip S. Yu. “FinHarness: An Inline Lifecycle Safety Harness for Finance LLM Agents.” arXiv:2605.27333, 2026. https://arxiv.org/abs/2605.27333
5. Jeffery Opoku and David Banahene. “ToolChain-CRC: Conformal Risk Control for Agentic AI Under Retrieval and Tool-Use Drift.” arXiv:2606.18467, 2026. https://arxiv.org/abs/2606.18467
6. Tanmay Sah, Vishal Srivastava, Dolly Sah, and Kayden Jordan. “The Verifier Tax: Horizon Dependent Safety Success Tradeoffs in Tool Using LLM Agents.” arXiv:2603.19328, 2026. https://arxiv.org/abs/2603.19328
7. Anastasios Angelopoulos, Stephen Bates, Adam Fisch, Lihua Lei, and Tal Schuster. “Conformal Risk Control.” *International Conference on Learning Representations*, 2024. https://proceedings.iclr.cc/paper_files/paper/2024/hash/f3549ef9b5ff520a7e41ff3cc306ab2b-Abstract-Conference.html
8. Yunhao Feng, Ruixiao Lin, Ming Wen, Qinqin He, Yanming Guo, Yifan Ding, Yutao Wu, Jialuo Chen, Zhuoer Xu, Xiaohu Du, Jianan Ma, Zixing Chen, Xingjun Ma, Yunhao Chen, and Xinhao Deng. “Safety Testing LLM Agents at Scale: From Risk Discovery to Evidence-Grounded Verification.” arXiv:2607.01793, 2026. https://arxiv.org/abs/2607.01793
9. Ying Sheng, Shiyi Cao, Dacheng Li, Banghua Zhu, Zhuohan Li, Danyang Zhuo, Joseph E. Gonzalez, and Ion Stoica. “Fairness in Serving Large Language Models.” *18th USENIX Symposium on Operating Systems Design and Implementation*, pages 965–988, 2024. https://www.usenix.org/conference/osdi24/presentation/sheng
10. Dongxin Guo, Jikun Wu, and Siu Ming Yiu. “SAGA: Workflow-Atomic Scheduling for AI Agent Inference on GPU Clusters.” *35th International Symposium on High-Performance Parallel and Distributed Computing*, 2026. DOI: 10.1145/3806645.3807598. https://arxiv.org/abs/2605.00528
11. Mingyan Yang, Guanjie Wang, Manqi Luo, Yifei Liu, Chen Chen, Han Zhao, Yu Feng, Quan Chen, and Minyi Guo. “Justitia: Fair and Efficient Scheduling of Task-parallel LLM Agents with Selective Pampering.” arXiv:2510.17015, revised 2026. https://arxiv.org/abs/2510.17015
12. Yifei Wang, Hancheng Ye, Yechen Xu, Cong Guo, Chiyue Wei, Qinsi Wang, Dongting Li, Tingjun Chen, Hai “Helen” Li, Danyang Zhuo, and Yiran Chen. “MARS: Efficient, Adaptive Co-Scheduling for Heterogeneous Agentic Systems.” arXiv:2604.26963, 2026. https://arxiv.org/abs/2604.26963
13. Yuhan Liu, Cong Xu, Qi Jia, Yihua Wang, Feiyu Chen, Liang Jin, Lu Liu, Yaqian Zhao, Yuting Ding, and Xiang Li. “H-MAS: Hierarchical Multi-Agent Scheduling for Multi-Tenant LLM Serving.” *Findings of the Association for Computational Linguistics: ACL 2026*, pages 39051–39071, 2026. DOI: 10.18653/v1/2026.findings-acl.1946. https://aclanthology.org/2026.findings-acl.1946/
14. Shunyu Yao, Noah Shinn, Pedram Razavi, and Karthik Narasimhan. “τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains.” arXiv:2406.12045, 2024. https://arxiv.org/abs/2406.12045
15. Edoardo Debenedetti, Jie Zhang, Mislav Balunović, Luca Beurer-Kellner, Marc Fischer, and Florian Tramèr. “AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents.” *Advances in Neural Information Processing Systems 37, Datasets and Benchmarks Track*, 2024. DOI: 10.52202/079017-2636. https://proceedings.neurips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract-Datasets_and_Benchmarks_Track.html

## Proposed Pipeline Handoff

The literature-search skill does not silently edit `ccfa.yaml`. If the pipeline orchestrator accepts this report, the recommended state transition is:

```yaml
stage:
  current: experiment_planning
gate:
  current: G2_conditional
artifacts:
  literature_search: literature-search-20260728-verification-scheduling/papers.md
```

The transition should preserve the condition: **G2 may design only the minimal falsification experiment; it may not authorize full training or manuscript drafting.**
