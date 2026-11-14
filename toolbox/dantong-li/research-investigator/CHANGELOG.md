# Changelog

## v6.4 (2026-10-06), after an offline Cogentic parity run
- A focused run no longer ends at its delivery. Intake records "After delivery: continue" in
  contract.md (the default; `ri.py init --after continue|stop`), or "stop" only when the user asks
  for this claim only or sets a limit that the delivery reaches. `--after stop` needs
  `--stop-quote`: a phrase of at most 200 characters, copied from the user's request, that limits
  the run ("only this claim", "then stop", "nothing else"); `ri.py` refuses anything else. In
  two v6.4 parity runs the orchestrator read "Show that ..." as "this claim only", the second
  time quoting the whole request because it contained "the only reference". Run directories from v6.2 and
  v6.3 have no such key and behave as stop. The user's words: "keep going, that's how it can run
  automatically."
- With continue, focused mode still delivers fast, but spends no extra rounds on stronger rungs or
  "Stronger (after R1)" items: it closes the lane at the target rung and consolidates at once (or
  delivers the refutation or failure report). Then `ri.py mode RUN --to program --reason-file
  <file>` converts the run (refused under STOP or PAUSE; a repeat changes nothing; intake never
  re-runs) and records `converted` in state.json.
- Continuation opening (program.md §2.1): one investigator RENEW on the delivered result, whose
  successors are SELECT's first candidates. It picks its operators by what was delivered (an
  open target gets After-STALL first) and writes the map grid and story.md's first headline,
  which a focused run lacks. Then a sweep of 2–4 PROPOSE lenses (OBVIOUS-CONSTRUCTION and
  ADVERSARY first), SELECT, gates, lanes, renewal and BREADTH as in any program (I9). `ri.py
  status` shows these steps instead of the focused or opening hints.
- The continuation is in scope and not optional: a focused run with continue gets "In scope: the
  claim; after its delivery, research questions built on the delivered result" in contract.md,
  and `mode --to program` adds a Continuation line under Scope boundaries and says the run is
  not finished. I9 now says a long turn or a large context is not a host limit. A parity run had
  scoped its contract to the single inequality, called the continuation optional, and ended at a
  "turn limit" right after its continuation RENEW proposed the class-wide converse.
- TIGHTNESS is class-wide first: the converse for every algorithm, protocol or mechanism with the
  same constraints, information, incentives and resource accounting; the converse for the specific
  object is the fallback rung R2. In the offline parity run the outer loop never ran, and the
  follow-ups chosen after the clear were narrower than the paper's.
- Tests: tests/test_v64_continuation.py (28 tests; 267 in all). Older focused-ending tests pass
  `--after stop` and keep testing the v6.3 behaviour.

## v6.3 (2026-10-05), after six runs on real research packs (Codex and Claude hosts)
Speed to first proof (Cogentic parity)
- Fast start (program.md §6.1): a claim the user states verbatim (the focused claim, or one
  program seed) is copied as R1 with "D: the negation of R1" and its lane opens at once; round
  1's briefings run beside a light QUESTION-GATE, and its provers go on ADVANCE. SURVEY,
  LANDSCAPE, ANCHOR and MODEL run in parallel and act at the next round boundary. R1 is never
  renumbered; MODEL adds weaker rungs below and lists stronger variants for a follow-up
  question. Real runs had spent about two hours vetting before any prover started.
Waves and time
- Workers return within about 45 minutes by default; scouts compute at most 20 minutes (5 per
  run). Scout's "grow until the time limit" had no limit, and one scout held a blocking wave of
  five finished results for over an hour.
- Blocking-parallel hosts never put a scout or SURVEY in a wave with gates or reviews.
Hosts and reporting
- Manual records are written as UTF-8 without a BOM (PowerShell 5.1 redirection garbled
  symbols). The Python check runs in the shell the run will use (a sandbox can hide a per-user
  Python).
- "How I read your request" opens with 2–3 plain sentences in the user's terms before any model
  IDs.
Refutations of the literal claim (offline Cogentic parity benchmark)
- A witness that works only under a literal reading the user plausibly did not intend (a boundary
  convention, a definition that conflicts with another, a case the wording excludes) refutes that
  reading only: the skeptic returns REFORMULATE with both readings, and a refutation gets one
  limited RENEW that applies READING first (frontier-method.md §10). Its successor is the focused
  claim and runs as a fast start; the literal refutation is reported at once. In the offline
  benchmark run, every agent saw that a boundary guard in the source's definition falsifies the
  literal claim, but the skill consolidated that refutation after 24 minutes and never attempted
  the intended theorem.
- Every counterexample, a skeptic's witness included, needs INDIVIDUAL, a cross review and WITNESS.
- Tests: test_ri.py ran `unittest.main()` before its last four classes, so running the file
  directly skipped 31 tests; discover now runs all 239.
Results found at gates (round-6 audits)
- A new argument a skeptic writes at a gate is SOLVED (or `solved: Rj` for a lower rung): ingest
  freezes it with the skeptic as author, and INDIVIDUAL and SECOND-INDEPENDENT review it at once
  in a gate-only round outside the lane cap. KILL(IMPLIED) needs a named locator, and its fact is
  certified only for a named citer (in focused mode, the user's claim itself). `q set` refuses killed or parked while such a candidate is
  under review or once R1 is accepted. Real runs had filed their best proofs as killed questions.
- REFORMULATE, DEMOTE and KILL(IMPLIED) log a `question-verdict` event (SELECT or MODEL handle it
  before the first SELECT); a RENEW below the lane cap returns a successor or a reason.
First prover sooner
- Seeds follow the user's stated priorities (contract.md "From your notes", verbatim); MODEL writes
  an R1 for at most 2 primary direction seeds; one batched full seed gate runs after the
  MODEL-GATEs. Intake reads guides, handoff notes, chat exports and README targets as user-notes.
  `ri.py status` has a no-prover watchdog. All four real-pack runs stopped with no prover.
- Only a `settles` holds lanes; a `bridges` is context. `ri.py file-cards` files cards and logs
  new-source, except for bundle files MODEL already read.
- MODEL has an opening budget (gates for M0, M1 and 2 seed variants; 4 audits; 2 scouts); transfer
  rows are gated only when cited; only the latest request list is live; the outer share is a
  minimum. Opening audits had taken 22–39% of tasks.
- Ingest files PATCH verdicts verbatim as new model IDs (definitions only; bounds go into gated
  arguments); the apply-verdicts MODEL runs only for DEGENERATE, at most once.
Waves, packets and time
- Background+notify whenever offered; critical-path tasks never share a blocking wave with long
  tasks; running workers get no messages (`dispatch.md`).
- Default Assignments for MODEL, PROPOSE, SELECT, MODEL-GATE, SURVEY, LANDSCAPE, TRANSFER-AUDIT,
  EXPLORE and a comparator-free writer; a warn-only I1 lint; a QUESTION-GATE gets the card without
  its Tier and Skeptic lines. The never-include list voids a gate and nothing else does;
  quarantine needs a §9 reason code.
- Every packet carries a Time line (provers 90 minutes, lane verifiers 60, scouts 20 of compute).
  Workers stop only their own processes and keep temporary files in their task directory.
- Manual fallback: closed vocabularies, SHA-256 freezing, and a per-loop checklist that mirrors
  `ri.py status`. Both Codex runs had no Python.
Verification and delivery
- Hashed attachments for computer-assisted steps; one candidate per INDIVIDUAL, SALVAGE and
  SECOND-INDEPENDENT task; a model-level fact that rests on a new argument needs a second
  ISOLATED pass.
- The accepted proof goes to `reports/` at once; the comparator is skipped when it has no choice;
  the focused CLAIM-GATE always runs, beside the comparator; a revision that only inserts the
  PAPER fills needs no DELTA PAPER; the writer may add no remarks.
Reporting and method
- progress.md is rewritten whole from intake on, with a lint (`check --progress`); I5 adds
  "improved", like-for-like comparisons and `cited (Sxx; ...)`.
- A Frame line (RESOURCE-CURVE, ON-OFF, COMBINATION) for key differences that are not an amount;
  cards name their gap step; value cells aim at the tight value; every sweep has a constructive
  lens; an exact finite-parameter optimum is mathematics, gated under I3.

## v6.2 (2026-10-05), after two live end-to-end runs
Validation: focused (a correct agent-checked proof plus an exact finite-B trade-off); program (40
tasks, 3 model variants, agent-checked separation results, honest QUALIFY/TRIVIAL claim gates).
Host safety and paths
- Host-safe names: verifier reports are `review.md` (a legacy `report.md` is still read); the
  advisor writes `advisor-log.md` (a legacy `analysis.md` is still read). Workers name files
  only as their role prompt says (a host refused exactly report.md, analysis.md, summary.md and
  findings.md); a refused write goes in the reply, which the orchestrator saves as
  `tasks/Txxx/stdout.md` and files.
- The dispatch message names the canonical files a worker owns. RUN is the same absolute path
  every time; `ri.py` handles long Windows paths, but RUN stays short.
- Intake types `user-notes` by file name (leading word README, notes, brief, idea, todo, plan,
  questions or direction, or `notes` joined by - or _; never paper-like names); other top-level
  .md/.txt is `text`; a paper or literature summary typed user-notes is a source. 1–6 source
  families.
Packets and roles
- The never-include check matches exact paths; non-default roles get a Return line; one ISOLATED
  task may check several candidates; literature results are labelled `cited (Sxx; ...)`; writer
  length follows the result, and its header labels the results, never the document (the
  reports/ copy is named agent-checked only after PAPER passes); state.md lists outputs by role.
Gates, lanes and limits
- Gate batching (models, questions, results of one source, ISOLATED candidates). Gate-only
  rounds for a REFUTE-SKETCH and for a requested KILL(IMPLIED) argument; `kind transfer` covers
  any model-level fact; acceptance waits for a dispatched SANITY or WITNESS check.
- Per-lane `--budget`; focused endings consolidate without RENEW; `event --handled --by` names
  the handling task (RENEW, SELECT, BREADTH, comparator); light gates via `--light`. Advisor-due
  rules skip ended lanes, and no advisor runs when no lane will run another round. Under a finite
  limit, consolidation (about 4 calls) comes first once the allowance nears it.

## v6.1 (2026-10-05), after the round-3 evaluations
Control and resume
- STOP is sticky: "continue the research run at RUN" lifts only a PAUSE. With STOP present the
  orchestrator dispatches nothing and tells the user the lift phrase; `ri.py resume --stop
  --reason-file` removes it. STOP and PAUSE match any case and extension (STOP.txt). One resume
  procedure (runtime.md §6); status questions are answered after reconciliation.
CLI (`ri.py`)
- `task new --start`, default Assignments with the never-include lists enforced, `--redo`,
  `ingest`, safe `intake --archive`, a run lock, `-file` flags for free text, abspath paths.
- Line-oriented verifier header; objection IDs unique per review; exclusion and accept checks;
  dead ends as negated fragment lemmas; lane holds; persisted slots and plausibility.
- Review fixes: `accept` also refuses a contradiction with an accepted refutation whose exclusion
  is pending; a blocked WITNESS task or `init --no-code` waives the WITNESS gate; PAPER and RENEW
  packets name the writer's trace.md and TARGETED reports; `ledger add --statement-file`; late
  drafts get SECOND-INDEPENDENT; ingest reads files with a byte-order mark; scout mode ANCHOR is
  only an EXPLORE title.
Lanes and verification
- Allocation rules renamed A1–A11; one D rule; round-close work feeds the next round's briefings.
- SALVAGE review of gap drafts; counterexamples need the cohort's CROSS-DRAFT; allowed
  assumptions tracked as `assumes`; light gate for transfer rows and simulation edges; record
  grouped by direction target; contradiction rule.
Outer layer
- Neutralization step in the transfer audit (SURVIVES-BY-REDUCTION) and MODEL-GATE check 7;
  LANDSCAPE literature task; baseline ANCHOR scout; like-for-like anchors; NEGATION-IMPLIED and
  strictness checks; ADVERSARY lens; scout CERTIFY; user notes and mid-run user input routes.
- Focused mode has numbered steps and post-clear rounds (at most 2), then consolidation.
- program.md split into program.md (orchestrator) and frontier-method.md (workers); the worked
  example moved to worked-example.md (deterministic paging with lookahead, symbolic IDs).
Reporting and packaging
- Earlier progress.md rewrites ("How I read your request", portfolio, on stop) with a Picture
  slot and a style rule. Writer may expand routine steps; comparator presents one proof.
- evals/ moved out of the skill to research-investigator-dev/ (eval text leaked into a test run).

## v6 (2026-10-05), compared with v5.1
Structure
- Two layers: a new outer frontier program around the Cogentic proof lane, which stays close to
  the paper. Invariants I1–I12 are stated once in SKILL.md; the continuation rule is stated once
  (v5.1 repeated it 20+ times).
- Role prompts moved from references/roles.md into prompts/*.md, with a shared _envelope.md and a
  short result.md contract.
- References are now program, proof-lane, verification, runtime, state and design-notes. They
  replace intake-and-model, research-program, roles, state-schema, workflow-schema,
  topology-contract and design-basis.
Roles
- New: skeptic (MODEL-, QUESTION-, CLAIM-GATE) and scout (EXPLORE, SANITY, WITNESS, BUILD). The
  investigator has five modes: MODEL, PROPOSE, SELECT, RENEW, BREADTH.
- Counterexample work is a prover direction (DISPROVE), as in the paper. The scout replaces the
  separate counterexample researcher and experimenter.
- Paper fidelity restored: the orchestrator allocates directions inside a lane without
  mathematical opinion. In v5.1, investigator priorities drove that allocation.
Outer layer (new)
- Source cards, model card with anchors and simulation lattice, frontier map, transfer audit,
  question cards with ladders and tiers, story, proposal lenses, significance rubric, portfolio
  rules, renewal events, successor operators, exhaustion rule, one illustrative worked example.
Inner lane and verification
- Appendix-A-style lane statements; record of attempts grouped by target; stall trigger for a
  targeted literature review; lane budget.
- Verifier: adversarial stance, checklist tags, severity scale, verdict rule, fidelity check;
  SECOND-INDEPENDENT and ADJUDICATE scopes; scout sanity checks; assurance profile.
- A lemma needs one ISOLATED review (two if load-bearing); v5.1 asked for three reviews.
- Labels: "agent-checked" replaces "agent-verified"; numerical evidence and self-checked added.
State and runtime
- scripts/ri.py writes state (IDs, sha256 freezing, gate checks, record, ledger, status with
  suggested next actions). It replaces the audit-only research_state.py and workflow_state.py.
  Manifests, receipts, sequence checks and workflow transitions are gone. v5.1 runs are not read.
- Stateless orchestrator: capability card, L2/L1 isolation, turn-keeping, STOP/PAUSE files,
  resume reconciliation, optional deterministic driver.
Documentation
- design-notes.md cites arXiv:2609.40324v2 (1 Oct 2026; §2 pp. 2–5; App. A pp. 15–18) and maps
  the user's diagrams in one table (no connector-by-connector audit). assets/guide.html replaces
  topology.html. evals/scenarios.md (now in research-investigator-dev/) keeps scenarios 1–11 and
  adds 12–18.
