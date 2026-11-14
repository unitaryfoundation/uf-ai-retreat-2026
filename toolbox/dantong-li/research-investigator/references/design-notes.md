# Design notes: provenance, adaptations, user requirements

Read this when you review or adapt the skill. A run does not need it.

## 1. Source basis

Primary source: Y. Cai, V. Gupta, Y. Jiang, C. Liaw, A. Mehta, G. Velegkas, D. Wang, "Cogentic:
Multi-Agent Orchestration for Automated Proof Discovery", arXiv:2609.40324v2 [cs.AI], 1 Oct 2026.
Harness: §2 (Figure 1, §§2.1–2.5), pp. 2–5. Problem prompts: Appendix A, pp. 15–18. "Lnnn" is a
line in the plain-text extraction of v2 used to build v6.

The paper gives an architecture and five problem prompts. It publishes no role prompts, scheduler
or file formats; all prompts, schemas and `scripts/ri.py` here are original. Its results were
checked by domain experts (L19–20, L236); nothing produced by this skill inherits that assurance.
Appendix A shows what the paper's orchestrator receives: one precise problem per run, at most an
open construction target shaped by a known bound (A.5), never a broad direction. Hence the outer
layer (§2).

| Paper mechanism | Lines | Where in v6 |
|---|---|---|
| Orchestrator: tracks state, partitions prover slots across directions, spawns summarizers, evaluates verifier consensus, manages record and ledger | L103–105, L136–138 | SKILL.md; proof-lane.md allocation; `ri.py` |
| Orchestrator does no derivations; orchestrator and advisor hold no mathematical opinion | L137–138, L216–218 | I1; opinion-free PLAN |
| Direction = a claim, a counterexample search, or repair/finalize; prover told what, not how | L163–168 | prover.md: PROVE, DISPROVE, SPECIAL-CASE, REPAIR |
| One independent summarizer per prover; selective; suggestions; long documents by path | L170–177 | summarizer.md; allocation rule A10 |
| Individual + cross-draft verification; accept only if both pass; adversarial stance | L144, L179–185 | verifier.md; I3 (counterexamples too) |
| Record of attempts pooled by target, with method and failing objection | L189–192 | lanes/Qxx/record.md, grouped by direction target (`ri.py record`) |
| Ledger: confirmed fragments → auditor → isolated re-check → reuse without re-proof; dead ends | L194–199 | ledger-auditor.md (dead ends as fragments); verifier ISOLATED; I4 |
| Process advisor: run-wide logs, repeated mistakes, verifier blind spots, instructions, allocation advice; separate because orchestrator context is scarce | L201–216 | process-advisor.md (advice per lane); instructions.md; I7 |
| Literature reviewers: background first; re-dispatched when attempts stall at the same step | L132–133, L139–141 | literature-reviewer.md SURVEY, TARGETED; `stall` event (its numeric trigger is v6's) |
| Rounds until a draft clears or the budget runs out | L154–156 | proof-lane.md state machine; `lane-budget` event |
| After a clear, explore remaining avenues, then terminate; comparator → formal writer → final audit; self-contained output | L220–229 | `top-accepted`; focused delivery, then the program continuation (post-clear rounds only with `--after stop`); comparator.md; writer.md; verifier PAPER |
| Needs only a problem statement; works until a paper exists | L35–37 | lane statement; `focused` mode |
| Appendix A style: background first (L911, L929, L992); "prove or disprove" (L1001); fallback 3 → 4 (L982–984); lower bound first; against 2 − Ω(1/n) the ideal is 2 − O(1/n) (L1015–1024); solution class (L1026–1027); mild assumptions removed later (L988–990, L1006–1007); literature depth (L935–936, L1032–1033) | L881–1035 | lane statement template; ladders (frontier-method.md) |
| O(100) calls per problem, O(1000) for the hardest | L32–35, L92–94 | runtime.md: one lane ≈ one problem |
| Expert checking; output outpaces human reading; formalization | L607–620 | I5; assurance profile; HUMAN_AUDIT_PRIORITIES |

Reading decisions. The Figure 1 caption (L127–129) says an advisor writes briefings; §2.1
(L170–174) says summarizers do. v6 follows §2.1. "Verifier consensus" (L136) is read as the
AND-gate of §2.2, not a vote. A.4 asked for factor 3 with 4 as fallback; the result was 3.52
(L306, L492–498). An intermediate rung was the real outcome, so v6 labels every rung reached, and
the significance rubric cites this constant improvement.

## 2. Adaptations (not in the paper)

| Adaptation | Why | Where |
|---|---|---|
| Outer frontier layer: sources → model card → transfer audit → proposals → vetting → lane statements → renewal | The paper starts from a precise statement (L36); the user starts from a direction, a ZIP and a key difference (chat L902, L1219) | program.md; frontier-method.md; investigator.md |
| LANDSCAPE task in the first wave; PROPOSE waits for it | The bundle may miss the closest work on T + X; Appendix A asks for the landscape first (L935–936, L1032–1033) | literature-reviewer.md; program.md |
| `user-notes` sources; `user-input` event with fixed routes; investigator EXPLAIN | The user puts ideas and the key difference in the ZIP (chat L1219) and sends hints later; I1 forbids the orchestrator to interpret them | program.md; investigator.md; I12 |
| Investigator sets agenda and lane slots; orchestrator plans rounds opinion-free | Someone must choose questions, while L216–218 holds inside lanes | SKILL.md; proof-lane.md |
| Skeptic: MODEL-, QUESTION-, CLAIM-GATE | User asked for a red team (chat L482; diagrams). Verifiers judge correctness only; novelty, triviality and significance need an owner other than the proposer | skeptic.md |
| Neutralization (transfer-audit step 3b, SURVIVES-BY-REDUCTION, MODEL-GATE check 7); a light gate (`--kind transfer`) on SURVIVES rows and simulation edges | A broken proof is not a broken bound: padding or simulation can make X useless (plain lookahead is the classic case). These rows answer the user's main question, so one reviewer's verdict is not enough | frontier-method.md; skeptic.md; verification.md |
| Scout: EXPLORE (opening ANCHOR at k = 0), SANITY, WITNESS, BUILD, CERTIFY | User's coding agent. Exact small cases are the cheapest conjecture source and falsifier, and do not share LLM reading errors | scout.md |
| 2–4 independent PROPOSE lenses, then SELECT; BREADTH review in a fresh context | Applies the paper's independence (L173–174) to brainstorming; prevents anchoring | investigator.md |
| Ladders R1..Rm plus D as lane statements | Generalizes A.4/A.5; each rung is a result; D keeps "prove or disprove" | frontier-method.md |
| Allocation rules A1–A11; D slots keyed to the skeptic's plausibility, or N ≥ 4 | The paper allocates without opinion (L136–138) but states no rule. The D share follows the skeptic's forecast, never the orchestrator's (L217–218) | proof-lane.md §3 |
| Per-lane round close: BRIEF r+1 waits for round r's auditor, ISOLATED reviews and advisor | The next round starts from what the last one wrote down (L130–132, L154–156); lanes have no global barrier, so other lanes use the free slots | proof-lane.md; SKILL.md |
| Fidelity check: MATCH / WEAKER / DIFFERENT_MODEL, with `assumes=<text>` | A prover can prove a weaker statement and pass on its own terms. A mild assumption (L988–990) stays MATCH but shows in every label until a HYPOTHESIS-AUDIT successor removes it | verifier.md; verification.md; I3 |
| Severity scale and verdict rule | The paper gives a stance, not a scale; makes "passes both" decidable | verification.md |
| ADJUDICATE one disputed objection | Under an AND-gate one mistaken objection blocks forever; no vote is added | verifier.md; `ri.py objection resolve` |
| SALVAGE review of gap drafts; SECOND-INDEPENDENT review for one-draft rounds; SANITY and WITNESS checks | Every draft is read by a verifier (L181) and confirmed lemmas feed the ledger (L194–197), but a gap draft has no full theorem. Cross-draft review needs two drafts; computation catches false claims cheaply | verifier.md; proof-lane.md |
| Isolation L2/L1; seven labels; assurance profile | Hosts may lack fresh contexts; the paper uses "verified" for agent checks (Figure 1) and expert checks (L236) alike | I2, I5; runtime.md |
| Continuation: I9, I10, PAUSE, sticky STOP | The paper may keep exploring after a first success before it terminates (L222–223); running until stopped is the user's requirement (§3). Many hosts end a turn on a text-only reply. Only the user lifts a STOP; a deleted STOP cannot be restored | SKILL.md; runtime.md §5–6 |
| Focused mode: consolidate at once after the target rung, then continue as a program built on the result (v6.4 default); with `--after stop`, at most 2 rounds on stronger rungs, then end | The paper explores remaining avenues after a clear, then terminates (L222–224). The user wants runs to go on automatically (2026-10-06), and in a parity benchmark the post-clear rounds chose follow-ups narrower than the paper's | SKILL.md §5; program.md §2.1, §3 |
| State CLI `ri.py`: default Assignments, `ingest`, run lock | Orchestrator context is scarce (L211–216); hand-written packets drift and can break independence. Hashes bind reviews to frozen files; a manual fallback exists | ri.py; state.md |
| Renewal events, successor operators, tiers | The paper stops after one problem; a program must choose what follows an accept, refutation or stall | program.md; frontier-method.md |
| Quarantine; imported results | Reuse without re-proof (L197–198) compounds errors; withdrawals must propagate | verification.md; I4 |

## 3. User requirements

Sources: the six user prompts in the chat export `ChatGPT-Research agent
recommendations-20261003-0005.md`, and later instructions recorded in the v5.1 design basis.
Assistant suggestions in the export are design input, not requirements (I12).

| Chat line | Requirement | How v6 meets it |
|---|---|---|
| 12 | Autoresearch from directions or references with a capable team, on the user's own harness and API bridge | `program` mode; automatic dispatch; no product names; never changes model, endpoint or settings |
| 482 | Idea → thorough literature review → brainstorm-and-validate loop until publishable results → report; red-team and coding agents dispatched automatically | SURVEY, LANDSCAPE, TRANSFER-AUDIT; PROPOSE/SELECT; skeptic; scout; lanes; milestones; significance rubric |
| 484 | No explicit prompting of subagents | I11; `ri.py task new` builds packets and default Assignments |
| 670 | ASD-STE100-style explanations with diagrams and clear logic flow | Short imperative sentences; defined terms; progress.md style rule and Picture slot; assets/guide.html. No formal ASD-STE100 compliance is claimed |
| 718 | No diagrams without explanation; answer the question | Answer first; every diagram has text |
| 902 | "Now allow resource X": all bounds, constructions, better protocols; an investigator proposing conjectures; Cogentic as a skill | Model card for X; frontier map with threshold, saturation, trade-off; transfer audit with neutralization; lenses; `focused` mode for clear claims |
| 1219 | Topics, ideas, references and key difference as a large ZIP; Cogentic roles with minimal adaptation; outer loop at designer's discretion; full topology diagram | Safe ZIP intake (`ri.py intake`); key difference verbatim in contract.md, also from a user-notes file; user ideas as seed cards; inner lane as in the paper; guide.html |
| later | Framework-independent; run until stopped; a ZIP run must not end at a quick audit | No product names; I9, I10, PAUSE, sticky STOP; exhaustion only after BREADTH |
| 2026-10-06 | A run that starts from one precise claim keeps going after delivering it | `init --after continue` (default); `ri.py mode --to program`; the continuation opening (program.md §2.1); class-wide TIGHTNESS first |

## 4. The user's diagrams mapped to v6

In assets/source-diagrams/: A = research-loop.png, B = supervisor.png, C = research-system.png.

| Node or loop | v6 role, file or mechanism |
|---|---|
| A Your input: goal, references, limits | contract.md; user-notes; `user-input` event; limits; STOP/PAUSE |
| A Read the papers | literature reviewer SURVEY, LANDSCAPE → sources/ |
| A Develop an idea | investigator PROPOSE/SELECT → questions/; QUESTION-GATE |
| A Run the tests (fair baselines, raw results) | scout → scout/; lane provers; fairness in CLAIM-GATE |
| A Check the evidence | verifiers; SANITY/WITNESS; DISPROVE directions |
| A Decide what is next | round PLAN; lane events → RENEW |
| A loop "return to the required step" | stall → TARGETED review; RENEW successors; REPAIR directions (I8) |
| A exit "evidence sufficient or limit reached" → report | milestone report, lanes continue; run ends only per I9 |
| A "A paper is not the success condition" | I5; record.md; exclusions; dead ends in progress.md |
| B You | user; contract.md; I11 |
| B Research supervisor | orchestrator (scheduling, I1) + investigator (questions) |
| B Literature, Method, Coding, Red-team agents | literature reviewer; summarizer + prover; scout; skeptic and verifiers |
| B Shared record; evidence returns to supervisor | run directory; result.md → `ri.py ingest` → control-loop integration |
| B "A valid objection must change the next research action" | I8 |
| C1 User input (topics, references, key difference, ZIP) | `ri.py intake`; contract.md; sources/index.md (user-notes rows) |
| C2 Research orchestrator | SKILL.md orchestrator; strategy goes to the investigator; "stop at satisfactory results" replaced by I9 |
| C3 Memory and knowledge base | run directory: source cards, model.md (definitions, notation), record.md, ledger.md; read by path (I7) |
| C4 Investigator | MODEL/PROPOSE/SELECT/RENEW/BREADTH/EXPLAIN; map.md; story.md |
| C4 Summarizer (reads papers) | Name clash: literature reviewers do this; v6's summarizer is the paper's per-prover briefing writer (§2.1) |
| C4 Prover/Constructor (multiple) | parallel provers; scout BUILD |
| C4 Verifier (with cross-review) | INDIVIDUAL (SALVAGE for gap drafts), CROSS-DRAFT (SECOND-INDEPENDENT for a single draft), ISOLATED, PAPER, ADJUDICATE |
| C4 Skeptic/Red team | skeptic gates; DISPROVE directions; SANITY |
| C4 Coder/Experimenter | scout |
| C5 Integration and next-step planning; C6 "Satisfactory results?" | orchestrator integrates mechanically (`ri.py ingest`); investigator SELECT/RENEW decides; process advisor advises; a satisfactory result is a milestone, not the end (I9) |
| C green loop "new questions and directions" | events → RENEW → QUESTION-GATE → new lanes |
| C red loop "issues, counterexamples, incomplete proofs" | REPAIR, ADJUDICATE or reformulation (I8); `ri.py exclude` → `refuted` |
| C6 steps A–F | A–B opening steps 1–4; C PROPOSE/SELECT/gate; D PROVE; E VERIFY + SANITY; F CLOSE + RENEW |
| C7 Final output | progress.md; reports/ (agent-checked); map.md, story.md; scout/; log.jsonl, tasks/ |
| C Example workflow; key adaptations | `program` default; status from a fresh `ri.py status` after reconciliation; adaptations adopted |
| C When to pause for user input | I11: ambiguity → labelled model variants; cost, installs, ethics, out-of-scope → ask; choice of direction → investigator; user messages mid-run → `user-input` routes; submission is outside the skill |

## 5. Known limitations

- **Shared bias.** Reviewers from one model family can share blind spots; separate contexts give
  procedural, not statistical, independence. Mitigations: different gate angles, scout checks,
  advisor blind-spot rules, and a profile that names the model family.
- **Agent-checked is not proved.** Only a proof assistant (machine-checked) or a human expert
  (expert-verified) gives more. HUMAN_AUDIT_PRIORITIES direct the expert.
- **Novelty search is bounded.** "Not found in search S" reports coverage, not novelty. Without
  web access only the bundle is searched.
- **Host continuation.** A skill cannot create a background process. Turns end, contexts compact,
  quotas run out. v6 checkpoints, says "interrupted" and resumes from the run directory.
- **Records are not proof of execution.** Hashes catch edits and stale reviews; they are not
  tamper-proof and do not prove isolation.
- **Cost and scope.** More roles than the paper; O(100) calls is a reference point, not a promise.
  Scope is mathematics and theoretical CS.
