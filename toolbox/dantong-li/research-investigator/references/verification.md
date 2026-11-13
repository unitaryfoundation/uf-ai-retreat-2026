# Verification

This file says what each item needs before it counts, how verdicts combine, and how results are
labelled. Elsewhere:
- when to dispatch each check: [proof-lane.md](proof-lane.md);
- verifier stance, procedure, checklist tags, review (review.md) and result format:
  `prompts/verifier.md`, which `ri.py` copies into every verifier packet;
- freezing, stale-review and self-review refusals, ingest and gate checks: `ri.py` (`cand add`,
  `ingest`, `review add`, `accept`, `check`); without Python, state.md's manual fallback.

## 1. Gates by item type

All gate reviews come from fresh tasks that did not author the item (I2).

| Item | `--kind` | Required gates | Then |
|---|---|---|---|
| Lane result | proof, construction, impossibility | INDIVIDUAL + CROSS-DRAFT (or SECOND-INDEPENDENT): both PASS/PASS_WITH_MINOR, fidelity MATCH; no open CRITICAL/MAJOR from any review or scout check; deps active (I3). A SALVAGE review never counts. | `accept`, `ledger add` |
| Counterexample to a rung | counterexample; `--claims` is the rung it refutes | INDIVIDUAL PASS (fidelity: the witness meets every hypothesis of the exact rung) + the cohort's CROSS-DRAFT (or SECOND-INDEPENDENT) PASS, fidelity MATCH + scout WITNESS PASS (exact where possible) if machine-checkable (`ri.py` waives it when the WITNESS task returns blocked, or for a run initialised with `--no-code`) | `accept`, `exclude` (§8) |
| Proof of D | proof, construction, impossibility; `--claims Q.D` | as a lane result | `accept`, `exclude` (§8), optionally `ledger add` |
| Ledger fragment or dead end | lemma `--from Cxxx` | one ISOLATED PASS, parent withheld, by a task that wrote neither fragment nor source draft; no open CRITICAL/MAJOR; second ISOLATED if load-bearing (§7) | `accept`, `ledger add` |
| Lemma proposed as a claim | lemma | as a lane result | `accept`, `ledger add` |
| Model-level fact: transfer verdict, simulation edge, endpoint or saturation claim | transfer; `--claims "transfer:<S03 Thm 2>@M1"` | one ISOLATED check of the argument; a second ISOLATED pass from another fresh task if a review reports `new_argument: yes` or the entry is load-bearing (§7) | `accept`, `ledger add`; until then the map row is "conjecture (audit Txxx)" ("conjecture (audit Txxx; SURVIVES, ungated)" for a SURVIVES row) |
| Imported literature result (optional) | imported | source card + one ISOLATED check against the source (§7) | `accept`, `ledger add` |
| Manuscript | manuscript | PAPER PASS/PASS_WITH_MINOR; no open CRITICAL/MAJOR (§11) | `accept`, copy to `reports/` |
| Model, question, headline | none | skeptic gates in fresh contexts (program.md) | no `ri.py` gate |

Rules for every row:
- A gate counts only once its review is recorded; an unreturned task is not a pass.
- PASS_WITH_MINOR counts as a pass; its written fills go to the writer. Never revise a lane
  candidate only to fix MINOR issues (a manuscript: §11).
- No majority vote: any non-pass blocks. Route each open CRITICAL or MAJOR objection per I8:
  a REPAIR direction (proof-lane.md A6), an adjudication (§6), a reformulation by the
  investigator, or a recorded parking reason.
- Any edit makes a new candidate (`--revises`); verdicts never carry over (I3).

## 2. Independence in practice (I2)

`ri.py task new` writes each gate packet's default Assignment from this table and refuses
anything on the never-include list.

| Scope | Include, by path |
|---|---|
| INDIVIDUAL, SALVAGE, CROSS-DRAFT, SECOND-INDEPENDENT | candidate file(s), rung texts (`statement.md`), `frontier/model.md`, ledger entries in the deps, cited source cards |
| ISOLATED | the fragment (or transfer, imported) file, `model.md`, its dependency entries, the source cards it cites; any other source card or the source file added with `--extra-file` |
| ADJUDICATE | the candidate, that objection's line only, the rebuttal section, `statement.md`, cited sources |
| PAPER | manuscript, selected candidates, their statements; phase-2 inputs listed separately |
| scout SANITY, WITNESS | candidate (protocol or object only), `statement.md` (rung text; its Sanity line gives the instance domain), `model.md` |

**Never include:** the prover's `result.md` or `notes.md`, any other review, ranking or
ruling, `record.md`, the question card (tier, plausibility), investigator or skeptic
rationale, whether the candidate is accepted, another cohort candidate's file or attachments,
another prover's task directory, or a scout output on the same candidate. A skeptic
QUESTION-GATE gets a gate copy of the card without its Tier and Skeptic lines.

**Accidental exposure.** A gate that saw anything on the never-include list for its item is
void; a fresh task re-runs it. Nothing else voids a gate: task IDs, file names, source cards,
pack text, papers, ledger entries and self-labels inside the frozen file (verifiers ignore
them) do not. Never quarantine an accepted entry for exposure or a label (§9).

**Designed exceptions:** ADJUDICATE sees one objection and its rebuttal. A delta re-check sees
the old review.md and the diff. PAPER phase 2 sees the records, but only after phase 1 is saved.

A candidate's two gates come from different tasks and contexts; record every task's context
(`--context`) so `ri.py` can refuse same-context pairs. An L1 gate yields
"self-checked (provisional)", never "agent-checked".

## 3. Severity and verdicts

**Severity and verdict rule** are defined in prompts/verifier.md. In short: a CRITICAL (a
false statement or strategy-breaking step, shown by a counterexample or derivation) gives FAIL;
a MAJOR (a non-routine gap at a load-bearing step, a citation whose hypotheses are not
established, or fidelity other than MATCH), or a load-bearing step left unchecked, gives
INCONCLUSIVE; MINOR issues, each with a written fill, give PASS_WITH_MINOR; else PASS.

**Objections.** Every objection line has the form `O<n> <SEVERITY>: <location> [<TAG>] - <one
line>`. A review numbers its objections once across all its candidates; `ri.py` names them
`T045.O2` and refuses a number reused on a second candidate. Record verdicts and severities
exactly as reported; never reinterpret them (I1).

**Effective verdict.** Suppose every blocking objection of a review is later resolved
(rejected by adjudication, or withdrawn), and the review left no load-bearing step or citation
unchecked. That review then counts as PASS_WITH_MINOR for its gate. If `ri.py accept` still
lists the gate as missing, dispatch a fresh review of that scope.

## 4. Fidelity

Fidelity asks whether the proved theorem is the claimed rung, in the claimed model. Each gate
verifier compares its restatement with the exact rung text and the model card: MATCH (same or
stronger statement, same model), WEAKER(how) or DIFFERENT_MODEL(how), as prompts/verifier.md
defines them.

Acceptance needs MATCH from both gates (I3); anything else is a MAJOR objection. A result
between two rungs claims the rung it implies. For example, factor 3.52, where R1 asks for 3
and R2 for 4, claims R2; the result note states 3.52.

**Allowed assumptions.** A proof that uses a simplifying assumption the lane statement allows is
MATCH, and the review records `assumes=<text>` (`review add --assumes`). A candidate's
`assumes` is the union over its gate reviews. The result then carries "(assumes: <text>)" in
record.md, ledger.md, `ri.py status`, the accepted result note and the assurance profile, and
RENEW returns a HYPOTHESIS-AUDIT successor that removes the assumption (frontier-method.md §10).

A WEAKER or DIFFERENT_MODEL result is never accepted for its claimed rung and never relabelled
in place. Keep its value this way:
1. The record shows the attempt with its fidelity objection; the review's SALVAGE line states
   what the argument does prove.
2. At the next RENEW, only the investigator may re-file it: as a lower rung whose text it
   matches, a weaker rung appended at the bottom, or a new question (DIFFERENT_MODEL: under the
   model it uses).
3. Freeze the same text for the named claim, with the original prover task as author:
   `ri.py cand add RUN --lane Q07 --claims Q07.R3 --file candidates/C014.md --author T013 --revises C014 --kind proof`.
4. Run both gates again with fresh tasks, INDIVIDUAL and SECOND-INDEPENDENT (a re-filed
   candidate is a late draft outside any cohort); fidelity is judged against the new claim.

## 5. Sanity checks and computation

Scout checks add evidence that does not share the language models' blind spots (dispatch:
proof-lane.md §2.4).
- Acceptance waits for any SANITY or WITNESS check dispatched on the candidate; `ri.py accept`
  enforces it.
- A contradiction (`contradicts`, `witness-invalid`) is an automatic CRITICAL. It blocks until
  a repair, or until an adjudication finds the scout's computation wrong.
- A SANITY domain covers only instances that meet the candidate's hypotheses and allowed
  assumptions. An instance outside them is reported separately and is not a contradiction.
- A consistent check proves nothing beyond its domain. Report the domain and the arithmetic,
  for example "n ≤ 6 passed (exact)" or "(floating point)". Floating-point output is
  numerical evidence only. Ties, thresholds and identities need exact arithmetic.
- Finite computation is part of a proof only when the candidate proves the reduction to the
  finite case, and the code, its output and any certificate are in the candidate or its hashed
  attachments (`cand add --attach`) for the verifier to check; a prover's data files are never
  filed under `scout/`. "The program printed success" is not evidence.
- "machine-checked" requires an actual proof-assistant run, with tool, version, source, output
  and trusted assumptions recorded. No language-model review grants it.
- If no check is possible, the assurance profile says "small-case check: not checkable".

## 6. Adjudication and repairs

**Adjudication.** A REPAIR draft may rebut objections in its `## Rebuttals` section, listed under
`rebuttals` in result.md. For each rebutted objection, dispatch one ADJUDICATE task (`--role
verifier --mode ADJUDICATE --objection T045.O2`; ri.py adds C014, the objection and the rebuttal):
a fresh task that is neither the candidate's author nor the objection's reviewer. `ri.py ingest`
records the ruling:
- REJECTED: the objection is resolved as rejected, and an adjudicate review with verdict PASS
  is added. The objection stops blocking C014 (§3, effective verdict).
- UPHELD: an adjudicate review with verdict FAIL. The objection stays open; route it per I8.
- A `blocking` line from the adjudicator becomes an objection of that review; a `blocking` line
  on another candidate (for example the repair draft that holds the rebuttal) becomes an
  objection of a separate adjudicate review of that candidate. The original review is always
  kept.

**Repairs.** A repair is a new candidate (`--revises Cxxx`) in the next round's cohort, gated
by fresh tasks that never see the old reviews. When the revision is accepted, close the
parent's objections that it fixed: `ri.py objection resolve RUN T045.O2 --how fixed --by C019`.
The parent stays unaccepted.

**Delta re-check.** If adjudication has rejected every CRITICAL and MAJOR objection on the
parent, and the revision changes only what MINOR or COSMETIC objections asked for, the
INDIVIDUAL gate may be a delta re-check: a fresh verifier (INDIVIDUAL, DELTA variant) gets the
old review.md, the diff and the new file, and checks each fix and that nothing else changed
meaning. The cross gate comes from the round's CROSS-DRAFT as usual. Otherwise, including while
adjudication is pending, run a full INDIVIDUAL review.

## 7. Ledger admission

The ledger holds only reusable premises (I4): accepted lane results, auditor fragments and dead
ends with an ISOLATED PASS, exclusions (§8), gated transfer rows (§1), and imported results on
request. Attempts, failed fragments and scout patterns stay in the record. `ledger add` takes
the entry's statement from the candidate's first paragraph under `## Theorem` (`## Statement`
for fragments), plus "(assumes: ...)" when set. Never pass a `--statement` that changes its
meaning.

**Fragments.** The auditor rewrites each verifier-confirmed step as a self-contained lemma
(prompts/ledger-auditor.md); a dead end (§8) is a fragment of the same kind. The ISOLATED
packet holds the fragment, the model card and the dependencies, never the parent draft;
`--from` is provenance only. A failed fragment stays in the record; a fixed fragment is a new
candidate.

**Load-bearing entries.** An entry is load-bearing if it lies in the dependency closure of an
accepted R1 candidate or of a candidate a headline cites. `ri.py status` flags the R1 case and the
closures of the presented candidates (the comparator's `selected`, or the writer's `--cand` when
no comparator ran). Each load-bearing fragment, imported result or transfer fact needs a second
ISOLATED review from another fresh task. Until it passes, the assurance profile says "second
isolated review pending" and no dependent headline is reported. If it fails, quarantine the entry
(§9).

**Imported literature results.** A cited result normally stays in its source card; verifiers
check its hypotheses at each use site (CITE). It enters the ledger only at the investigator's
request: `ri.py cand add RUN --lane Q07 --claims <claim using it> --kind imported --file
sources/S03.md --author <task that wrote the card>` (name the result, e.g. "Thm 2", in the
Assignment); one ISOLATED verifier checks it word for word against the source; then `accept`
and `ledger add --statement-file <file>` (the verbatim statement). A prior program's argument
whose status there is DRAFT, or whose review was never finished, needs its argument checked,
not only its wording: as a premise, the fragment gate (one ISOLATED review of the argument, §1);
reported as a result or a headline, the lane-result gate (INDIVIDUAL and SECOND-INDEPENDENT)
before it carries this run's label.

## 8. Exclusions, dead ends and contradictions

An exclusion records that an exact rung, in an exact model, is false (I4). There are two
routes, both after `accept`:
- a counterexample claiming Q07.Rj: `ri.py exclude RUN --claim Q07.Rj --cand C016 --note-file
  <file>` (the refuted statement and model, as restated by the INDIVIDUAL review). A skeptic's
  KILL(FALSE) witness takes this route: `ri.py cand add RUN --lane Q07 --claims Q07.Rj --kind
  counterexample --file tasks/Txxx/<witness file> --author Txxx`, then the counterexample gate of
  §1 (INDIVIDUAL, SECOND-INDEPENDENT and, if machine-checkable, WITNESS);
- a proof of D (`--claims Q07.D`): `ri.py exclude RUN --claim Q07.R1 --cand C017`, or the rung
  on the statement's "D refutes:" line; then optionally `ri.py ledger add RUN --cand C017`.

`ri.py` enforces the rules: the claim is in the candidate's own lane; a counterexample
claiming Q.Rj excludes exactly Q.Rj; a proof of Q.D excludes exactly the rung D refutes; Q.D
itself is never excluded. Because R1 ⇒ R2 ⇒ ... ⇒ Rj, refuting Rj refutes R1..Rj: one entry
covers "Q07.R1..Rj" and `refuted` is logged once for the lane. Weaker rungs Rj+1, ... stay
open. `ri.py check` re-validates every exclusion.

Not exclusions: a FAIL on a proof (the proof fails, not necessarily the claim); timeouts,
stalls and failed searches (unresolved or parked); a witness that violates a hypothesis of the
rung (fidelity failure); a counterexample to D (it implies R1 only if it is itself a full proof
of R1; do not infer).

**Dead ends.** An explicit counterexample a review gives to a step inside a draft refutes that
step, not a rung. The ledger auditor writes it as a fragment, "Dead end: <sub-claim> fails:
<instance>", proved by the witness check, frozen with `--kind lemma --from Cxxx`, gated as a
fragment (§1) and added with `ledger add`. Never `exclude` a dead end. Summarizers list dead
ends so later provers avoid the false step.

**Contradictions.** `ri.py accept` refuses (exit 1, "contradiction") a rung result covered by an
active exclusion or by an accepted counterexample or proof of D whose exclusion is still
pending, and a counterexample or proof of D that refutes an accepted rung result. `status` and
`check` report "Qxx.Ri accepted (Cxxx) and excluded (Lyyy)" (or "refuted by accepted Cyyy
(exclusion pending)"), and a candidate that passes its gates but would contradict.
An accepted result that crosses an IMP marked SURVIVES in transfer.md is the same conflict; a
worker (RENEW or a skeptic gate) names it. Either case makes the map cell `contradictory`
(RENEW marks it). Quarantine the entries involved (§9); dispatch a TARGETED literature review
and a fresh SECOND-INDEPENDENT review of the accepted proof; re-check the SURVIVES argument as
a transfer candidate (§1). This is not a too-easy event.

## 9. Quarantine

Quarantine an entry when it is found false or unsupported (by a later review, a sanity
contradiction or a failed second ISOLATED review), when its model changes, when it is part of a
contradiction (§8), or when an imported excerpt misquotes its source.

These are the only reasons (`--code`); a label in a file, or a gate's exposure to metadata, is
never one (§2). Run `ri.py quarantine RUN L005 --code <reason> --reason "<one line>"`. This marks
the entry, and transitively every ledger entry and accepted candidate that depends on it, and logs
one `model-change` event per affected lane. Quarantined items are not premises, and `cand add`
refuses them as deps. In `progress.md`, mark the affected results "quarantined".

Re-establish only through new candidates and fresh gates: a fixed lemma gets a new L-ID, and
its dependents are re-proved. History is never deleted.

## 10. Labels and assurance profile

| Label (I5) | Meaning | Granted by |
|---|---|---|
| conjecture | stated, no supporting check | any role |
| numerical evidence | consistent finite computation | a scout table |
| candidate | frozen; gates missing or failed | `cand add` |
| self-checked | gates passed, some at L1 (provisional) | `accept` |
| agent-checked | every counted gate review at L2 | `accept` |
| machine-checked | recorded proof-assistant run (§5) | the run |
| expert-verified | a human expert checked it | the user |

These labels describe this run's own checks. A result from the literature is labelled
`cited (Sxx; <status in source>)`, never with one of them: its status as its bound row records
it (theorem, informal claim, conjecture, folklore), for example `cited (S03; theorem)`. A
prior program's result adds its own status as written there, for example `cited (S12; theorem;
prior status REVIEWED)`; a prior internal review is evidence, never this run's label.

A result's reported label is the weakest label in its dependency closure. User-facing text
never says "proved", "verified" or "new" without a supporting label. Write "agent-checked
manuscript", never "verified manuscript". State novelty as "not found in search S", where S
names the search (reviewer task and coverage).

Every result reported to the user carries an **assurance profile**. Build it from `ledger.md`
and from the gate reviews' CITATIONS_CHECKED, SANITY_CHECKS and HUMAN_AUDIT_PRIORITIES:

```
Q07.R2 [agent-checked]: <exact statement> (assumes: <text> | omitted when none). Candidate C003.
Assurance: 2 independent LLM reviews (same model family; T020 individual, T024 cross),
fidelity MATCH, 4 citations checked, small-case check n <= 6 passed (exact, T022),
0 open MAJOR; depends on L003 (1 isolated review), L007 (2 isolated reviews).
Weakest link: L003 (1 isolated review).
Audit first: (1) Lemma 3, union bound over advice strings; (2) Claim 4.2, constant vs n.
```

"Audit first" is the human audit guide; a domain expert is the final verifier.

## 11. Manuscript gate

The pipeline is comparator → writer → PAPER verifier (commands, and when the comparator is
skipped: proof-lane.md §6).
- **Comparator** chooses only among accepted candidates. Among statements that imply each
  other it presents one proof, chosen by assurance (prompts/comparator.md).
- **Writer** adds no mathematics beyond the reviewers' written MINOR fills and expansions of
  routine steps, each listed in `trace.md`. New lemmas, cases, strengthenings and gap fills go
  back as `gaps_sent_back` (proof-lane.md §6). It keeps every hypothesis, quantifier, regime
  and "assumes" condition. The manuscript is self-contained for an expert who knows nothing
  about the run. Statements about the work (labels, assurance profiles, search coverage) go in
  a marked section backed by `trace.md`.
- **PAPER verifier** (prompts/verifier.md) works in two phases. Phase 1 checks the mathematics
  against the accepted candidates and lane statements, including every marked expansion (a wrong
  one is CRITICAL or MAJOR); any other new mathematical statement or step is MAJOR, used or not.
  Phase 2 then checks statements about the work against the records.

**Gate:** PAPER PASS or PASS_WITH_MINOR, and no open CRITICAL or MAJOR. Then `accept` and copy it
to `reports/` as `<name>-agent-checked-manuscript.md` (the weakest label present replaces
"agent-checked"). Only this step names a document an agent-checked manuscript; the writer labels
the results, never the document. **On PASS_WITH_MINOR**, if the user's limits allow, run one
writer revision (`--revises`) that applies the PAPER review's MINOR fills. If `ri.py cand add`
finds that the revision only inserts the review's fill blocks verbatim in their named sections, it
is accepted on that review; otherwise run a DELTA PAPER check (prompts/verifier.md) and accept the
revision if it passes. Otherwise, or if it fails, deliver the accepted manuscript with its PAPER
`review.md` (which holds the fills) next to it in `reports/`, and say so in `progress.md`. **On
failure**, the writer revises (`--revises`) and PAPER runs again within the remaining limits; a
revision that only deletes unlisted statements (fill "delete") and applies MINOR fills gets a
DELTA PAPER check. If the limits run out, deliver the document titled "draft — unresolved
objections", listing each open objection.

STOP or PAUSE overrides this pipeline: after it, dispatch no writer or PAPER task unless the
user asked for a wrap-up.
