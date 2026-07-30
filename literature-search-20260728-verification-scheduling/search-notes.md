# Search Notes

Date: 2026-07-28  
Mode: standard  
Screened candidates: 27  
Scored final set: 15  
Search stop condition: query saturation across safety verification, conformal control, multi-tenant scheduling, agent-level fairness, and executable benchmarks; the final scheduling pass found SAGA and Justitia but still no work combining their systems semantics with action-safety calibration and a non-bypass hard class.

## Safe Queries Used

The search used public concepts only. No unpublished project title, local path, private report text, or internal hypothesis wording was sent to a search service.

- `agent action verification overhead verifier cascades safety LLM agents`
- `multi tenant verification scheduling queue tail latency LLM agents safety`
- `conformal risk control agent actions safety calibration LLM agents`
- `stateful tool agent safety benchmark executable end state prompt injection`
- `multi-tenant safety verifier scheduling LLM agents queue fairness`
- `agent action verifier queue scheduling tail latency fairness`
- `conformal risk controlled action verification scheduling multi tenant agents`
- `scarce verifier compute cascade scheduling agent safety`
- `multi-tenant LLM serving fairness burst workload agent programs`
- `workflow-aware agent scheduling task completion fairness`
- `heterogeneous agent GPU CPU co-scheduling admission control`
- Exact public paper titles were used only to verify official paper, project, code, and license records.

## Sources Checked

- Official proceedings and publishers: PMLR/ICML, NeurIPS proceedings, USENIX, ACL Anthology, AAAI/OJS, ICLR proceedings, OpenReview.
- Stable paper records: arXiv and DOI metadata.
- Official project/repository records: CORA, τ-bench, AgentDojo, RedTeamCUA, OffTopicEval, Vera, VTC, GuardAgent, MARS.
- Discovery-only sources were used to locate candidates and were not used to support final claims.

## Screening Ledger

| # | Candidate | Disposition | Reason |
| --- | --- | --- | --- |
| 1 | GuardAgent | Final | Direct executable action-guard baseline |
| 2 | ShieldAgent | Final | Direct formal policy-verification and efficiency baseline |
| 3 | CORA | Final | Direct conformal action-gating novelty risk |
| 4 | FinHarness | Final | Direct verifier-cascade novelty risk |
| 5 | ToolChain-CRC | Final | Direct trajectory-level calibration and drift risk |
| 6 | The Verifier Tax | Final | Core safety-success-recovery diagnostic |
| 7 | Conformal Risk Control | Final | Formal anchor |
| 8 | Vera / Vera-Bench | Final | Executable deterministic verification reference |
| 9 | VTC / Fairness in Serving LLMs | Final | Implementable tenant-fair service baseline |
| 10 | SAGA | Final | Agent workflow scheduling and task-level fairness |
| 11 | Justitia | Final | Agent fair queuing and worst-case delay |
| 12 | MARS | Final | Heterogeneous agent co-scheduling and public replay code |
| 13 | H-MAS | Final | Multi-tenant bursts, workload drift and SLO scheduling |
| 14 | τ-bench | Final | Primary stateful environment |
| 15 | AgentDojo | Final | Primary security environment |
| 16 | Conformal Constrained Policy Optimization for Cost-Effective LLM Agents | Supporting | Important cost/reliability orchestration, but evaluated on multi-hop QA rather than unsafe actions or verifier queues |
| 17 | Autellix | Supporting | Strong program-level scheduling baseline; covered operationally by the MARS comparator path in the MVE |
| 18 | Locality-aware Fair Scheduling in LLM Serving | Supporting | Fairness plus prefix locality, but not agent-action verification |
| 19 | Ensuring Fair LLM Serving Amid Diverse Applications / FairServe | Supporting | Real multi-tenant traces and weighted service counters; no action safety |
| 20 | OffTopicEval | Auxiliary benchmark | Useful single-turn OOD stress; not stateful action scheduling |
| 21 | RedTeamCUA / RTC-Bench | Secondary benchmark | Strong licensed environment, but too infrastructure-heavy for the first MVE |
| 22 | SafeArena | Screened out of final | Strong misuse benchmark, redundant with closer stateful/security candidates |
| 23 | Agent Security Bench | Screened out of final | Broad attacks/defenses benchmark, not a verifier-service workload |
| 24 | Conformal Selective Acting | Supporting theory | Anytime selective risk for RLVR specialist streams, not tool-action queues |
| 25 | Anytime-Valid Conformal Risk Control | Supporting theory | General theory extension; redundant with CRC and ToolChain-CRC for this report |
| 26 | OpenAgentSafety | Screened out of final | Broad safety evaluation framework; no distinct verifier scheduling mechanism found |
| 27 | ST-WebAgentBench | Screened out of final | Safety/trust benchmark; redundant with AgentDojo/RedTeamCUA for G1 |

## Excluded Sources

- Policy-excluded or low-quality sources: MDPI results were excluded. A low-signal “burst-aware weighted fair queuing” journal result was retained only as an internal search clue and was not scored or cited.
- Untraceable PDFs, commercial blog posts, interview-preparation pages, generic product pages, and search snippets were excluded from evidence.
- Reddit and secondary summaries were not used for final claims.
- Papers whose only relevance was general LLM inference throughput were excluded unless they supplied a direct fairness, agent-program, or heterogeneous scheduling baseline.

## Artifact And License Verification Notes

- τ-bench current repository: MIT; code/data present. The July 2026 v1.0.1 `banking_knowledge` grading change makes cross-version scores non-comparable.
- AgentDojo: MIT; code and installable package present.
- RedTeamCUA: Apache-2.0; benchmark/code present; VMware/AWS plus web-service setup is heavy.
- OffTopicEval: MIT; code/data present.
- VTC artifact: Apache-2.0; code present.
- MARS preview: Apache-2.0; replay and OpenHands paths present; repository states full experiment reproduction is still coming, targets datacenter GPUs, and reports testing on H100/H200.
- CORA: repository contains only a README and states code, benchmark and model will be available later.
- FinHarness: no official code link found on the arXiv record or title-specific search.
- ToolChain-CRC: no official code link found on the arXiv record or title-specific search.
- Autellix: no official code link found on the arXiv record; MARS includes a PLAS-style reimplementation.
- SAGA: no official code link found; paper metadata indicates HPDC 2026.
- Justitia and H-MAS: no official reusable code link verified.
- Vera: repository code and benchmark are present, but no license text or GitHub license badge was visible.
- GuardAgent: code and dataset path are public, but no repository license was visible.
- ShieldAgent: project page is public; reusable source/license was not verified.

## Unknowns

- Papers not accessible: no critical final paper was inaccessible; several artifacts were unavailable.
- Venue status not verified: FinHarness, CORA, ToolChain-CRC, MARS, Justitia and Vera are treated as arXiv/preprint records unless an official proceedings page was found.
- Missing benchmark details: exact redistribution rights for Vera-Bench, GuardAgent datasets, ShieldAgent-Bench and future Phone-Harm.
- Missing baseline details: official FinHarness and ToolChain-CRC implementations; full MARS reproduction scripts; official SAGA/Justitia/H-MAS code.
- Novelty uncertainty: absence of a combined paper is a screened-corpus result, not an exhaustive proof. A literature monitor should watch agent serving, guardrail systems, and conformal action control through G2/G3.

## Handoff Notes

- For writing: do not draft novelty or “first” claims yet. Cite individual mechanisms conservatively and keep the contribution boundary at the intersection.
- For idea optimization: if the MVE shows no verifier bottleneck, pivot to hard capability gates plus recovery protocol or verifier-service optimization; do not add a more complex learned scheduler.
- For direction scouting: monitor new work combining action guardrails with queueing, fairness, overload control, or multi-tenant service.
- For experiment design: use the G2 packet in `papers.md`; start with pinned τ-bench plus AgentDojo and trace replay on the 4090D.
- For review: challenge any gain that is not measured at matched dangerous-action execution, identical capacity, identical hard-set semantics, and per-tenant tail/fairness reporting.
- For pipeline orchestration: recommended next state is `experiment_planning` with gate `G2_conditional`; this skill intentionally did not edit `ccfa.yaml`.
