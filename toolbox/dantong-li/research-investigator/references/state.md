# State: run directory, ownership and ri.py

Run directory, file owners, IDs, formats and every `ri.py` command. The loop is in SKILL.md §6;
host mechanics are in runtime.md.

## 1. Run directory

`ri.py init` creates this skeleton. Keep RUN short (runtime.md §10).

```
RUN/
  contract.md          objective, key difference, mode + reason, scope, limits, lane budgets,
                       capability card
  checkpoint.md        <= 2 pages: ri:status block + orchestrator notes
  progress.md          user-facing digest, answer first
  STOP  PAUSE          sentinel files, any letter case, any extension (STOP.txt counts)
  .ri.lock             exists only while an ri.py command writes
  driver.lock          exists only while the optional driver runs (runtime.md §9)
  sources/
    index.md           bundle inventory (from intake)
    raw/               extracted bundle (never executed)
    S01.md ...         source cards
    bounds.md          bound rows from SURVEY and LANDSCAPE tasks, each prefixed with its Sxx
  frontier/            model.md (model cards, endpoints, simulation edges), map.md (grid),
                       transfer.md (transfer audit), story.md (<= 3 headlines),
                       patches/M5.md ... (MODEL-GATE patches, filed verbatim by ri.py)
  questions/Q01.md ... question cards
  lanes/
    Q07/               one directory per lane, named by its question
      statement.md     lane statement: the only problem statement provers see
      record.md        record of attempts (generated)
      round-01/plan.md round plan: directions -> provers
  candidates/C001.md   frozen candidate files (immutable); C001/ holds its hashed attachments
  ledger.md            ledger view (generated)
  instructions.md      standing instructions
  tasks/T001/          packet.md, dispatch.md (spawn line), worker outputs (§2), result.md
  scout/               filed computational artifacts (scout/T034/)
  reports/             milestone manuscripts and their PAPER reviews
  state.json           canonical machine state (ri.py only)
  log.jsonl            append-only mutation log (ri.py only)
```

## 2. File ownership (I6)

One writer per file. **Filing**: the orchestrator copies a worker's output unchanged into a
canonical place (only a placeholder ID N# becomes its assigned Qxx); the content stays the
authoring role's.

| File | Sole writer | Notes |
|---|---|---|
| contract.md | orchestrator | Objective, key difference, scope and limits change only on a user instruction (appended verbatim). You write the mode reason, a key difference and the "From your notes" section found in user notes (verbatim, with paths) and the capability card. `ri.py intake` adds the intake-cap and bundled-code lines under Limits; on the user's answer, change "Bundled code: not asked" to "allowed" or "not allowed". |
| checkpoint.md, progress.md | orchestrator | `ri.py status` writes checkpoint.md's machine block |
| STOP, PAUSE | user, directly or through `ri.py stop/pause/resume` | |
| sources/ | orchestrator | `intake` writes index.md and raw/; cards and bound rows are filed from literature-reviewer tasks |
| frontier/*.md, questions/Qxx.md, lanes/Qxx/statement.md | investigator | A question's status that counts is in state.json |
| frontier/patches/ | `ri.py ingest` (each a skeptic's `patch-<Mx>.md`, filed verbatim) | Never edited; the investigator folds patches into model.md at SELECT or RENEW |
| lanes/Qxx/round-NN/plan.md | orchestrator | Header from `round --open` |
| lanes/Qxx/record.md, ledger.md, candidates/ | `ri.py` | Generated or frozen; never edit |
| instructions.md | process advisor (content); filed by `ri.py ingest` from the advisor's task directory | Format in prompts/process-advisor.md; never edited in place |
| tasks/Txxx/packet.md and its inputs (dispatch.md, card-Qxx.md, object-Cxxx.md, status.md) | `ri.py task new` | Never opened or changed by the orchestrator, except that a later message to the worker (a cancel) is appended to dispatch.md |
| tasks/Txxx/ (everything else) | the worker of Txxx | |
| scout/, reports/ | orchestrator | Filed from scout, writer and PAPER-verifier tasks |
| state.json, log.jsonl, .ri.lock | `ri.py` only | Never edit by hand |

**Outputs by role and mode**, as the role prompts name them. Each task writes these and
`result.md` in its task directory. The investigator also edits frontier/*.md, questions/Qxx.md
and lanes/Qxx/statement.md in place in MODEL (seed questions), SELECT and RENEW.

| Role and mode | Files |
|---|---|
| investigator MODEL | reading.md; edge-Ma-Mb.md per non-identity edge |
| investigator PROPOSE | cards.md |
| investigator SELECT | select.md; new/N#-card.md and new/N#-statement.md per card |
| investigator RENEW | renew.md; new/N#-card.md and new/N#-statement.md per successor |
| investigator BREADTH, EXPLAIN | breadth.md; explain.md |
| literature-reviewer SURVEY | Sxx.md (or NEW-<short-name>.md) per source; bounds.md |
| literature-reviewer LANDSCAPE | landscape.md; NEW-<short-name>.md per source found; bounds.md |
| literature-reviewer TRANSFER-AUDIT | audit.md; transfer-<model>.md per model |
| literature-reviewer TARGETED | targeted.md |
| scout | setup.md; table.md (EXPLORE, ANCHOR); certificate.md (CERTIFY); code. SANITY, WITNESS and BUILD verdicts are in result.md |
| skeptic | gate.md; solved-Qxx.md (SOLVED, or `solved: Rj`); refutation-Qxx.md (REFUTE-SKETCH); implied-Qxx.md (KILL(IMPLIED)); patch-<Mx>.md (PATCH); degenerate-<Mx>.md (DEGENERATE); a witness file (KILL(FALSE)) |
| summarizer | briefing.md |
| prover | draft.md; notes.md; data files a computer-assisted step uses (listed under `data:`; frozen as attachments, never filed under scout/) |
| verifier (every scope) | review.md |
| ledger-auditor | frag-<n>.md; dead-<n>.md; provenance.md |
| process-advisor | advisor-log.md; instructions.md (when it writes a new revision) |
| comparator | selection.md |
| writer | manuscript.md; trace.md; gaps.md (when needed) |

Workers never run `ri.py`. Filing and question registration: program.md.

## 3. IDs

| Item | Form | Assigned by |
|---|---|---|
| Source | S01 | `intake`; later sources by you, in index order |
| Model | M0 (baseline), M1 | investigator |
| Question and its lane | Q01 | `q add` |
| Candidate; ledger entry or exclusion; task; event | C001; L001; T001; E1 | `cand add`; `ledger add`, `exclude`; `task new`; `event` and commands that log events |
| Rung; claim | R1 (top), R2 ...; D. Claim: Q07.R2 | investigator. Ri implies Ri+1; D refutes R1 unless the statement says "D refutes: Rj" |
| Objection | T045.O2: issue O2 of review task T045, unique across the whole review | the verifier |

IDs are never reused; padding widens as needed (Q100).

## 4. File formats

**result.md**: prompts/_envelope.md and the role prompts; `ri.py ingest` parses the prover,
verifier and scout headers.

**checkpoint.md** (≤ 2 pages; rewrite every iteration). progress.md starts with the same first line.
```
Driven by research-investigator (skill_dir <abs>); to resume read SKILL.md §5.
# Checkpoint
<!-- ri:status -->
(written by ri.py status; do not edit)
<!-- /ri:status -->
## Running        T054 prover Q07 r3 ctx=a1b2 | ...
## Waiting on     task IDs this turn waits for, if any
## Pending events E12 top-accepted Q07 -> RENEW not yet dispatched; holds
## Next actions   1. <exact action, inputs by path>  2. ...
## Notes          <= 10 lines: decisions not visible in state
```

**lanes/Qxx/round-NN/plan.md** (`round --open` writes the header line; you write one line per
slot with the rule applied (proof-lane.md §3), then the Sanity and advice line):
```
# Q07 round 03 — N = 4; rung R1; plausibility mixed; budget 3 of 8
P1  REPAIR C014     A6 (ranking T051)   summarizer T060   prover T064
P2  PROVE Q07.R1    A9 (A1)             summarizer T061   prover T065
P3  PROVE Q07.R1    A9 (A4)             summarizer T062   prover T066
P4  DISPROVE Q07.D  A7                  summarizer T063   prover T067
Sanity: Q07.R1 checkable for n <= 6.  Advice (rev 3) for Q07: none.
```

**state.json** (schema 6): canonical state, including K, lane slots, plausibility and holds,
task links (redo, briefing, notes.md path), candidate direction and assumes, the focused
after-delivery choice (`after`: continue or stop; absent in a run from before v6.4, which then
behaves as stop) and a conversion record (`converted`: from, seq, question, lane_rounds).
**log.jsonl**: one JSON object per mutation.

## 5. ri.py reference

Conventions:
- Invoke as `<python> <skill_dir>/scripts/ri.py` (3.9+, standard library, no network). RUN is
  the first positional argument after the command words. Exit codes: 0 ok; 1 gate, audit or
  refusal (the message says what is missing); 2 usage error.
- Pass RUN as the same absolute path every time (never `.` or a relative path). Other paths
  are relative to RUN, or absolute. `ri.py` prints absolute paths without resolving links;
  packet headers give run-relative output paths.
- **Run `ri.py` commands one at a time**, never as parallel tool calls. Every command that writes
  state or checkpoint.md holds `RUN/.ri.lock`; another command waits up to about 30 s, and a lock
  older than 10 minutes is taken over as stale.
- **Free text goes through files.** Write user, bundle or worker text to a file with the file
  tool and pass the `-file` flag (`--objective-file`, `--key-difference-file`, `--note-file`,
  `--reason-file`, `--statement-file`, `--extra-file`, `--assignment-file`). Never paste such
  text into a shell command: shells expand `$` and backticks. Inline only short text you wrote,
  without `$` or backticks. Every `--note TEXT` has a `--note-file PATH` twin, and every
  `--reason TEXT` a `--reason-file PATH` twin (stop, pause, resume, quarantine).

### Setup and control

```
ri.py init RUN (--objective TEXT | --objective-file PATH)
               [--key-difference TEXT | --key-difference-file PATH] [--mode program|focused]
               [--after continue|stop [--stop-quote TEXT | --stop-quote-file PATH]]
               --isolation L2|L1 [--k K] [--lane-budget 8] [--no-code]
```
Creates RUN (it may exist without state.json) and the §1 skeleton: contract.md with Objective,
Key difference, Mode (focused: an "After delivery: continue|stop" line; `--after` defaults to
continue; `--after stop` needs `--stop-quote`: the user's limiting phrase, copied from the
Objective, at most 200 characters, such as "only this claim" or "then stop"; anything else is
refused, program.md §3), Scope boundaries, Limits, Lane budgets and the runtime.md §1 card;
checkpoint.md and progress.md with the §4 first line; instructions.md with `revision: 0`. On
Windows, warns when the absolute RUN path exceeds 120 characters. Refuses if state.json exists.
`--no-code` (card `worker_io: shell no`) records that workers cannot run code: counterexamples
are then gated without a WITNESS check (runtime.md §7).

```
ri.py intake RUN --archive FILE [--max-mb 500] [--only PREFIX ...]
```
Safe extraction into sources/raw/, executing nothing: lists entries first; rejects absolute
paths, `..`, links and devices; renames Windows-invalid or reserved names, recording originals;
caps total size, file size and compression ratio; one level of nested archives; a path-length
budget. `--only` extracts only members under the given path prefixes (use it rather than
raising the cap); a `--max-mb` above 500 is recorded under Limits in contract.md. Writes
sources/index.md rows: S##, original name, stored path, type (paper-pdf, tex, notes, code, data,
archive, other; `user-notes` for a top-level file whose name starts with the word README,
notes, brief, idea, todo, plan, questions or direction (plurals too) or contains `notes` joined
by - or _ (my_notes, notes-on-X); for a text file up to two folders deep named guide,
start-here, overview, status, roadmap, next-steps, handoff, scope, conjecture, agent-brief,
chat, conversation, transcript or prompts, or inside a folder named guides, notes, directions,
conjectures, handoff, brief or overview; and for a file the top-level README points to (a
relative link or a "START HERE" line); never for code, data, archives or paper-like names (an
arXiv number, "paper", "arxiv"); `text` for other top-level .md/.txt), size, status. When the
bundle holds code files, intake adds "Bundled code: not asked" under Limits in contract.md and
prints the ask-once line (runtime.md §1).

```
ri.py status RUN [--brief | --full] [--no-write]
```
≤ 60 lines (`--brief` ≤ 15, `--full` all): mode, K, control flags, questions by status, each
active lane's round, stage, hold ("Q07 HELD by E12 (stall) until RENEW") and open candidates, live
and unknown tasks (not superseded ones), unhandled events, quarantine, contradictions. SUGGESTED
NEXT ACTIONS, in order: control flags, reconcile, holds and events, round-close work, lane stages,
outer work; one I8 line per lane round. Mechanical hints: ingest a returned task; reconcile a
queued task with outputs, or a cancelled task once no STOP or PAUSE is in force; a late result.md
of a superseded task is "extra evidence: file, do not re-ingest"; stall after 2 rounds without a
new accepted rung, ledger entry or objection tag; lane-budget due the lane's budget (`--budget`,
else `lane_budget`) rounds after the last renewal; advisor due when a closed round of a lane still
running has reviews newer than the last advisor task; "reviews pass but sanity check Txxx still
running" for a candidate waiting on a scout check; queue low (after the first SELECT) when ready
plus vetting questions < max(2, K//2) − active lanes (gate-only rounds not counted); breadth
review every 10 lane-rounds or 30 tasks finished since the first SELECT or the last breadth
review; a run-wide process advisor when none has run by the first SELECT, or 20 tasks have
finished since the last one; before the first SELECT, events are handled by SELECT; in program
mode while no prover task exists, "no prover yet: N tasks, M min; next opening step: ..." and,
once the first SELECT's QUESTION-GATEs returned with nothing ready or 20 tasks have finished, the
no-prover safeguard; opening-budget warnings (more than 4 TRANSFER-AUDITs or 2 non-ANCHOR scouts
before the first SELECT); in focused mode, the consolidation line at the lane's end (with
`continue`: no extra rounds, and the `mode RUN --to program` step after delivery; with `stop`: at
most 2 more rounds and the "Stronger (after R1)" question) and, once a manuscript passed PAPER,
the delivered line (the conversion step with `continue`, the end of the run with `stop`); after
a conversion, the continuation opening (RENEW on the delivered result, then PROPOSE x2-4, then
SELECT, then registering and gating its cards; no queue-low line meanwhile), the no-prover
safeguard counted from the conversion (no watchdog line) and a breadth count from the
conversion; up to 3 progress lint lines (`check --progress`). Every form rewrites
checkpoint.md's machine block, except with `--no-write` (for observers); `--brief` shortens only
the printout.

```
ri.py stop|pause RUN [--reason TEXT | --reason-file PATH]
ri.py resume RUN [--stop (--reason TEXT | --reason-file PATH)]
```
`stop` and `pause` create the file and log the event. `resume` removes PAUSE variants only;
`resume --stop` removes STOP variants, needs the user's words as reason (`--reason-file`), and
logs the old and new reasons (runtime.md §5).

```
ri.py mode RUN --to program (--reason TEXT | --reason-file PATH)
```
After a focused delivery with "After delivery: continue" (program.md §3): sets the mode to
program, records `converted` (from focused, the seq, the delivered question, the lane-round
count) and appends a dated line under contract.md's Mode. It never re-runs intake and keeps
every question, candidate, ledger entry, event and task. Refused (exit 1) while STOP or PAUSE is
in force; on a run already in program mode it changes nothing and says so. It notes a contract
that says stop (convert only on the user's words) and a lane still active (it runs on as a
program lane). The delivered question is the lane of the manuscript that passed PAPER, else the
focused claim (a READING successor before its refuted parent). From then on `status` shows the
continuation opening (program.md §2.1) instead of the focused hints or the program opening, then
ordinary program hints once its first SELECT's cards are gated.

```
ri.py check RUN [--progress]
```
Audit: JSON parses; IDs and objection IDs unique; referenced files exist; candidate and
attachment sha256 match; accepted candidates meet their gates; exclusions meet the `exclude`
rules; no claim both accepted and excluded; ledger deps active and acyclic; quarantine closure
consistent. Warnings (exit code unchanged): checkpoint.md notes over about 60 lines or without
"## Next actions". `--progress` adds the progress lint, also as warnings: template text left in
progress.md; progress.md older than the last acceptance; bare Txxx, Cxxx or Exx tokens in
sections 1–4 and "How I read your request"; sentences over 30 words; letter-digit run-ons
("all960"); "proved", "verified", "novel", "improved", "is new" or "new result/bound/theorem"
without an I5 label or `cited (` in the same sentence.

### Questions and rounds

```
ri.py q add RUN --title TEXT [--tier SAFE|CORE|AMBITIOUS|EXPLORE] [--model M1] [--parent Qxx]
               [--operator NAME] [--priority primary|secondary]
ri.py q set RUN Qxx [--status draft|vetting|ready|active|resolved|refuted|parked|killed]
               [--rung R1] [--tier ...] [--slots N] [--plausibility supported|mixed|doubtful]
               [--model M1] [--title TEXT] [--note TEXT] [--budget N]
```
`q add` assigns Qxx with a card template, status draft. `--status active` creates lanes/Qxx/
(statement template unless one exists; round 0). `--rung` sets the current rung. `--slots` is the
lane's N; it changes only by a portfolio decision (investigator) or a K reduction.
`--plausibility` copies the skeptic's verdict. `--budget N` sets this lane's round budget
(default: init's `--lane-budget`), counted the same way: rounds since opening or the last
lane-budget renewal; `status` shows "budget used/N". `--priority` (seeds) orders status output.
`--status killed|parked` is refused while a review or scout task on a candidate of the question
is live, or once its R1 is accepted (program.md §5.3).

```
ri.py round RUN Qxx --open [--override-hold] [--gate-only]
```
`--gate-only` marks a round with no provers (program.md §5.3): it counts toward neither the lane
cap nor the lane's round budget, and status suggests only its reviews. Increments the lane round,
writes round-NN/plan.md with N, plausibility, rung and budget, prints the number, and notes when
lane-budget is due and when the previous round had briefings but no provers (it still counts).
Refuses (exit 1) on a held lane unless `--override-hold` or `--gate-only`.

### Tasks

```
ri.py task new RUN --role ROLE [--mode MODE] [--lane Qxx] [--round N] [--title TEXT]
               [--cand C014,C015] [--direction "PROVE Q07.R1"] [--brief Txxx]
               [--question Qxx[,Qyy]] [--light] [--objection Txxx.Ok]
               [--assignment-file PATH] [--extra TEXT | --extra-file PATH]
               [--start [--context LABEL] [--isolation L2|L1]]
ri.py task new RUN --redo Txxx [--extra-file PATH | --assignment-file PATH] [--start]
```
ROLE: a role of SKILL.md §3, hyphenated (ledger-auditor). Writes tasks/Txxx/packet.md: header,
Assignment, role prompt + _envelope.md, and `SI<nn>: <text>` of each standing instruction whose
`applies:` matches (verifiers and skeptics get only `review-safe: yes` rules). The Assignment is
the default below or `--assignment-file`, plus any `--extra` lines, then "Time: return within
about N minutes of work; save partial work first (status partial)" unless the text has a Time
line (N per role: scout 20, of compute; skeptic 25; summarizer 20; literature reviewer 45;
investigator MODEL and SELECT 60, other modes 45; prover 90; verifier INDIVIDUAL, SALVAGE,
CROSS-DRAFT, SECOND-INDEPENDENT and PAPER 60, other scopes 45; writer 60; others 45), and ends
"Stop condition: <default for role>". `--start` marks the task running (context = task ID,
isolation = run default) and writes tasks/Txxx/dispatch.md with the spawn line. Refusals:
INDIVIDUAL, SALVAGE or SECOND-INDEPENDENT with more than one `--cand`; a CROSS-DRAFT whose
candidates span lanes or rounds; a QUESTION-GATE on a question with no R1. `--question` also
works with `--mode MODEL-GATE` (focused: one task gates M1 and Q01). Warnings (I1): hand-written
Assignment or extra text with a citation-like token (arXiv ID, DOI, author-year) found nowhere
in sources/, or steering words ("likely", "promising", "expect", "do not pretend").
`--redo` copies role, mode, lane, round, cand, direction and the filled Assignment of Txxx
(`--assignment-file` replaces it, e.g. when it was still the placeholder), links
`redo_of`/`superseded_by`, and marks Txxx superseded. `--extra` lines join the Inputs list when the
Assignment has one. Refuses while STOP or PAUSE exists.

**Default Assignments.** No gate packet (verifier, scout SANITY or WITNESS) gets the
never-include list of verification.md §2: the prover's result.md and notes.md, other reviews,
rankings and rulings, record.md, the question card, investigator or skeptic rationale, another
cohort candidate's file or attachments, another prover's task directory, a scout output on the
same candidate. That section's designed exceptions (ADJUDICATE, PAPER phase 2) are built in. A
lane on a filed patch model (`q set --model M<n>`) gets `frontier/patches/M<n>.md` in every
worker packet. Manual runs copy these rows, Time line included, and add only IDs and paths.

| Role and mode | Flags | Inputs, by path |
|---|---|---|
| verifier INDIVIDUAL, SALVAGE, SECOND-INDEPENDENT; CROSS-DRAFT | `--cand C1` (one); CROSS-DRAFT `--cand C1,C2,..` (one lane round) | frozen candidates and their own attachments; statement.md (rung texts); model.md; the ledger entries in each candidate's deps; the source cards it cites |
| verifier ISOLATED | `--cand` | the fragment, model.md, its dep ledger entries; never the parent draft |
| verifier ADJUDICATE | `--objection Txxx.Ok` | the candidate; that objection's ISSUES line, copied from state; the prover's rebuttal (draft.md section); statement.md |
| verifier PAPER | `--cand` | manuscript, selected candidates, statements, the writer's trace.md (only its Expansions table in phase 1); phase-2 inputs (the rest of trace.md, records, ledger.md) listed separately |
| summarizer | `--direction` | direction, statement.md, record.md, ledger.md, scout/; never questions/Qxx.md |
| prover | `--direction --brief Txxx` | direction, the briefing, statement.md, ledger.md, sources/, scout/ (filed tables: cite them instead of recomputing) |
| scout SANITY, WITNESS | `--cand` | the candidate's `## Object` section, copied to `object-Cxxx.md` when present (else the candidate: protocol or object only), rung text, model.md |
| ledger-auditor | `--lane --round` | the round's reviews (review.md) and candidate files, ledger.md |
| process-advisor | none; `--title run-wide` for a run-wide advisor | record.md of every lane, reviews since the previous advisor task, its advisor-log.md, instructions.md, `ri.py status` output; when run-wide, the result.md of every task finished since the previous advisor |
| investigator RENEW | none | pending events, affected record.md files, prover notes.md paths since the last RENEW, ledger.md, frontier/*.md and patches, pending skeptic verdicts, TARGETED reports since the last RENEW, literature results with `follow_ups` since the last SELECT or RENEW; the no-prover safeguard line when status shows it. The first RENEW after a conversion (`--title continuation`, program.md §2.1): the delivered result and its operators (After-ACCEPT, TIGHTNESS first, with the open stronger rungs; After-REFUTE after a refutation; After-STALL on the open target first when only a weaker rung or none was accepted), the map-grid line, its question card, lane statement and record, the "Stronger (after R1)" files (none of a refuted question), parked questions, reports/, ledger.md, frontier/*.md, contract.md; no events (SELECT handles them) |
| skeptic QUESTION-GATE | `--question Qxx[,Qyy]`; `--light` for checks 1–3b (a light gate) | per question: a gate copy of questions/Qxx.md without its Tier and Skeptic lines (`card-Qxx.md`), lanes/Qxx/statement.md (an active lane with a MODEL or RENEW `new/Qxx-statement.md` not yet installed: that file instead); frontier/{model,map,transfer}.md, frontier/patches/, ledger.md, contract.md |
| skeptic MODEL-GATE | `--title "M1, M2"`; `--question Q01` (focused: with that QUESTION-GATE) | frontier/model.md and patches, contract.md, the M0 source cards |
| investigator MODEL | `--title`: opening (default), "apply gate verdicts", "focused fast start", "focused" | user-notes rows, contract.md, sources/index.md and bounds.md, filed cards, uncarded raw files, LANDSCAPE and ANCHOR outputs, seed gate verdicts and early literature results if returned, primary seeds; before the first SELECT, a "Pending events" list (unhandled literature-hit events and primary seeds' question-verdicts, KILL(IMPLIED) excepted); "apply gate verdicts": the DEGENERATE MODEL-GATE gate.md files, frontier/*.md and patches; a focused title adds only its instruction line (investigator.md MODEL step 8 and "New questions" hold it in full) |
| investigator PROPOSE | `--title "lens <LENS>"` | frontier/*.md and patches, audits, scout tables, ledger.md, sources/bounds.md, landscape.md, killed and parked cards; in the continuation opening also the delivered question's statement, reports/, contract.md and the continuation RENEW's renew.md |
| investigator SELECT | none | after a conversion: the continuation RENEW's new/ cards first (or a line saying it returned none), its renew.md and the "Stronger (after R1)" files; every cards.md since the last SELECT or RENEW (since the conversion, in a continuation), frontier/*.md and patches, questions/, ledger.md, sources/bounds.md, landscape.md, audits, scout tables, the latest breadth.md, finished skeptic, audit and scout results (follow-ups, corrections), unhandled events, K; the no-prover safeguard line when due |
| literature-reviewer SURVEY, LANDSCAPE, TRANSFER-AUDIT | `--title` names the index rows (SURVEY, e.g. `--title "S01-S04"`) or the result (TRANSFER-AUDIT) | contract.md; sources/index.md; frontier/model.md once M0 is filled; LANDSCAPE: the user-notes; TRANSFER-AUDIT: the source card and file, frontier/patches/; focused SURVEY: the settles check |
| scout EXPLORE | `--title "ANCHOR <Sxx>"`, or a cell with `--extra` giving the grid | ANCHOR: the baseline source file; else model.md and map.md; the authorization line when contract.md says "Bundled code: allowed" |
| writer | `--cand Cxxx` (no comparator: the only accepted candidate for its statement) | the candidate and its attachments, its dependency closure's candidate files, its gate reviews (MINOR fills, assurance facts), statement.md, model.md, contract.md, cited source cards; the word budget |

Comparator, BREADTH, EXPLAIN, TARGETED, skeptic CLAIM-GATE, scout BUILD and CERTIFY, and a writer
after a comparator get a template: write the Assignment to a file and pass `--assignment-file`
(IDs, paths and verbatim user or worker text only, I1).

```
ri.py task set RUN Txxx [Tyyy ...] --status queued|running|done|partial|blocked|unknown|cancelled|withdrawn
               [--context LABEL] [--isolation L2|L1] [--note TEXT] [--force-empty]
```
Records status, context (host ID or label) and isolation for one or more tasks. `withdrawn` (with
`--note`) marks a task that was never spawned: no reconcile hint, no advisor count. `--status
running` refuses while the Assignment is still the placeholder; `--force-empty` is for recovery
only.

```
ri.py ingest RUN Txxx [Tyyy ...] [--accept] [--brief]
```
Reads each result.md (and review.md where needed), sets the task done, partial or blocked,
records what it can, and prints what it did and what is left for you:

| Result | ingest records | Left for you |
|---|---|---|
| prover | `cand add` with direction, claims (`none` → the direction's target plus `--gap`), kind, method, deps, gap, `--revises` for REPAIR, `--attach` for the files under `data:`; the notes.md path for RENEW | reviews; one ADJUDICATE per printed rebuttal; a SPECIAL-CASE draft whose case is not a rung (ingest prints "claims: none and no direction target"): `ri.py cand add RUN --lane Qxx --kind lemma --direction "SPECIAL-CASE <case>" --file tasks/Txxx/draft.md --author Txxx`, gated as a lane result (verification.md §1, lemma proposed as a claim) |
| verifier | one `review add` per `review` line, with its `blocking` and `confirmed` lines. SECOND-INDEPENDENT → `cross --note single-draft`; SALVAGE → `individual --note salvage`; ADJUDICATE: REJECTED → PASS plus `objection resolve --how rejected`, UPHELD → FAIL; a `blocking` line on another candidate → a separate adjudicate review of it | route objections (I8); `shared_failing_step` → stall event; `too_easy` → too-easy event |
| scout SANITY, WITNESS | consistent, or witness-valid with exact=yes → PASS; witness-valid not exact → INCONCLUSIVE; contradicts or witness-invalid → FAIL with its CRITICAL `blocking` line; a WITNESS task with status blocked (not machine-checkable) records no review and waives the WITNESS gate | — |
| process-advisor | status; files its `instructions.md` over the run's copy (new revision); prints `allocation_advice` | apply the advice at the next PLAN (A8) |
| skeptic | per item: the verdict (q set hints); REFORMULATE, DEMOTE, KILL(IMPLIED) → `question-verdict` event (also any other KILL on the focused claim except KILL(FALSE), whose witness is gated: program.md §5.2); SOLVED, `solved: Rj` and REFUTE-SKETCH files frozen (author: the skeptic task); PATCH files filed under frontier/patches/; a DEGENERATE M1 argument frozen as kind transfer | the gate-only round (program.md §5.3); corrections and qualifiers into progress.md |
| literature-reviewer | status; prints `found: settles` as a literature-hit hint, `bridges` as context, `follow_ups` as outer work | `file-cards` |
| comparator, writer | `selected` (load-bearing closures); a warning above the word budgets | filing |
| other roles | status; lists artifacts | filing (program.md) |

`--accept` also accepts every candidate of the touched lanes whose gates now hold and runs
`ledger add` for accepted lane results and fragments. Exclusions are never automatic. `--brief`
prints only each task's status line and what is left for you.

### Candidates, reviews, gates

```
ri.py cand add RUN --lane Qxx --claims CLAIM --file PATH --author Txxx
               [--kind proof|construction|impossibility|counterexample|lemma|manuscript|imported|transfer]
               [--direction TEXT] [--method TEXT] [--deps L001,L002] [--revises Cxxx]
               [--from Cxxx [--step LOCATION]] [--round N] [--gap TEXT] [--allow-pending-deps]
               [--attach FILE ...] [--for Qxx|Hn|Cxxx]
```
Freezes PATH as candidates/Cxxx.md with its sha256, author task and context. `--claims`: the
rung a lane result proves; Qxx.D for a proof of D; the rung a counterexample refutes; for a lemma
or manuscript, the claim it serves; for kind transfer, free text such as `transfer:S03 Thm 2@M1`
(no lane). `--from` marks an auditor fragment or dead end (kind lemma only); `--step` names the
confirmed step of the `--from` source that the fragment rewrites (provenance.md's location), and
record.md's Confirmed steps links step -> fragment -> ledger entry through it. `--gap` marks a
declared gap: never acceptable. Deps must be active ledger entries unless `--allow-pending-deps`.
`--attach` copies data files to candidates/Cxxx/ and hashes them; the frozen check covers them.
`--for` names the citer: required for an `implied-Qxx.md` argument, noted when missing for kind
transfer. Kind transfer without `--claims` reads the file's first `claims:` line; `@Mx` in the
claim sets the entry's model. A warning names result.md header fields, I5 label lines or verdict
words in the file (labels belong in result.md). A manuscript with `--revises` whose diff only
inserts the parent's PAPER fill blocks verbatim in their named sections is accepted on that
review, with no DELTA PAPER (verification.md §11).

```
ri.py review add RUN --cand Cxxx --scope individual|cross|isolated|paper|adjudicate|sanity|witness
               --task Txxx --verdict PASS|PASS_WITH_MINOR|FAIL|INCONCLUSIVE
               [--fidelity MATCH|WEAKER|DIFFERENT_MODEL] [--assumes TEXT] [--report PATH]
               [--blocking "O1 CRITICAL: <location> [<TAG>] - <one line>; O2 MAJOR: ..."]
               [--confirmed "Lemma 2; Claim 3.1"] [--note single-draft]
```
Records one review and the sha256 reviewed. Refuses a stale file, a reviewer that authored the
candidate (or its `--from` source, for isolated) or shares its context, and an objection number
the task already used on another candidate. One scope per task and candidate; individual and
cross come from different tasks, and both need `--fidelity` for a lane result. Each `--blocking`
item (CRITICAL or MAJOR) opens objection Txxx.Ok; severities count only in uppercase right after
`O<n>`. `--assumes` records an allowed assumption under MATCH; a candidate's assumes is the union
over its gate reviews.

```
ri.py objection resolve RUN Txxx.Ok --how fixed|rejected|withdrawn --by Txxx|Cxxx [--cand Cxxx]
               [--note TEXT]
```
fixed: by a revision Cxxx; rejected: by an ADJUDICATE task; withdrawn: by the original reviewer in
a later review. `--cand` is required when the ID is ambiguous in legacy data.

```
ri.py accept RUN Cxxx
```
Applies the gate for the candidate's kind (verification.md §1); labels it self-checked if a counted
gate review ran at L1, else agent-checked. Waits (exit 1) while a scout SANITY or WITNESS task
on the candidate is queued or running. Refuses (exit 1, "contradiction") a rung result whose
claim an active exclusion, or an accepted counterexample or proof of D with its exclusion still
pending, covers; and a counterexample or proof of D that refutes an accepted rung result. Logs
`rung-accepted` (`top-accepted` for R1) for proof, construction or impossibility, noting "assumes:
..." when set. After a counterexample or a proof of D, prints the `exclude` command.

```
ri.py ledger add RUN --cand Cxxx [--statement TEXT | --statement-file PATH]
ri.py exclude RUN --claim Qxx.Rj --cand Cxxx [--note TEXT | --note-file PATH]
ri.py quarantine RUN Lxxx|Cxxx --code objection|sanity|failed-isolated|model-change|contradiction|misquote
               (--reason TEXT | --reason-file PATH)
```
`ledger add`: accepted candidate → Lxxx; default statement = first paragraph under '## Theorem'
('## Statement' for fragments) plus "(assumes: ...)"; flags load-bearing entries (deps of an
accepted R1) that need a second isolated review. `exclude`: an accepted counterexample claiming
Q.Rj excludes exactly Q.Rj; an accepted proof of D excludes exactly the rung D refutes; same lane
only, never Q.D. One entry covers Q.R1..Rj and logs `refuted` once; weaker rungs stay open.
`quarantine`: needs a verification.md §9 reason as `--code` (a label or metadata in a file is
never one); marks the entry, its dependents and accepted candidates, transitively; logs
`model-change` per affected lane.

### Views and events

```
ri.py record RUN Qxx
ri.py ledger RUN
ri.py event RUN --type TYPE [--lane Qxx] [--note TEXT]
ri.py event RUN --handled E# [E# ...] --by Txxx
```
`record` regenerates lanes/Qxx/record.md (proof-lane.md §4); `ledger` regenerates ledger.md. TYPE:
rung-accepted, top-accepted, refuted, stall, lane-budget, new-source, literature-hit,
question-verdict, too-easy, model-change, queue-low, breadth-review, milestone, user-input.
`ri.py` itself logs the first three, model-change and question-verdict (ingest); `file-cards` logs
new-source. rung-accepted and top-accepted are logged once per lane and rung (again once every
earlier acceptance of that rung is quarantined). stall, lane-budget, literature-hit and new-source
with `--lane` hold the lane; `--handled` (space-separated IDs; `--by` names the task that handled
them: RENEW, SELECT, BREADTH, MODEL, or the comparator or writer at a milestone or focused
delivery) releases it. Meaning and routing: program.md's events table.

```
ri.py file-cards RUN Txxx [Tyyy ...]
```
Files literature-reviewer outputs (program.md §4): cards to sources/Sxx.md (a `NEW-` card gets
the next Sxx after a dedupe by arXiv ID, then DOI, then normalized title and authors; a
duplicate gets a "duplicate of Sxx" index row), bound rows to sources/bounds.md with `NEW-`
names replaced, and `raw/` downloads to sources/raw/Txxx/. Once an investigator MODEL has
finished, it logs a `new-source` event per new card, with `--lane` for each active lane whose
statement names the source's raw path, arXiv ID or DOI, except for a bundle file that MODEL's
Assignment named as uncarded.

## 6. One lane round, command by command

Lane Q07, round 3, three provers: about 2 commands per worker.

```
ri.py round RUN Q07 --open                       # prints 3; you write plan.md's slots
ri.py task new RUN --role summarizer --lane Q07 --round 3 --direction "PROVE Q07.R1" --start   # T050-T052
# rewrite checkpoint.md, spawn the wave, wait
ri.py ingest RUN T050 T051 T052
ri.py task new RUN --role prover --mode PROVE --lane Q07 --round 3 --direction "PROVE Q07.R1" --brief T050 --start   # T053-T055
ri.py ingest RUN T054                            # froze C014 (claims Q07.R2)
ri.py task new RUN --role verifier --mode INDIVIDUAL --lane Q07 --round 3 --cand C014 --start   # T057
ri.py task new RUN --role verifier --mode CROSS-DRAFT --lane Q07 --round 3 --cand C014,C015,C016 --start   # T059
ri.py ingest RUN T057 T059 --accept              # C014 accepted -> L004
ri.py record RUN Q07
ri.py q set RUN Q07 --rung R1                    # next stronger open rung
ri.py task new RUN --role ledger-auditor --lane Q07 --round 3 --start   # T060
ri.py ingest RUN T060                            # lists frag-1.md
ri.py cand add RUN --lane Q07 --claims Q07.R1 --kind lemma --from C015 --step "Lemma 2" --file tasks/T060/frag-1.md --author T060   # C017
ri.py task new RUN --role verifier --mode ISOLATED --lane Q07 --round 3 --cand C017 --start   # T061
ri.py ingest RUN T061 --accept                   # C017 accepted -> L005
ri.py task new RUN --role process-advisor --start
ri.py status RUN --brief
```

Variants. Gap draft: ingest adds `--gap`; dispatch `--mode SALVAGE`. Repair: ingest adds
`--revises C015`; after acceptance, `objection resolve RUN T059.O1 --how fixed --by C019`.
Rebuttal: `task new --role verifier --mode ADJUDICATE --objection T059.O1 --start`.
Accepted counterexample claiming Q07.R2: `exclude --claim Q07.R2 --cand C020`. Accepted proof of
D: `exclude --claim Q07.R1 --cand C021`. Auditor dead end: `cand add --kind lemma --from Cxxx`,
ISOLATED, `ledger add`; never `exclude`.

## 7. Manual fallback (no Python)

Use when the capability card says `python: none`.

1. Create the §1 directory and templates by hand; unpack the bundle with `intake`'s checks.
2. Keep machine state as tables in `RUN/state.md` (not this reference): Questions, Tasks,
   Candidates, Reviews (with objections), Ledger, Events, with the fields §5 records, then a Log
   list, one line per change. Next ID = largest in the table + 1; never reuse one.
3. Freeze: copy the draft to candidates/Cxxx.md; set `frozen: yes`; record the statement's first
   200 characters as its digest, which each review quotes. Never edit a candidate after review.
4. Apply the gates (verification.md §1) and the `exclude` rules from the tables; note the rule.
5. Write record.md, ledger.md and the checkpoint block by hand, in ri.py's sections.
6. Label the run "unaudited records" in contract.md, checkpoint.md, progress reports and
   assurance profiles. Never run `ri.py init` on a manual run.
7. Write every file as UTF-8 without a byte-order mark, with the host's file tool where one
   exists. Shell redirection can change the encoding: Windows PowerShell 5.1's `>`, `Out-File`
   and `Set-Content` write a BOM or the ANSI code page, which garbles symbols like ≤, ⪯ and
   accented names. In PowerShell, use `[IO.File]::WriteAllText(path, text,
   (New-Object Text.UTF8Encoding $false))`.
8. **Closed vocabularies.** Use only ri.py's question, task, candidate and objection statuses
   and event types (§5), `question-verdict` and `withdrawn` included; never invent one. A
   result found at a gate is a candidate, then a ledger entry.
9. **Freeze** with the shell's SHA-256 when it has one (`Get-FileHash`, `sha256sum`,
   `certutil -hashfile`), over the draft and each attachment; each review quotes it. Use the
   200-character digest of step 3 only without a hash tool.
10. **Packets.** Copy the §5 Default Assignments row, Time line included, and add only IDs and
   paths. A gate packet holds only verification.md §2's inputs; a QUESTION-GATE gets the card
   without its Tier and Skeptic lines, and only for a question with an R1. INDIVIDUAL, SALVAGE and
   SECOND-INDEPENDENT take one candidate; a CROSS-DRAFT, one lane round. Write each Assignment as
   tasks/Txxx/assignment.md and the spawn line in tasks/Txxx/dispatch.md; put helper scripts under
   RUN/tools/; keep table rows contiguous. File MODEL-GATE patches and literature cards by hand,
   as `ri.py ingest` and `file-cards` would. Read briefs, guides, handoff, next-steps and
   chat-export files as user-notes, wherever they sit.
11. **Each loop**, evaluate by hand what `ri.py status` would print and note it in checkpoint.md:
   holds; unhandled events (`question-verdict` included); fast-start provers wait for the light
   gate's ADVANCE; queue-low; breadth-review; lane budgets; stall; the no-prover watchdog; the
   opening budget (4 TRANSFER-AUDITs and 2 non-ANCHOR scouts before the first SELECT); a run-wide
   advisor; the bundled-code question; the `q set` killed/parked refusal; a second ISOLATED pass
   after `new_argument: yes`; a named citer for an `implied-Qxx.md` candidate; a §9 reason for any
   quarantine; the progress lint (`check --progress`). The Reviews table records each review's
   verdict, fidelity and every CRITICAL or MAJOR objection ID.
12. **Rewrite checkpoint.md whole** each iteration, in full words, with at most about 60 lines
   of notes; history goes to the Log.
13. **Focused after delivery.** Copy the after-delivery choice (continue by default; stop only on
   the user's limiting words, quoted) into contract.md's Mode and the state.md header; with continue, the
   conversion is a Log line "mode focused -> program after the delivery of Qxx" plus a dated line
   under contract.md's Mode, never under STOP or PAUSE, then program.md §2.1.
