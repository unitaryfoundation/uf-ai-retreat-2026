# Frontier program: orchestrator operations

## 1. Purpose

Your outer-layer operations, all mechanical (I1): route worker outputs by their fields; never
judge the mathematics. The workers' method and templates are in
[frontier-method.md](frontier-method.md), which you do not read.

## 2. Opening (program mode)

[parallel] = dispatch together, up to K.

1. **Intake.** SKILL.md §5, steps 1–3 (user notes, key difference, seed questions). A `user-notes`
   file that is clearly a paper or literature summary is a source. **Seeds:** copy the user's
   priorities, success criteria (what counts, what does not) and wording of the wanted result into
   contract.md "From your notes", verbatim with paths. Register seeds in that order with
   `q add --priority`: each stated conjecture or precise question, and each named direction or
   next-work item as a draft seed with no ladder. Items the notes call secondary or optional are
   secondary seeds; with no stated priority, the first four in the notes' order are primary, the
   rest secondary. Never park a seed for missing specification: MODEL instantiates standard
   variants. **An earlier research program** (versioned reports, status labels, a next-work list):
   its guides, handoff and next-work files are user-notes; each open item ("determine" and
   "optimize" included) is a seed with lineage "prior program"; its reports form one family, whose
   SURVEY starts from the guides and cards only results they mark load-bearing. Group the other
   sources into 1–6 families so the first wave (SURVEYs, LANDSCAPE, ANCHOR, one light seed gate)
   fits in K; else merge the smallest families. The family holding the baseline results is the
   **baseline family**. Then rewrite `progress.md`: what the bundle holds, your reading of the
   user's intent, and the opening plan.
2. **[parallel]** A literature reviewer SURVEY per family; one literature reviewer LANDSCAPE; one
   scout ANCHOR (`--mode EXPLORE --title "ANCHOR <source>"`, the Assignment naming the baseline
   source file); one light QUESTION-GATE on the primary seeds stated as claims (seed fast start,
   §6.1; on a blocking host, in a short wave of its own).
3. **Investigator MODEL** once the baseline family's card is filed. Its default Assignment names
   other families' raw files as "uncarded", the user-notes, `sources/bounds.md`, returned
   LANDSCAPE and ANCHOR outputs and seed gate verdicts, and any literature result returned before
   it (MODEL handles it: `event --handled ... --by` the MODEL task). While MODEL runs, fill free
   slots with returned literature tasks' `follow_ups`: at most one per family, oldest first,
   within the request cap (on a blocking host, never in MODEL's wave: runtime.md §3). Later
   `follow_ups` go by path to the next SELECT or RENEW, which re-lists in `tasks_requested` those
   it wants.
4. What MODEL's ranked `tasks_requested` lists, within its opening budget (investigator.md MODEL):
   skeptic MODEL-GATEs, at most 4 TRANSFER-AUDITs, at most 2 scouts (on a blocking host, the
   MODEL-GATEs in a short wave of their own: runtime.md §3). After a PATCH, audits and scouts not
   yet dispatched target the patch's model ID (§5.2).
4b. **Seed gate.** Once every MODEL-GATE has returned, one batched full QUESTION-GATE on the
   primary seeds that have an R1 (`--question Q01,Q02`); its packet names the filed patches.
   The first ADVANCE opens as the foothold lane (SKILL.md §5 step 6). Secondary seeds are gated
   only if SELECT picks them.
5. **Model reading** (SKILL.md §7). "How I read your request" copies the investigator's
   `reading.md`, marked provisional, then adds each MODEL-GATE verdict line and its
   `corrections` lines verbatim under the model they correct. If LANDSCAPE reported `web: no`,
   add "Frontier from the supplied bundle only."
6. **Proposal sweep** once every MODEL-GATE and LANDSCAPE have returned; never wait for audits,
   scouts or an apply-verdicts MODEL. Dispatch investigator PROPOSE tasks, one lens each,
   together (§5.1).
7. **Investigator SELECT** when the sweep returns. It also handles the events logged so far; mark
   them handled `--by` the SELECT task. Copy its `select.md` section "For the user" (the
   portfolio) into `progress.md`.
8. **[parallel]** Skeptic QUESTION-GATEs on the selected questions (batching: §5.2).
9. **Open lanes** at the ready gate (§6), by SKILL.md §5 step 6 (foothold rule; never while a
   `settles` hit on that question is unhandled).

`ri.py file-cards` logs a card filed after MODEL as a `new-source` event (§7), unless its source
is a bundle file MODEL's Assignment named as uncarded.

### 2.1 Continuation opening (a focused run after its delivery)

A focused run with "After delivery: continue" becomes a program once its result is delivered (§3).
Reuse what exists: sources, model, frontier files, ledger, reports and scout tables. Never re-run
intake, SURVEYs or the opening MODEL.
1. **[parallel]** One investigator RENEW on the delivered result (`--title continuation`; `ri.py`
   writes its Assignment) and, if none ran and workers have web, LANDSCAPE. The RENEW applies the
   After-ACCEPT operators, TIGHTNESS first, or the After-REFUTE ones after a refutation (READING
   already ran). When only a weaker rung was accepted, or none (a failure report), it applies the
   After-STALL ones to the open target first (frontier-method.md §10). Its Assignment names, by
   path, the open stronger rungs, the "Stronger (after R1)" items and the parked questions
   written before the delivery. A focused MODEL writes no grid and no story.md, so the RENEW
   first writes the M1 map grid (frontier-method.md §3) around the delivered result, with its
   endpoints and transfer rows, and story.md's first headline. Its successor cards are not
   registered: they go to SELECT by path as its first candidates.
2. When the RENEW returns, a proposal sweep of 2–4 PROPOSE tasks (§5.1, continuation sweep): they
   see its grid, and their packets name the delivered result and its `renew.md`. MODEL only when
   the RENEW or a gate asks for it (for example a new model variant), then its MODEL-GATEs.
3. **Investigator SELECT** when the sweep has returned. It handles every event still unhandled
   (the delivery task handled the lane's own); mark them `--by` the SELECT task. Register its
   cards (§4); copy its "For the user" into `progress.md`.
4. Skeptic QUESTION-GATEs on the selected questions, lanes at the ready gate (§6), then renewal,
   queue-low and BREADTH as in any program (I9). The breadth-review lane-round count starts at the
   conversion.

## 3. Focused mode

SKILL.md §5 lists the steps. Until its delivery, focused mode skips the proposal sweep, SELECT,
BREADTH and queue-low. Intake records the **after-delivery choice** in contract.md ("After
delivery:", `ri.py init --after`): `continue`, the default, or `stop`, only when the user's words
ask for this claim only ("just prove X", "only this claim") or set a limit stated by the claim's
outcome ("stop when you have a proof"). Quote those words: `--after stop --stop-quote "<words>"`.
A request to prove, show, or prove or disprove a claim is not a request to stop after it; nor is
a precise statement, a single reference, or "no internet". A call, time or money budget keeps
`continue`: I9 ends the run when it runs out. A run directory from before v6.4 behaves as `stop`.
The **focused claim** is Q01, or the question READING created from it (`--parent Q01 --operator
READING`): the claim the user meant. A claim to prove or disprove opens by the fast start (§6.1);
an open "determine" problem needs the full ready gate (§6), with a full QUESTION-GATE (checks 1–5)
on the final statement. Events differ:
- stall, literature-hit: one RENEW limited to DESCEND, SPECIALIZE, or re-targeting within the
  claim; never SELECT. A `settles` that refutes the claim, or answers a contract asking whether
  the claim is known, is logged with `--lane Q01` (a hold), also before the lane opens. Any other
  `settles` is logged without `--lane`: provers keep working, and its path goes to the lane's
  next summarizers and the closing CLAIM-GATE. A `bridges` is context;
- a KNOWN verdict or `found: settles`: tell the user at once in `progress.md` §1 (locator and
  exact statement, formulas exact). A limited RENEW (only for a hit that holds the lane) then
  keeps the lane for an attributed proof or re-targets to the part the source does not cover;
- a lane kept after a settles finding: at most 2 more rounds: `ri.py q set RUN Q01 --budget
  <rounds used + 2>` (status prints "budget used/N");
- target rung accepted: with `stop`, at most 2 more rounds on the stronger rungs (paper §2.5),
  under the same budget line; in a fast start, on the "Stronger (after R1)" items as Q02 (SKILL.md
  §5 focused step 4). With `continue`, none: close the lane at the target rung (`q set --status
  resolved --rung Rt`) and consolidate at once; the stronger rungs and items wait for the
  continuation RENEW (§2.1);
- refutation: tell the user at once in `progress.md` §1 ("false as literally stated", with the
  witness). Then one limited RENEW applies READING (frontier-method.md §10): if the witness
  defeats only a literal reading, its successor re-targets to the natural reading and runs as a
  fast start. Consolidate a refutation only when that RENEW finds the witness defeats the
  intended claim, or when the refuted question was itself created by READING;
- top rung accepted, lane-budget, or a user limit: consolidate the strongest accepted rung
  (proof-lane.md §6), or deliver a failure report built from the record. Mark the acceptance,
  lane-budget, literature-hit and new-source events, and a READING question's `refuted`, handled
  by the delivery task (`ri.py event RUN --handled E# ... --by <comparator or writer task>`); no
  RENEW. Focused mode writes no story.md; `progress.md` says `frontier/` reflects the opening;
- **after delivery** (the manuscript passed PAPER, or the refutation or failure report is
  delivered): with `stop`, the run ends. With `continue`, say in `progress.md` §1 that the claim's
  result is delivered and that the run continues as a research program built on it. Then run
  `ri.py mode RUN --to program --reason-file <file>` (refused under STOP or PAUSE; a repeat changes
  nothing) and the continuation opening (§2.1). From then on the run is a program: I9 applies.

## 4. Filing and registration

- **Source cards.** `ri.py file-cards RUN Txxx` files each SURVEY or LANDSCAPE card as
  `sources/Sxx.md` with its row in `sources/index.md`. A `NEW-` card gets the next Sxx after a
  dedupe by arXiv ID, then DOI, then normalized title and authors. Of two cards for one source,
  it keeps the larger as Sxx and marks the other "duplicate of Sxx" in `sources/index.md`, never
  merging their texts. It appends each task's `bounds.md` rows unchanged to `sources/bounds.md`
  (`NEW-` names replaced by Sxx) and files the task's `raw/` downloads under `sources/raw/Txxx/`.
  Without Python, do the same by hand.
- **Transfer rows, edges, scout tables, patches.** The investigator integrates rows, edges and
  filed model patches at its next SELECT or RENEW; gate rows and edges by §5.4. File reusable
  scout tables and certificates under `scout/`.
- **New questions.** Register only SELECT and RENEW cards, under `tasks/Txxx/new/`. For each
  `new/N#-card.md`: `ri.py q add RUN --title ... --tier ... --model ... [--parent Qxx --operator
  NAME]`; copy the card to `questions/Qxx.md` and `new/N#-statement.md` to
  `lanes/Qxx/statement.md`; replace N# by Qxx in both. PROPOSE `cards.md` and BREADTH
  `breadth.md` are never registered; pass them by path to the next SELECT or RENEW. Nor are the
  continuation RENEW's cards: they go to SELECT by path (§2.1). Seed and focused questions are
  registered at intake; the investigator edits them in place.

## 5. Lenses and gate routing

### 5.1 Lens choice (lenses: frontier-method.md §8)

- **First sweep (2–4 tasks):** OBVIOUS-CONSTRUCTION; then TRANSFER/BREAK with ADVERSARY if a
  returned TRANSFER-AUDIT lists a BREAKS-AT or UNCLEAR verdict, else CURVE/EXTREMES; fill up to 4
  in this order: ANALOGY/SIMULATION, CURVE/EXTREMES, BARRIER, SMALL-CASE DATA (only if a scout
  table exists). Under a user limit of about 60 tasks or fewer, run 2: OBVIOUS-CONSTRUCTION and
  the second choice above (TRANSFER/BREAK and ADVERSARY then share one task,
  `--title "lens TRANSFER/BREAK+ADVERSARY"`).
- **Every sweep** includes a constructive lens (OBVIOUS-CONSTRUCTION or CURVE/EXTREMES): a
  queue-low sweep without one swaps its second lens for the less recently used of the two.
- **Pairing:** TRANSFER/BREAK never runs without ADVERSARY or BARRIER in the same sweep.
  SMALL-CASE DATA is dropped first when fewer tasks fit.
- **queue-low sweep:** the two least-recently used lenses, plus the pairing rule; ties go by
  first-sweep order.
- **Continuation sweep** (§2.1): OBVIOUS-CONSTRUCTION and ADVERSARY; fill up to 4 with BARRIER,
  then CURVE/EXTREMES. Under a user limit of about 60 tasks or fewer, run the first 2.
- Put the lens in the title: `--title "lens ADVERSARY"`.

### 5.2 Gate verdicts

Before a QUESTION-GATE on a question whose lane is not active, run `q set RUN Qxx --status
vetting`; a fast-start or foothold lane stays active. Route each verdict by its field:
- **MODEL-GATE.** SOUND: nothing to do. Any verdict may carry `corrections`: copy them verbatim
  under the model in "How I read your request"; the next SELECT or RENEW applies them. PATCH:
  `ri.py ingest` files each `patch-<Mx>.md` verbatim as `frontier/patches/M<n>.md` (gated, never
  re-gated); questions not yet active, audits and scouts on Mx use M<n> from then on
  (`q set --model M<n>`); an active lane changes model only when SELECT or RENEW says so, at a
  round boundary (§6.1). A bound inside a patch is never filed: the skeptic puts it in an
  argument, gated as a transfer fact (§5.4) or a SOLVED result (§5.3). DEGENERATE: one
  investigator MODEL ("apply gate verdicts", at most once at opening; later, RENEW) restricts or
  re-charges X (new model ID, new MODEL-GATE) or drops the variant; verdicts on the models it
  introduces go to the first SELECT. If the degenerate model is M1 (the user's or the bundle's own
  reading), ingest freezes the skeptic's `degenerate-M1.md` as `--kind transfer` (§5.4); report it
  at once in `progress.md` §1 and "How I read your request", labelled "candidate (skeptic
  argument; check pending)" until gated, never as a dead end.
- **QUESTION-GATE.** ADVANCE: `ri.py q set RUN Qxx --plausibility <p>`; `--status ready` once §6
  holds (an active lane: `--plausibility` only; the ADVANCE releases its round's provers, §6.1).
  REFORMULATE, DEMOTE and KILL(IMPLIED) (except the focused claim's), and any other KILL on the
  focused claim except KILL(FALSE): `ri.py ingest` logs a `question-verdict` event (§7). Its
  handler writes a new version (REFORMULATE; light re-gate), a stepping-stone rung or SAFE card
  (DEMOTE), or successors (KILL(IMPLIED)). A fast-start seed's non-ADVANCE light gate gets no
  RENEW: MODEL step 8 applies it, and a new version joins the batched seed gate (§2 step 4b).
  SOLVED, REFUTE-SKETCH, a `solved:` lower rung, a requested KILL(IMPLIED) argument, and the
  focused claim's KILL(IMPLIED): §5.3. KILL(code): `ri.py q set RUN Qxx --status killed
  --note-file <file>` ("<code>: <evidence>"); a KILL(IMPLIED) note reads "follows from <locator>"
  and is reported as an attributed answer, never as a dead end; other codes stay as dead ends.
  The focused claim is never killed by a gate (SKILL.md §5 focused step 2). KILL(FALSE) becomes
  an exclusion only after the witness passes the counterexample gate (verification.md §8) and
  `ri.py exclude`.
- **CLAIM-GATE.** STANDS: report with the label. QUALIFY or OVERCLAIM: copy the qualifier or the
  corrected wording verbatim into every `progress.md` section that states the result, §1
  included, and into the writer's Assignment; the next RENEW copies it into story.md. KNOWN:
  report as a rediscovery with its locator; log `literature-hit`; a locator with no source card
  gets a TARGETED task that cards it. TRIVIAL: report as a remark; dispatch a skeptic MODEL-GATE
  for loopholes.

A "light" QUESTION-GATE runs checks 1–3b (`ri.py task new ... --mode QUESTION-GATE --light`);
the investigator marks each successor light or full.

**Batching.** One skeptic task may gate several models (MODEL-GATE) or several questions
(QUESTION-GATE, `--question Q07,Q08`) when it authored none of them, with one verdict per item;
in focused mode one task may run the MODEL-GATE on M1 and the QUESTION-GATE on Q01
(`--mode MODEL-GATE --question Q01`). One TRANSFER-AUDIT task may cover several results of one
source; one ISOLATED verifier checks all transfer or fragment candidates frozen in a wave.
Result reviews are never batched: INDIVIDUAL, SALVAGE and SECOND-INDEPENDENT take one candidate
per task, and a CROSS-DRAFT covers one lane round's cohort (`ri.py` refuses otherwise). Under a
finite user limit, batch whenever possible.

### 5.3 Gate-only rounds for skeptic arguments

A skeptic task Txxx's argument becomes a result only through a gate-only round. Its file is
frozen unchanged, with Txxx as author; a rewrite by another role is a new candidate authored by
the rewriting task.
- SOLVED: `solved-Qxx.md` claims `Qxx.R1`; a `solved: Rj` field: the same file claims `Qxx.Rj`;
- REFUTE-SKETCH: `refutation-Qxx.md` claims `Qxx.D`;
- KILL(IMPLIED): `implied-Qxx.md` claims `Qxx.R1` only when a named question, statement or
  headline will cite it (`tasks_requested: gate-only Qxx for Qyy`); otherwise it stays a remark,
  recorded in map.md with the skeptic's locator. In focused mode, the focused claim's argument
  is always gated (`--for` that question).

`ri.py ingest` freezes SOLVED, `solved:` and REFUTE-SKETCH files, and the focused claim's
`implied-Qxx.md`, and prints the commands below. These rounds open at once, with no investigator
request, even on a held lane; gate-only rounds never count toward the lane cap (§6) or the lane's
round budget.
1. A question that is not active: `ri.py q set RUN Qxx --status active --plausibility
   <supported; doubtful for REFUTE-SKETCH> --slots <N, else 2>`, then `ri.py round RUN Qxx
   --open --gate-only`: a round with no provers. An active lane (a fast start): its current
   round becomes the gate-only round; dispatch no provers in it. A `solved:` lower rung needs no
   round: gate it beside whatever its question does.
2. A requested KILL(IMPLIED) argument: `ri.py cand add RUN --lane Qxx --claims Qxx.R1 --kind
   proof --file tasks/Txxx/implied-Qxx.md --author Txxx --for Qyy`. For every such candidate,
   dispatch INDIVIDUAL and SECOND-INDEPENDENT reviews, and a scout SANITY check if the Sanity
   line names one (I3 unchanged).
3. Accepted proof of D: `ri.py exclude RUN --claim Qxx.<rung D refutes> --cand Cxxx`; the lane
   ends refuted. Accepted R1: `top-accepted`; the lane ends resolved and RENEW proposes
   successors (§7). Accepted lower rung: `rung-accepted`. Otherwise the lane runs normally from
   round 2 (with D slots after a REFUTE-SKETCH) when the lane cap allows; until then
   `q set --status ready`. Its record keeps the argument and its objections for the next
   briefings.

While such a candidate is under review, or once its question's R1 is accepted, never set the
question killed or parked (`q set` refuses).

### 5.4 Transfer gate (light)

`--kind transfer` covers any model-level fact (a transfer row, a simulation edge, an endpoint
or saturation claim), gated by one ISOLATED review. If that review reports `new_argument: yes`,
acceptance also needs a second ISOLATED pass from another fresh task (`ri.py` enforces it).

Gating is lazy. Gate a row only when a lane statement's Background or Constraints use it as a
premise, a headline or an "X does not help" result depends on it, or a draft cites it. A row a
lane statement uses as a premise is gated with that question's QUESTION-GATE; other rows are gated
beside the lane's round, never before it. Until it passes, the row is a conjecture: a draft that
relies on it draws a MAJOR [CITE] objection. Always gate a row named in a contradiction (§7), and
each file the investigator's `tasks_requested` names:
1. `ri.py cand add RUN --kind transfer --file tasks/T014/transfer-M1.md --author T014 --for Q07`
   (the file's first line, `claims: transfer:<S03 Thm 2>@M1`, gives the claim; an edge:
   `claims: transfer:edge M0⪯M2`).
2. One verifier `--mode ISOLATED --cand C1,C2,... --start` for all transfer candidates frozen in
   this wave, with their source cards and source files added by path (`--extra-file`).
3. `ri.py ingest RUN Txxx --accept` (accept and `ledger add`). A failed check goes to the next
   RENEW.

## 6. Ready gate and opening a lane

A question is **ready** when it has:
- an ADVANCE, SOLVED or REFUTE-SKETCH verdict on its current version;
- an exact R1 under a model that is SOUND or carries a verbatim PATCH;
- a ladder with D and a "D refutes" line;
- a lane statement whose Sanity line names a scout check or says "not checkable (<reason>)".

Then `ri.py q set RUN Qxx --status ready`. While active lanes (gate-only rounds not counted) are
fewer than max(2, ⌊K/2⌋), open ready questions in the investigator's portfolio order: `ri.py q set
RUN Qxx --status active --slots N --model M --rung <current rung>` (N from `lanes_to_open`), then
`ri.py round RUN Qxx --open`, then proof-lane.md.

### 6.1 Fast start (the only exception to the ready gate)

Like the paper's provers, the fast start begins on a claim the user states verbatim: the focused
claim (SKILL.md §5, focused step 2) and, in program mode, one primary seed (step 4). Copy the
statement: R1 is the claim verbatim, "D: the negation of R1. D refutes: R1", the user's
definitions and references verbatim, "Sanity: pending (scout ANCHOR)". A READING successor (§3)
opens the same way; its statement is the RENEW's, not a copy. Open the lane before any gate has
returned (`q set`'s note is expected) and dispatch round 1's briefings; a program seed's lane
opens when its light gate returns ADVANCE (SKILL.md §5 step 4). Round 1's provers wait for the
light QUESTION-GATE, whose verdict is routed by §5.2: an ADVANCE releases them; a SOLVED, a
REFUTE-SKETCH or the focused claim's KILL(IMPLIED) makes round 1 the gate-only round (§5.3). The
lane counts as gated from then on. Never renumber R1 later: a MODEL statement adds weaker rungs
below it and lists stronger variants for a follow-up question. A later full gate, MODEL-GATE,
literature-hit, or SELECT decision acts at the lane's next round boundary.

In focused mode, on a blocking-parallel host (runtime.md §3), order the waves by length: first the
light gate and round 1's briefings; then round 1's provers with SURVEY, LANDSCAPE, the scout
ANCHOR and investigator MODEL.

## 7. Events

Log each event (`ri.py event RUN --type <type> [--lane Qxx] --note-file <file>`) unless `ri.py`
logs it; take the mechanical action. A **hold** blocks new rounds in the lane (`round --open`
refuses) until `ri.py event RUN --handled E# --by Txxx` names the task that handled it: RENEW,
SELECT, BREADTH, MODEL (literature that returned before it), or the comparator or writer at a
milestone or focused delivery. Batch all unhandled events into one investigator RENEW, but
dispatch it for a stall only after the TARGETED review returns, and for too-easy only after both
skeptic gates return. In program mode no RENEW runs before the first SELECT, except the
continuation RENEW of a converted focused run (§2.1), which handles no events: SELECT handles the
events logged so far (§2 step 7), and a MODEL handles those its Assignment names. Route its
output by SKILL.md §6, and apply its `contradiction` field.

| Event | Detected by | Mechanical action first | Hold; release | RENEW returns |
|---|---|---|---|---|
| `rung-accepted` | `ri.py accept` below R1 | lane moves to the next stronger open rung | no | HYPOTHESIS-AUDIT if "assumes" |
| `top-accepted` | `ri.py accept` on R1 | in-flight work finishes; close the lane (proof-lane.md §6) | lane ends | successors; story update |
| `refuted` | `ri.py exclude`, once per lane | the same; close the lane refuted | lane ends | READING (first, when it applies), HARVEST, BOUNDARY, MINIMAL-HYPOTHESIS, CORRECT |
| `stall` | status hint (2 rounds with no new accepted rung, ledger entry or objection tag); CROSS-DRAFT `shared_failing_step`; advisor advice naming a shared step | TARGETED review of the stuck step; a scout EXPLORE on it unless the Sanity line says not checkable | yes; RENEW | DESCEND, SPECIALIZE, SPLIT, FLIP, RESTRICTED-CLASS, BARRIER, COMPUTE, PARK |
| `lane-budget` | status: `--budget` (else `lane_budget`) rounds since opening or the last renewal | none | yes; RENEW | continue with a reason (budget restarts), descend, or park |
| `literature-hit` | `found: settles` naming a question or the claim (LANDSCAPE, TARGETED, SURVEY settles check); CLAIM-GATE KNOWN | finish the running round | yes; RENEW (opening: SELECT; before MODEL: MODEL) | re-target past the known result |
| `new-source` | `ri.py file-cards`: a card filed after MODEL (late SURVEY, LANDSCAPE, TARGETED, user paper), except a bundle file MODEL read as uncarded | none; `--lane` for each lane whose statement cites it | with `--lane`; RENEW (opening: SELECT) | map and transfer update; re-targeted cards |
| `question-verdict` | `ri.py ingest`: a skeptic REFORMULATE, DEMOTE or KILL(IMPLIED) | none | no; RENEW (before the first SELECT: the MODEL naming it, else SELECT) | a new version, a stepping-stone placement, or successors (After-ACCEPT operators) |
| `too-easy` | a `too_easy` field other than `none` (verifier, skeptic, RENEW), never on a KILL(IMPLIED) certificate; an accepted value equal to c(∞) in `model.md` | skeptic MODEL-GATE + CLAIM-GATE; no headline until both return | no | model patch (new model ID) or remark |
| `model-change` | `ri.py quarantine` | verification.md §9 | no; quarantine blocks use | re-scoped questions |
| contradiction (logs `model-change`) | `accept` refuses, or status or check reports, a "contradiction"; a `contradiction` field (investigator, skeptic) | quarantine the entries involved; TARGETED review of the conflict; fresh SECOND-INDEPENDENT review of the accepted proof; transfer gate (§5.4) on the SURVIVES row. Never too-easy. | no; quarantine blocks use | which side fails; map update |
| `queue-low` | status, after the first SELECT: ready plus vetting questions < max(2, ⌊K/2⌋) − active lanes | proposal sweep (§5.1), then SELECT | no | new cards |
| `breadth-review` | every 10 lane-rounds (summed), or 30 tasks finished since the later of the first SELECT and the last breadth review; after each headline; before any exhaustion claim | investigator BREADTH in a fresh context (map, model, transfer, ledger, records, statements, statuses) | no | an answer to each divergence |
| `milestone` | a story.md headline whose claims are all accepted; a user request | CLAIM-GATE beside the comparator → writer → verifier PAPER → `progress.md`, `reports/` (proof-lane.md §6) | no | story update; lanes keep running |
| `user-input` | a user message during the run | papers: intake, SURVEY, `new-source`; scope or priority: append verbatim to `contract.md`; method hints: to RENEW and summarizers as "USER SUGGESTION (not binding)"; why or explain: investigator EXPLAIN, relay `explain.md` (no event) | no | honour scope changes; weigh hints |

A `bridges` from any literature task is context, never an event: give its path to MODEL, SELECT
and the lane's next summarizers. `nothing-found` → record the coverage.

## 8. Exhaustion

"No useful work remains" is valid only when a fresh BREADTH review finds every map cell tight,
excluded, or parked with a reason and a resurrection condition, and a widened search within the
contract (other regimes, sibling problems, robustness of X) finds nothing. Then set the
checkpoint status to blocked/exhausted, write a final progress report, and tell the user what
would unlock more work.
