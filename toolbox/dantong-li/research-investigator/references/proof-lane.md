# Proof lane: the inner Cogentic loop

A **lane** is one Cogentic campaign on one open question and uses its ID (`Q07`). It runs
rounds until its top rung is settled, an event holds it, or the investigator parks it. Lanes
never wait for each other. Provers see only `lanes/Q07/statement.md`.

Your lane work is mechanical (I1): you assign *what* each prover works on, from the statement,
the record, verifier outputs and the advisor's advice; never *how*, and never by which side
looks true.

`ri.py` means `<python> <SKILL_DIR>/scripts/ri.py`; example paths are relative to `RUN`. Gate
rules: [verification.md](verification.md). Events: the events table in
[program.md](program.md). This file says when to run what.

**Dispatch and return.** Dispatch every task here as `ri.py task new ... --start` (packet with
a default Assignment, task marked running), checkpoint, spawn with the dispatch message
(runtime.md), then optionally `ri.py task set RUN Txxx --context <host id>`. Add Assignment
lines only with `--extra-file`; the comparator and a writer after a comparator have no default
and need `--assignment-file`. Every return goes through `ri.py ingest RUN Txxx`, which records
what it can and prints what is left for you.

> **Paper basis** (Cogentic §2.1–2.5, Fig. 1).
>
> *From the paper:*
> - The orchestrator plans each round (how many provers, which direction each) without
>   mathematical opinion.
> - One summarizer per prover writes an independent briefing. This follows §2.1, not the
>   Fig. 1 caption.
> - Provers work in parallel. Each draft is verified alone and side by side; both must pass.
> - The record pools attempts by target, with method and failing objection.
> - An auditor sends confirmed lemmas for isolated re-verification into the ledger, and the
>   advisor reviews logs, every round, for the next round.
> - Literature reviewers return when attempts stall at one step.
> - After a first clear, promising avenues may continue; then comparator → writer → paper
>   audit.
>
> *Adaptations:* pipelined parallel lanes; numeric allocation defaults; D slots keyed to the
> skeptic's plausibility forecast (never your own); a salvage review for gap drafts; a
> single-draft second gate; scout sanity and witness checks; numeric stall and budget
> triggers; adjudication; delta re-checks; `ri.py`.

## 1. Open a lane

Open a lane when all of these hold:
- the question is `ready` (program.md);
- the investigator has written `statement.md` with ladder R1..Rm and D;
- the portfolio gives the lane N prover slots (none given: N = min(4, K), where K is the
  concurrency limit).

```
ri.py q set RUN Q07 --status active --rung R1 --slots 4 --plausibility mixed --model M1
```

`--rung` is the current rung the investigator marked; `--plausibility` is the skeptic's
QUESTION-GATE value. N stays fixed for the lane. It changes only by a portfolio decision
(investigator) or a reduction of K, each recorded with `q set --slots`.

Investigator edits to `statement.md` apply from the next PLAN. Once the lane is active, the
rung texts, D, the model and the Constraints are frozen, because accepted candidates and
fidelity verdicts refer to them. The investigator may still edit Background, Known, Ideal
shape and Literature, and append weaker rungs at the bottom. Any other change is a successor
question.

## 2. Round state machine

```
PLAN -> BRIEF -> PROVE -> VERIFY -> CLOSE -> PLAN r+1 | event holds lane | lane end
   pipelined: a prover starts when its briefing lands; an INDIVIDUAL review starts when its draft lands
```

Rounds within a lane are sequential: PLAN needs the previous round's record and cross-draft
ranking, and BRIEF needs what the previous round's close work adds to the ledger and the
standing instructions (§2.5 step 5). A gate-only round (program.md §5.3) skips PLAN, BRIEF and
PROVE: it verifies a skeptic's frozen argument, then closes as usual.

### 2.1 PLAN (you)

1. `ri.py round RUN Q07 --open` prints r and creates `lanes/Q07/round-NN/plan.md`, with N,
   plausibility and the current rung in its header. On a lane held by an event it refuses
   (exit 1); the lane waits for RENEW.
2. Read `statement.md` (ladder, listed special cases), `ri.py status RUN`, `record.md`, the
   last cross-draft `ranking`, and this lane's entry in the latest `allocation_advice`. Never
   pass plausibility to summarizers or provers.
3. Apply §3 and write `plan.md`, citing only the rule applied per slot (I1).

```
# Q07 round 03 — N = 4; rung R1; plausibility mixed; budget 3 of 8
P1  REPAIR C014     A6 (ranking T051)   summarizer T060   prover T064
P2  PROVE Q07.R1    A9 (A1)             summarizer T061   prover T065
P3  PROVE Q07.R1    A9 (A4)             summarizer T062   prover T066
P4  DISPROVE Q07.D  A7                  summarizer T063   prover T067
Sanity: Q07.R1 checkable for n <= 6.  Advice (rev 3) for Q07: none.
```

### 2.2 BRIEF

Once round r−1's close work has returned (§2.5 step 5), dispatch one summarizer per slot:

```
ri.py task new RUN --role summarizer --lane Q07 --round 3 --direction "PROVE Q07.R1" --start
```

The default Assignment holds the direction and the lane files, never the question card (it
holds tier and plausibility). For REPAIR, the record gives the candidate's review paths.
Summarizers never see each other's output.

### 2.3 PROVE

As each briefing lands (`ri.py ingest RUN T061`), dispatch its prover:

```
ri.py task new RUN --role prover --mode PROVE --lane Q07 --round 3 --direction "PROVE Q07.R1" --brief T061 --start
```

The mode is PROVE, DISPROVE, SPECIAL-CASE or REPAIR. The prover returns `draft.md` (a lemma
DAG or a precise obstacle), `notes.md` and `result.md`.

### 2.4 VERIFY (pipeline rule)

When each prover returns:

1. `ri.py ingest RUN T065` freezes `draft.md` as a candidate from the result fields
   (`claims: none` freezes the direction's target with a gap) and keeps the `notes.md` path
   for RENEW. No `draft.md`: the task is set blocked.
2. Gate the candidate at once; do not wait for other drafts:
   - no declared gap: `ri.py task new RUN --role verifier --mode INDIVIDUAL --lane Q07 --round 3
     --cand C015 --start`;
   - declared gap: the same with `--mode SALVAGE`. It confirms proved lemmas for the auditor;
     a gap draft is never accepted.
3. If the lane statement's Sanity line names a scout check, dispatch a scout SANITY task
   (`--role scout --mode SANITY --cand C015`, never the prover) in parallel; same-rung
   candidates that land together may share one. If the Sanity line says "not checkable
   (<reason>)", copy it into plan.md. A counterexample always gets a scout WITNESS task
   (`--mode WITNESS`) instead; if its witness is not machine-checkable the scout returns
   blocked, and `ri.py` then waives that gate (as for a run initialised with `--no-code`).
   Acceptance waits for every SANITY or WITNESS check dispatched on the candidate. Meaning:
   verification.md §5.
4. If ingest prints "dispatch ADJUDICATE for ...", dispatch one task per rebutted objection
   (`--role verifier --mode ADJUDICATE --objection T045.O2`; ri.py adds the objection's candidate
   and the rebuttal; verification.md §6).

**Cross-draft review.** The round's **cohort** is every candidate frozen from this round's
prover tasks, including gap drafts. It is complete when none of the round's prover tasks is
queued or running. Then dispatch one CROSS-DRAFT verifier on the whole cohort
(`--mode CROSS-DRAFT --cand C014,C015,C016`). It does not wait for the INDIVIDUAL reviews, and
neither review sees the other. Never change a cohort after dispatch. A draft that lands later
gets INDIVIDUAL and SECOND-INDEPENDENT reviews.

**Single-draft second gate.** If the cohort has exactly one candidate, dispatch
`--mode SECOND-INDEPENDENT` instead. It counts as the cross gate.

**Recording.** `ri.py ingest RUN T070` records each review task as it lands: one review per
candidate block of the result header, blocking lines verbatim. If it leaves a line for manual
handling, use `ri.py review add` (state.md §5).

VERIFY ends when every frozen candidate has its required reviews: INDIVIDUAL or SALVAGE,
CROSS-DRAFT or SECOND-INDEPENDENT, and any scout check dispatched for it. Adjudications do not
hold the round.

### 2.5 CLOSE

1. `ri.py record RUN Q07`.
2. Accept. `ri.py ingest RUN T070 T071 --accept` accepts every candidate of the lane whose
   gates now hold and adds accepted lane results and fragments to the ledger (statement: the
   Theorem or Statement paragraph, plus any "(assumes: ...)"). You may accept earlier with
   `ri.py accept RUN C015`; exit 1 lists the missing gates. Exclusions are never automatic:
   - accepted counterexample claiming Q07.Rj: `ri.py exclude RUN --claim Q07.Rj --cand C016`;
   - accepted proof of D: `ri.py exclude RUN --claim Q07.R1 --cand C017` (or the rung on the
     statement's "D refutes:" line), optionally followed by `ri.py ledger add RUN --cand C017`
     (`ingest --accept` already does it).
   One exclusion of Rj covers R1..Rj and logs `refuted` once. After an accept below R1, also
   run `ri.py q set RUN Q07 --rung <next stronger open rung>`. If accept refuses with
   "contradiction", follow verification.md §8.
3. Ledger auditor, if a review of the round listed CONFIRMED_STEPS in a draft not accepted, or
   gave an explicit counterexample to a step:
   `ri.py task new RUN --role ledger-auditor --lane Q07 --round 3 --start`. Freeze each
   fragment and dead end it returns, with `--claims` from its summary:
   ```
   ri.py cand add RUN --lane Q07 --claims Q07.R1 --kind lemma --from C014 --step "Lemma 3" \
      --file tasks/T080/frag-1.md --author T080 [--deps ...]
   ```
   `--step` is the "location in source" column of the auditor's `provenance.md`; through it,
   record.md links the confirmed step to the fragment and its ledger entry (§4).
   Then one ISOLATED verifier per file, or one for several (`--mode ISOLATED --cand C030,C031
   --start`), parent withheld;
   `ingest --accept` records, accepts and adds it to the ledger (verification.md §7). A dead end
   is never excluded.
4. Process advisor: `ri.py task new RUN --role process-advisor --title "after Q07 r3, Q09 r2"
   --start`. One task covers every lane round closed since the last one; one runs at a time.
   It writes the new `instructions.md` in its task directory; `ri.py ingest` files it, and
   later packets carry the new revision. Skip it, in either mode, when no lane will run another
   round: nothing follows to feed. A run-wide advisor, which `ri.py status` flags, still runs;
   it writes standing instructions only.
5. **Feed the next round** (paper §2.3–2.4). PLAN r+1 may be written now. Dispatch BRIEF r+1
   only after round r's ledger auditor, its ISOLATED reviews and the advisor task covering
   round r have returned. Other lanes use the free slots meanwhile. In the control loop, this
   round-close work comes before new lane stages.
6. Check the events in §5. Then PLAN round r+1, unless an event holds the lane.

## 3. Mechanical allocation rules

| Direction | Allowed when |
|---|---|
| `PROVE Q.Ri` | always |
| `DISPROVE Q.D` | always |
| `SPECIAL-CASE <case>` (e.g. n = 2, k = 1) | the case is listed in the statement or is a rung |
| `REPAIR Cxxx` (fix it given its objections) | the latest cross-draft ranking calls it **near-complete**: no CRITICAL, at most 2 MAJOR, all local |

**D is required** if and only if the skeptic's plausibility for the question is mixed or
doubtful, or N ≥ 4. The same test applies in every round.

**Round 1.** Rc is the current rung: R1, unless the investigator marked another.
- A1. ⌈N/2⌉ slots on PROVE Rc.
- A2. If D is required: 1 slot on DISPROVE D.
- A3. If N ≥ 3: 1 slot on PROVE of the next weaker rung. If there is no weaker rung, use a
  listed SPECIAL-CASE; if there is none, use Rc.
- A4. All remaining slots on PROVE Rc.

**Overflow.** If A1–A3 need more than N slots, drop A3 first, then reduce A1 to ⌈(N−1)/2⌉.
A2 is never dropped while D is required.

**Later rounds**, in this order:
- A5. Rung update. Slots on an accepted rung, or on any weaker rung, move to the next stronger
  open rung. Never assign a rung below an accepted one, because Ri implies Ri+1.
- A6. REPAIR. One slot per near-complete candidate, in cross-ranking order, up to
  max(1, ⌊N/2⌋) slots. Skip candidates that are already accepted or already revised.
- A7. D. While R1 is open and D is required, keep at least one D slot. A REPAIR of a D
  candidate counts.
- A8. Advisor. Apply this lane's entry in the latest `allocation_advice` to the free slots
  exactly as written, if it names directions of the types above. Ignore any part that names a
  method or a likely answer. A stall named in the advice is an event (§5), not a slot change.
- A9. Fill the free slots with A1, A3 and A4, applied to the free count.
- A10. Every prover has its own summarizer task, also when provers share a direction.
- A11. Holds first: a lane held by an event gets no PLAN; a hold never changes allocation.

**Small N.** These follow from A1–A4 and the overflow rule, except N = 1.
- N = 1: if D is required, alternate Rc and D between rounds, Rc first. A due REPAIR takes the
  slot.
- N = 2: Rc + D if D is required, otherwise 2 × Rc. A REPAIR replaces one Rc slot.
- N = 3: 2 × Rc + D if D is required (A3 dropped), otherwise 2 × Rc + the next weaker rung.

You never choose a method, add or drop a rung, park a lane, or reallocate because a direction
looks promising or dead (I1). Only the investigator re-scopes, through an event.

### Worked allocation, N = 4 (illustrative)

Setup: ladder R1 ⇒ R2 ⇒ R3, with D = not R1. D is required (N ≥ 4; plausibility is also
mixed).

**Round 1.** A1: 2 × PROVE R1. A2: DISPROVE D. A3: PROVE R2.

**Outcomes.** C001 (PROVE R1) claims only R3 and FAILs with a CRITICAL at Lemma 3. C002 (PROVE
R1) is INCONCLUSIVE, and the cross-draft ranking calls it near-complete. C003 (PROVE R2) passes
both gates and is accepted (`rung-accepted`). C004 (DISPROVE D) declares a gap.

**Round 2.**
- A5: the R2 slot moves to R1. R3 is implied by R2, so it gets no slot.
- A6: REPAIR C002 (1 slot; the cap is 2).
- A7: DISPROVE D.
- A8: the advice for Q07 is "none".
- A9: two free slots. A1 gives 1 PROVE R1; A3 does not apply (2 < 3); A4 gives another PROVE R1.

Result: REPAIR C002, PROVE R1, PROVE R1, DISPROVE D. Had the advice been
"Q07: one slot SPECIAL-CASE n = 2 (listed; no slot in 2 rounds)", A8 would turn one PROVE R1
into SPECIAL-CASE n = 2.

## 4. Record of attempts

`ri.py record RUN Q07` regenerates `lanes/Q07/record.md` from state. Never edit it by hand. It
is read first by summarizers, the advisor, the investigator in RENEW, and you at PLAN.

Attempts are grouped by their direction's target, with the rung each one claimed. The failing
step is the draft's "Obstacle to the assigned target" when the claim falls short of the target,
else the decisive objection's location. "Accepted" lists only rung results, counterexamples and
D proofs; fragments and dead ends appear under "Ledger fragments".

```
# Record of attempts — Q07 (generated)
Accepted: Q07.R2 by C003 (agent-checked; assumes: n even)
Exclusions: none
## Target Q07.R1
| Cand | Rd | Prover | Claimed | Method | Outcome | Failing step | Decisive objection(s) |
| C001 | 1 | T012 | Q07.R3 | potential function | failed | obstacle: Lemma 4, factor 2 lost at k = 1 | T020.O1 CRITICAL [PROB] union bound over infinite family (tasks/T020/review.md) |
| C002 | 1 | T013 | Q07.R1 | primal-dual, charged lookahead | inconclusive | Claim 4.2 | T021.O2 MAJOR [CONST] constant depends on n (tasks/T021/review.md) |
## Target Q07.R2
| C003 | 1 | T014 | Q07.R2 | greedy with one advice bit | accepted (L004) | - | - |
## Target Q07.D
| C004 | 1 | T015 | Q07.D | adversarial family search | gap declared | step 2 | - |
## Ledger fragments
- L005 lemma (C006, from C001 Lemma 2)
- L006 dead end (C007, from C001 Claim 5)
## Confirmed steps
- C001 Lemma 2 (T020) -> C006 -> L005
## Open objections
- T021.O2 MAJOR on C002
```

Each method is the prover's one-line label, not a claim.

## 5. Lane events

The events table in [program.md](program.md) gives each event's trigger, hold and RENEW output.
In a lane you feed it:
- `ri.py` logs `rung-accepted` and `top-accepted` (accept), `refuted` (exclude) and
  `model-change` (quarantine). Never log these yourself.
- `stall`: `ri.py status` suggests it after 2 consecutive rounds without a new accepted rung,
  ledger entry or objection tag. The same-failing-step trigger comes only from a CROSS-DRAFT
  `shared_failing_step` other than none, or from the lane's `allocation_advice`. Never judge
  it from step labels yourself.
- `too-easy`: log it only from a `too_easy` value other than none (verifier, skeptic or RENEW)
  or from the c(∞) check on the model card. An accepted result that beats an IMP marked
  SURVIVES is a contradiction (verification.md §8), not too-easy.
- `lane-budget`: `ri.py status` says when it is due.

A `stall`, `lane-budget`, `literature-hit` or `new-source` event logged with `--lane` holds the
lane: `round --open` refuses until `event --handled ... --by` releases it (program.md §7).

```
ri.py event RUN --type stall --lane Q07 --note-file <file>   # file: T070 shared_failing_step: C014 Lemma 3 ~ C016 Lemma 2
```

## 6. Lane end and consolidation

- **Top rung accepted** (paper §2.5). Open no new round. Let the lane's dispatched tasks
  finish and accept whatever passes; the comparator later presents one proof per statement,
  chosen by assurance. Then `ri.py q set RUN Q07 --status resolved --rung R1`.
- **Refuted.** The same, then `ri.py q set RUN Q07 --status refuted`. Accepted weaker rungs
  stay in the ledger.
- **Parked by RENEW.** Let in-flight work finish, then
  `ri.py q set RUN Q07 --status parked --note-file <file>` (the resurrection condition).

RENEW then proposes successors.

Between milestones, an accepted candidate is reported as an **accepted result note**: one
entry under Results in `progress.md` with claim ID, label, exact statement with any
"(assumes: ...)", candidate path and assurance profile (verification.md §10). It is already a
self-contained proof. When it settles a lane's strongest rung so far, also copy it at once to
`reports/<Q>-<rung>-proof-<Cxxx>.md`, headed by that note, and tell the user. Under a limit too
tight for the writer and PAPER, that copy is the deliverable, with its ledger dependencies and
open MINOR fills listed.

**Full consolidation** runs at a milestone (a story.md headline complete), on user request, at
final delivery, and in focused mode after the lane ends:

1. Skeptic CLAIM-GATE on the headline (focused mode: on the accepted target rung, always, with
   the locators of any literature-hit or new-source event on Q01), in parallel with step 2, or
   with step 3 when step 2 is skipped. A QUALIFY or OVERCLAIM goes to the writer, as a revision
   if it has already returned.
2. Comparator: selects the strongest accepted candidates; one proof per statement; Pareto-
   incomparable results stay separate. Skip it when one accepted candidate claims the strongest
   accepted rung and no other result must be merged (`ri.py status` names the candidate).
3. Writer: manuscript from the selected candidates, their MINOR fills, ledger dependencies and
   source cards (without a comparator: `--cand Cxxx`, whose default Assignment lists them).
4. `ri.py cand add RUN --lane Q07 --claims Q07.R1 --kind manuscript --file tasks/T090/manuscript.md --author T090 --deps <L-IDs>`.
5. PAPER verifier; `ingest --accept`; copy to `reports/`. PASS_WITH_MINOR (one revision with
   the fills, if the limits allow) and failure: verification.md §11.
6. Writer `gaps_sent_back`: each [MATH] item becomes, in its owning lane, a REPAIR direction on
   the selected candidate with the item in the Assignment (`--extra-file`), or one prover task
   on a standalone lemma (gated as a lane result); each [CITE] item, a TARGETED literature
   task. After they return, rerun the writer and PAPER.

Other lanes keep running. STOP halts consolidation unless the user asked for a wrap-up.
