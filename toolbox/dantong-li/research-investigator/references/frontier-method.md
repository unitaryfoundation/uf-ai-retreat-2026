# Frontier method: templates and research method

Readers: the investigator (all of it), the skeptic (§1–§7), literature reviewers (§1, §2, §4),
scouts (§1) and the comparator (§7). The orchestrator does not read this file; its operations are
in [program.md](program.md). An illustration is in [worked-example.md](worked-example.md); it is
never evidence.

The program studies "task T, now with resource X". When X is an amount, the answer is usually a
curve: how the best achievable value changes with the amount of X. Otherwise it is a table of
separations, conversion costs or trade-offs (the frames of §1); never invent an amount. The
method: find which old proofs survive X; try both the most natural construction using X and
the neutralization of X before believing X helps; propose questions where proofs break; vet
them cheaply; then prove.

## 1. Core notions

- **ACH and IMP.** ACH (achievability) is what some protocol achieves. IMP (impossibility) is
  what no protocol in a stated class can beat. "Upper" and "lower" bound swap meaning between
  minimized measures (cost, regret) and maximized ones (ratio, revenue); ACH and IMP do not.
  "Beats" always means better in the measure's direction.
- **c(k, n)** is the best guarantee any protocol of the model achieves with k units of X on
  instances of size n (worst case over those instances). **c0** is the baseline value (k = 0) in
  the regime its source states: a finite-n value, a per-instance guarantee, or an asymptotic
  constant (a limit, or a bound with o(1)).
- **THRESHOLD** is the least growth rate k(n) such that liminf over n of c(k(n), n) beats c0 by a
  margin δ > 0 independent of n (state δ, or write "some δ > 0"). **SATURATION** is the least
  growth rate k(n) such that c(k(n), n) is within o(1) (or a stated margin) of c(∞).
  **TRADE-OFF** is the curve between them. A strict gain at a fixed n is a **finite-n gain**:
  record it separately; it is never THRESHOLD evidence by itself. An exact optimum at stated
  finite parameters with a checkable certificate (an LP or ILP dual, exhaustive enumeration) is
  mathematics for exactly those parameters: it may be a map cell or a rung ("at n = 5"), tied to
  the user's named design dimensions, and is accepted under I3 like any rung. Its statement's
  Sanity line names an exact re-check of the certificate (scout SANITY).
- **Frames** (the model card's Frame line). RESOURCE-CURVE: X is an amount k; the grid is k
  against n; standing questions THRESHOLD, SATURATION, TRADE-OFF. ON-OFF: X is present or not,
  or is a conversion or simulation relation between two task classes or frameworks; SEPARATION
  (in which regimes X changes the value at all) and EQUIVALENCE (the cost of simulating X with
  old resources) replace the curve questions, and the map is a directed graph of simulation
  edges, separations and conversion costs. COMBINATION: X joins two ideas; the map is a 2-D
  trade-off between their native resources, with integration levels as variants. With several
  mechanisms, keep one M0 and one labelled variant per mechanism. The k = 0 tests apply only in
  RESOURCE-CURVE; elsewhere k = 0 means "X absent".
- **Untrusted X** (predictions, noisy advice): the quality of X is an error measure η. The object
  is the Pareto frontier of consistency (value at η = 0), robustness (value at the worst η) and
  smoothness (how the value degrades with η).
- **Anchor rule (like with like).** A finite-n value that a source states must be matched
  exactly. A per-instance guarantee ("ratio ≥ c on every instance") must hold at each n. An
  asymptotic constant is compared as a trend; a finite-n difference from it never shows by
  itself that a model or code is wrong. A claim compared with an asymptotic c0 states a margin
  independent of n, or a liminf.
- **Simulation edge** `Ma ⪯_f Mb`: every protocol of Ma runs in Mb with overhead f. ACH results
  move up an edge (Ma to Mb); IMP results move down. Status: candidate, literature-checked,
  agent-checked (Lxxx), refuted. Name an edge by its endpoints (`edge M0⪯M2`); `E#` always means
  an event.
- **Neutralization.** An adversary may make X useless: (i) by transforming instances (padding
  with dummy requests, dilution, duplication, scaling, disjoint union with decoys); (ii) by a
  re-randomized hard distribution in which what X reveals is independent of the decision at the
  critical step; (iii) or X may be simulated by old resources with a loss (for example, guessing
  k advice bits loses at most a factor 2^k on a maximized ratio). A neutralized X gives an "X does
  not help" result, never a gain.

## 2. Model card (`frontier/model.md`)

```
## M0 baseline (S02 §2)
Instances: ...                     Guarantee, with quantifier order: ...
Information and timing: ...        Known in advance: <n, horizon, distribution, ...>
Randomness: <private/public; what the adversary sees>     Adversary: <oblivious/adaptive>
Interaction/rounds: ...            Objective and measure: <worst/average; exact/approx; max/min>
Efficiency: ...                    c0: <value; regime finite n | per instance | asymptotic; locator>
## M1 = M0 + X (variant: <label>)  [fields that differ, plus:]
Change: relaxation | restriction | replacement; quantitative | on-off
Frame: RESOURCE-CURVE | ON-OFF | COMBINATION (§1)
X permits: ...  Unit: ...  Amount k (may be k(n)): ...  Charged as: ...  Timing: ...
X depends on (oracle-type X): instance only | instance and coins | adversary-chosen
Trust: trusted | untrusted (quality of X: error measure η, range)
Ignorable (may protocols ignore X?): yes | no
Endpoints (claims): c(0) = c0 (anchor rule); c(∞) = <value>; k_triv = <least k making the task
  trivial> | none
MODEL-GATE: <Txxx verdict>
## Lattice
edge M0⪯M1: f = <overhead>; status: candidate
## Degeneracy log
loophole; trivializing or neutralizing instance; patch; new model ID
```

- User notes in the bundle state the user's intent: their definition of X comes before your
  reading. Ambiguous wording becomes several labelled variants, not a question to the user.
- Adopt the nearest source's standard cost model (query count, gate count, word-RAM, uniform
  circuits) verbatim. Keep the information-theoretic model separate from operational ones;
  operational costs enter a statement's Constraints only when its claim is operational.
- **Relaxation** (X can be ignored): edge M0⪯M1 with f = identity, so old ACH results survive.
  **Restriction or replacement:** old ACH results go on the transfer-audit list too.
- **k_triv is recorded, not patched away.** Rows with k ≥ k_triv are trivial; the interesting
  regime is k much smaller than k_triv. A patch is only for accounting loopholes (uncharged X,
  information hidden in timing or precision), as MODEL-GATE decides.
- Never edit a gated model. A change creates a new model ID; a MODEL-GATE patch is filed
  verbatim as one (`frontier/patches/M<n>.md`), and you fold it into model.md at SELECT or RENEW.
- Write a self-contained file `edge-Ma-Mb.md` for every edge whose f is not identity, and request
  its transfer gate.

## 3. Frontier map (`frontier/map.md`)

A cell key is `<model>/<k regime>/<other regime>/<measure>`, for example `M1/k=O(1)/asym/ratio`.

```
# Frontier map — measure: <competitive ratio, maximize>
## Grid M1   (each cell: gap class / status / questions)
k \ n           | small n (n ≤ n0)      | asymptotic n
k = 0 (anchor)  | closed / tight        | closed / tight
k = O(1)        | inherited-only / open | inherited-only / open (Q07)
k = polylog n   | unsearched            | unsearched
unlimited       | closed / tight        | closed / tight
## Cell M1/k=O(1)/asym/ratio
ACH: <expression>; construction; efficiency; scope; evidence (S02 Thm 1, L004, or "derived via
     edge M0⪯M1 from M0/asym/ratio"); label
IMP: <same fields; scope = all protocols in class C>
Gap: <class>   Status: <status>   Questions: Q07, Q09
## Curves: THRESHOLD ... (Q..); SATURATION ... (Q..); TRADE-OFF ... (Q..)
## Invariant checks
## Breadth reviews
```

- Rows: amounts of X (k = 0 anchor, O(1), polylog, poly, unlimited anchor, or the task's
  natural regimes). Columns: the other main parameter regime × measure. Untrusted X: columns are
  (consistency, robustness) pairs.
- Gap class: closed, constant, log, poly, exponential, one-side-missing, inherited-only (both
  sides come only from M0: X unexplored), contradictory. Status: tight, open, unsearched,
  excluded.
- Label: the I5 label for run results; `cited (Sxx; <status in source>)` for literature. An entry
  derived from a transfer row reads "conjecture (audit Txxx)", or "conjecture (audit Txxx;
  SURVIVES, ungated)" for a SURVIVES row, until the row's gate gives Lxxx.
- Standing questions per model: THRESHOLD, SATURATION, TRADE-OFF (or SEPARATION, EQUIVALENCE).
- **Invariant checks** at every update: ACH never beats IMP in one cell; c is monotone in k when
  X is ignorable; values agree across edges. An accepted result that crosses an IMP whose row says
  SURVIVES, or crosses an active exclusion, makes the cell **contradictory**. Report it in your
  `contradiction` field; the orchestrator quarantines and re-checks both sides. It is never a
  "too easy" result.

## 4. Transfer audit (`frontier/transfer.md`)

Reviewers draft rows in their task directories; the investigator integrates them at SELECT or
RENEW.

```
Result    | Side | Technique | Model | Proof verdict                    | Bound in model | Checked                 | Questions
S03 Thm 2 | IMP  | Yao       | M1    | SURVIVES-BY-REDUCTION (padding)  | holds          | agent-checked (L002)    | -
S03 Thm 2 | IMP  | Yao       | M2    | BREAKS-AT s3                     | open           | conjecture (audit T014) | Q07

### S03 Thm 2 (auditor T014)
Statement (verbatim, locator):
Steps: s1 ...; s2 ...; s3 "<quote>" uses <restriction of M0>
Per model:
  Relaxed restrictions used: <restriction; steps>
  Neutralization tried: (i) transformations ...; (ii) re-randomized distribution ...;
    (iii) simulation of X with loss ...
  Proof verdict, one of:
    SURVIVES-VERBATIM: <inclusion or simulation argument>
    SURVIVES-WITH-LOSS f: <f and argument>
    SURVIVES-BY-REDUCTION <transformation>: <how it restores the restriction; the bound in M>
    BREAKS-AT s: <quote s; the restriction X relaxes; what any protocol beating the bound
      must exploit>
      Why neutralization fails: <one line per attempt>
    UNCLEAR: <what would decide it>
  Bound in model: holds | fails | open
Constructions: bottleneck step; does X reduce exactly that cost?
Hints (conjecture): improved-protocol idea; repaired IMP that may survive
```

- **Rule.** If X is optional, old ACH results survive. An old IMP survives verbatim if no
  load-bearing step uses a relaxed restriction. Otherwise, try to restore the restriction by
  neutralization before calling the proof broken. A broken proof shows that the proof fails, not
  that the bound fails: "Bound in model" is `fails` only when an ACH in the model beats it.
- SURVIVES rows give "X does not help" theorems when M0 is tight (ACH = IMP). BREAKS-AT rows are
  the main source of ACH conjectures; each one also deserves an IMP card (ADVERSARY or BARRIER
  lens).
- **Light gate.** Every edge whose f is not identity, and every SURVIVES verdict on an IMP
  result that a statement, a headline or a draft cites (program.md §5.4), is frozen and checked
  once by a fresh verifier (verification.md); until then the row is a conjecture. So each
  `transfer-<model>.md` and `edge-Ma-Mb.md` must be self-contained: checkable against the source
  and the model card alone. "Checked" shows agent-checked (Lxxx) or conjecture (audit Txxx; a
  SURVIVES row adds "; SURVIVES, ungated").

## 5. Question card (`questions/Qxx.md`)

```
# Q07 — <title>    version: 1    status: draft
Model: M2   Kind: <kind>   Tier: CORE — <two-line reason>
Serves: <SAFE only: the card it serves>   Certifies: <TRANSFER/SURVIVAL only: row or edge>
R1: <exact: quantifiers in order, parameters, error probability, uniformity, how X counts>
R2: <R1 ⇒ R2; holds where R1 may fail: <regime or class>>
R3: <lowest rung not implied by the nearest known result, closable in 1–2 rounds>
D:  <disproof target; default ¬R1>        D refutes: R1 (default) | Rj
Current rung: R1   Slots: <prover slots per round>
Target cells: <key> — if true: <map change>; if false: <map change>
Evidence: <scout tables with ranges and n/k; transfer rows with labels; analogies and where
  they break; Qa ⇒ Qb>
Cheapest falsifier: ...   Nearest known result: <locator>; gap step: <the step R1 needs beyond it>
Lineage: parent Qxx | user | prior program; operator; trigger (event E#, C###/L###/T###)
Skeptic: <Txxx verdict; plausibility supported/mixed/doubtful; one line>
Park/kill: <reason; resurrection condition>
History: <v1 Txxx created; v2 Tyyy REFORMULATE ...>
```

**Ladder rules.**
1. Nested: R1 ⇒ R2 ⇒ ... . D implies the negation of the rung in "D refutes". Refuting Rj also
   refutes every stronger rung.
2. Strict: for each Ri+1, name a regime or instance class where Ri+1 holds and Ri may fail.
   Before calling two rungs distinct, check monotonicity in k (X can often be partly discarded,
   so "for every k ≥ 1" may equal "k = 1") and rescaling. Rungs that one argument covers
   equally (for example by fixing a parameter of the hypothesis) are not distinct; rungs that
   differ in the target value of a bound are.
3. About X: an ACH rung must not be achievable by a protocol that ignores X (test it at k = 0);
   an IMP rung must not follow from a baseline IMP that survives in the model. Either is
   IMPLIED, not a question about X. A rung that decides the comparison, conversion or
   combination the user named is about X even if X drops out of its proof.
4. Uniform: a rung compared with an asymptotic c0 has a margin independent of n, or a liminf.
5. Restricted-instance rungs ("on family F") are weak evidence for worst-case questions. Prefer a
   restricted regime or a restricted algorithm class.
6. Value cells (a best ratio, a threshold): R1 is the tight value or the strongest two-sided
   statement the evidence supports; a one-sided bound that certified numerics already support
   is a lower rung.

Kinds: CONSTRUCTION, IMPOSSIBILITY, TIGHTNESS, THRESHOLD, TRADE-OFF, SEPARATION,
TRANSFER/SURVIVAL, EFFICIENCY, ROBUSTNESS, SPECIAL-CASE. Statuses: draft → vetting → ready →
active → resolved(@rung), refuted, parked, killed (the orchestrator mirrors them in state). Once
a lane is active, the rung texts, D, the model and the Constraints are frozen: append a weaker
rung or create a successor.

## 6. Lane statement (`lanes/Qxx/statement.md`)

The only problem statement provers see. It says what to establish, never how. Use this
Appendix-A template exactly:

```
Background. Read: <paths to source cards / papers / ledger entries>. Baseline model M0: <tuple>.
New model M<k>: <tuple; what X permits; unit and charging of X; what is known in advance>.
Known in this model (from the frontier map, with labels): ACH ...; IMP ...;
  baseline impossibility <S03 Thm 2> breaks at step s because ... (transfer audit, <label>);
  small-case data (numerical evidence, non-binding): <scout table path>.
Goal. Prove or disprove: <R1>.
Disproof target. D: <D>. D refutes: <R1 | Rj>.
Ladder. If you cannot establish R1, first establish R2: <...>; failing that R3: <...>;
  then strengthen. Each rung is valuable on its own; label the highest rung you reach.
Ideal shape. <see below>.
Constraints. <solution class; what the protocol may depend on; efficiency; how X is counted>.
Allowed simplifying assumptions (to be removed later): <... | none>.
Not accepted: a different model; use of X beyond its charge; existential where explicit required.
Sanity. <scout check: predicate and small domain> | not checkable (<reason>).
Literature. Reviewers may also search: <aliases of X>.
```

- **Ideal shape**, orientation-free: if an IMP shows that the gap |c(k) − r| to a reference value
  r is Ω(g(k)), an ideal ACH shows it is O(g(k)). Maximized measure: an IMP c(k) ≤ 1 − Ω(1/√k)
  suggests aiming for an ACH c(k) ≥ 1 − O(1/√k). Minimized measure: an IMP c(k) ≥ 1 + Ω(1/k)
  suggests aiming for an ACH c(k) ≤ 1 + O(1/k).
- **Constraints** may not grant information absent from the model card (knowledge of n, the
  horizon, a distribution). Create a model variant instead.
- **Sanity** tells the orchestrator which scout check to run on candidates; it never asks the
  orchestrator to judge computability.
- Never include tiers, plausibility, scores or method hints. Revisions take effect at the lane's
  next PLAN and are logged in the card's History.

## 7. Story, significance and too-easy signals

```
## H1 (leading) — <one-sentence theorem as an expert would state it>
Plain statement: <the result in words, every symbol defined; progress.md copies this line>
Needs: Q07.R1 (accepted C031), Q12.R1 (open)    Missing: ...
Skeptic CLAIM-GATE: <Txxx: QUALIFY — "...">
Caveats: <CLAIM-GATE qualifiers and MODEL-GATE corrections, verbatim | none>
Significance: class <1–5>; expert surprise: <evidence; omit this part without evidence>
```

Without evidence of surprise for any headline, write "no evidence of surprise" once, in the
story header.

At most 3 headlines; at least one lane serves the leading headline's gap.

**Significance rubric**, strongest first:
1. **Qualitative change:** a separation between models, a different asymptotic order, an exact
   threshold ("no gain for k = o(f(n)), gain for k = Ω(f(n))"), or a broken named barrier.
2. **Tight characterization:** matching bounds or an exact trade-off curve, including "X provably
   does not help (for k = o(f(n)))" with a matching ACH.
3. **Resolution of a stated open problem** (cite it).
4. **Constant or log improvement:** valuable mainly when the constant is the stated question
   (compare 5.2 → 3.52 in the paper).
5. **Generalization with no new idea.**

**Expert-surprise test.** State the result in one sentence for an expert in the baseline. Claim
surprise only with evidence: a source's stated belief or open problem (locator), an obvious
approach that provably fails (ledger or transfer row), or a circumvented barrier (locator).
Otherwise write "no evidence of surprise".

**Too-easy signals:** the result meets the c(∞) value on the model card (`c-inf`), or its proof is
far shorter than the baseline's (`short-proof`). Report them in a `too_easy` field; the
orchestrator then dispatches skeptic MODEL-GATE and CLAIM-GATE. Crossing a SURVIVES row or an
exclusion is a contradiction (§3), not a too-easy signal.

## 8. Proposal lenses (one per PROPOSE task)

The orchestrator assigns lenses mechanically (program.md §5.1).
- **TRANSFER/BREAK:** for each BREAKS-AT row, a protocol exploiting exactly the restriction
  relaxed at step s, and the repaired IMP that should still hold.
- **ADVERSARY:** the most natural adversary against protocols with k units of X: one that
  neutralizes, dilutes, delays or blinds X, or adapts the baseline hard distribution so that X
  reveals nothing at the decisive step. Its value as a function of k; where it loses. It yields
  IMP cards and "X does not help" cards.
- **CURVE/EXTREMES:** THRESHOLD, SATURATION and TRADE-OFF (§1), anchored at k = 0 and k = ∞ (or
  k_triv), with the form taken from the opposite bound (Ideal shape). Untrusted X: the
  consistency–robustness curve and smoothness in η. TRADE-OFF also covers X against time, space
  or rounds.
- **OBVIOUS-CONSTRUCTION:** the most natural protocol using X; its exact guarantee; where its
  analysis loses; is it optimal?
- **SMALL-CASE DATA:** closed forms fitted to scout tables, with the range, n/k, the weakest point
  and the next distinguishing value. A table with small n/k may hide a gain that vanishes
  asymptotically.
- **ANALOGY/SIMULATION:** is X a known resource Y in disguise (advice, predictions, lookahead,
  shared randomness, preprocessing, extra rounds, recourse)? Import Y's trade-offs, separations
  and known neutralization tricks; say where the analogy breaks.
- **BARRIER:** for each IMP technique (adversary, Yao, information, fooling set, reduction,
  counting, potential): if X defeats it, propose a separation; if not, a robust bound.

## 9. Portfolio (investigator, SELECT and RENEW; coarse, no numeric scores)

Tiers: **SAFE** (likely to close in a few rounds; fills a cell or yields a reusable lemma; names
the card it serves); **CORE** (directly answers the key-difference question for a main cell);
**AMBITIOUS** (a class 1–2 result at lower odds); **EXPLORE** (a cheap probe of a neglected cell
or lens).
- Prover slots over time: roughly 40% CORE, 25% SAFE, 20% AMBITIOUS, 15% EXPLORE. Rotate
  AMBITIOUS and EXPLORE when capacity is small. The advisor may tune these defaults.
- At most max(2, ⌊K/2⌋) active lanes by default (gate-only rounds do not count); ready questions
  wait.
- At small K, commit lanes to one or two tracks, in the user's priority order (contract.md "From
  your notes") unless evidence says otherwise; other tracks stay map rows with a resurrection
  condition and get no audits or scouts until a lane frees.
- Transfer rows: BREAKS-AT gives an ACH card and an IMP card for the same cell; a gated
  SURVIVES row with tight M0 is already an "X does not help" result, and a lane may extend it to
  a wider range of k; UNCLEAR gives SPECIAL-CASE questions or TARGETED searches.
- Good first lanes: the earliest BREAKS-AT step, or extending a SURVIVES-BY-REDUCTION row.
- D slots follow the skeptic's plausibility and the slot count mechanically; you never set them.

## 10. Successor operators (RENEW; at most 3 per event)

Each successor names its operator, parent, trigger, target cell, and its gap step: the closest
ledger entry or edge, and the step R1 needs beyond it.

**After ACCEPT.** HYPOTHESIS-AUDIT (list the hypotheses actually used; drop unused ones;
generalize; required when the result carries "assumes: ..."). TIGHTNESS (the converse, if no
matching bound exists, stated first for the whole class the result competes in: every algorithm,
protocol or mechanism with the same constraints, information, incentives and resource
accounting, as a class-wide lower bound or impossibility; the converse for the specific object,
this mechanism or this algorithm, is the fallback rung (R2), never the only rung). BOTTLENECK
(target the lossiest step). PARAMETERIZE (explicit dependence on k: a curve instead of a point).
EXTEND-REGIME (n = 2 → general n; fixed k → k(n)). ROBUSTNESS (untrusted or noisy X,
corruption). ECONOMIZE (the same guarantee with less X or less time). TRANSFER (a sibling
problem in the bundle).

**After REFUTE.** READING first, whenever the witness relies on a boundary convention, a
definitional inconsistency in the sources, or a case the user's wording plausibly excludes
(restate the claim under the natural reading, with the evidence for it: the sources' other
definitions and examples, the original reference, the reading that keeps the claim non-trivial;
the literal refutation stays a reported result). HARVEST (the witness family as an IMP instance
for the cell). BOUNDARY (the largest regime where the claim holds; the threshold where it first
fails). MINIMAL-HYPOTHESIS (the smallest natural extra hypothesis excluding the witness). CORRECT
(the form the witness suggests).

**After STALL.** DESCEND (the next weaker rung). SPECIALIZE (n = 2, k = 1, or a restricted
algorithm class). SPLIT (along ledger lemmas). FLIP (attack the opposite side).
RESTRICTED-CLASS ("no protocol of type T beats ...", a result in its own right). BARRIER (test
the stuck sub-claim on small cases; check known barriers). COMPUTE (a scout CERTIFY task on the
stuck inequality; its certificate reaches provers through summarizers as a labelled conjecture).
PARK (with a resurrection condition).
