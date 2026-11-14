# Worked example: paging with lookahead (ILLUSTRATIVE)

Readers: investigator, skeptic, literature reviewer. It shows the shape of the artifacts in
[frontier-method.md](frontier-method.md). **It is never evidence:** do not cite it; if your run's
topic is the same, use only your run's sources. Sa and Sb are symbolic source IDs. Values are
symbols, except one textbook fact: without lookahead, the best deterministic competitive ratio of
paging equals the cache size. The real literature on lookahead in paging is not summarized here;
a real run must search it.

**Request.** "Deterministic paging with a cache of k_c pages. Now the algorithm sees the next l
requests. What changes? Find new bounds and algorithms."

**Symbols.** k_c is the cache size, a parameter of the baseline. The amount of X is l (the
lookahead). c(l) is the best competitive ratio with l; the measure is minimized.

Behind the example is a classical observation: plain lookahead does not help deterministic
paging, because an adversary can repeat each request so that the window shows only copies. This
motivated "strong lookahead", which counts the window in distinct pages.

## 1. Model card (excerpt)

```
## M0 baseline (Sa §1)
Instances: a request sequence σ over a set of pages; the cache holds k_c pages.
Guarantee: A is c-competitive if some b, independent of σ, gives A(σ) ≤ c·OPT(σ) + b for every σ
  (∃A ∃b ∀σ).
Information and timing: A sees request t when it arrives; the requested page must be in the cache
  once the request is served; A pays 1 per page it loads.   Known in advance: k_c, not |σ|.
Randomness: none (A deterministic). Adversary: knows A, so it can simulate A.
Objective and measure: minimize loads; worst case; exact.   Efficiency: none required.
c0 = k_c (textbook: LRU achieves it, Sa Thm 1; no deterministic A does better, Sa Thm 2);
  regime: every k_c, asymptotic in |σ| (the additive b).
## M1 = M0 + plain lookahead (variant: requests)
Change: relaxation; quantitative.
X permits: when request t arrives, A also sees requests t+1..t+l.   Unit: one future request.
Amount: l (may be l(k_c)).   Charged as: free.   Timing: with request t.
X depends on: the instance only.   Trust: trusted.   Ignorable: yes.   Known in advance: k_c, l.
Endpoints (claims): c(0) = k_c (anchor rule: Sa's value is asymptotic in |σ|); c(∞) = 1 (with
  the whole sequence visible, A runs the offline optimum); k_triv: none bounded in k_c.
MODEL-GATE: T009 PATCH (check 7)
## M2 = M0 + strong lookahead (T009 patch, verbatim)
X permits: when request t arrives, A also sees the shortest stretch of following requests that
  contains l distinct pages other than the current one. Other fields as in M1.
Endpoints (claims): c(0) = k_c; c(∞) = 1.
## Lattice
edge M0⪯M1: f = identity (ignore the window); status: candidate
edge M0⪯M2: f = identity; status: candidate
edge M1⪯M2 (same l): f = identity (the strong window contains the next l requests); candidate
## Degeneracy log
loophole: repeated requests; neutralizing instance: each request repeated l+1 times in a row;
  patch: count the window in distinct pages; new model ID: M2
```

## 2. MODEL-GATE and LANDSCAPE

```
T009 MODEL-GATE M1: PATCH.
Check 7 NEUTRALIZATION: the adversary repeats every request l+1 times in a row. When A must load
a page, its window shows only copies of that page. Copies cost nothing. So M1[l] is no better
than M0 for every l: an "X does not help" result (transfer row Sa Thm 2 @ M1). Patch keeping the
key difference: count the window in distinct pages other than the current one (strong
lookahead). Checks 1-6: no loophole.

T004 LANDSCAPE: found: bridges; web: yes. Already studied: Sb (plain lookahead is neutralized by
repetition; strong lookahead defined; bound rows filed to sources/bounds.md).
```

The PATCH is filed verbatim as M2 (`frontier/patches/M2.md`); M1 stays for its "X does not
help" row. LANDSCAPE's `bridges` is context, read by SELECT: the M1 result is reported as known
(Sb), never as new.

## 3. Transfer audit (excerpt)

```
Result   | Side | Technique | Model  | Proof verdict                      | Bound in model | Checked                 | Questions
Sa Thm 1 | ACH  | LRU       | M1, M2 | SURVIVES-VERBATIM (identity edges) | holds          | identity edge           | -
Sa Thm 2 | IMP  | adversary | M1     | SURVIVES-BY-REDUCTION (repetition) | holds          | agent-checked (L001)    | -
Sa Thm 2 | IMP  | adversary | M2     | BREAKS-AT s2                       | open           | conjecture (audit T014) | Q07

### Sa Thm 2 (auditor T014)
Statement: no deterministic online algorithm is better than k_c-competitive (Sa Thm 2).
Steps: s1 use k_c+1 pages. s2 request the page missing from A's cache; the adversary can choose
  it because A's eviction does not depend on future requests (uses: no view of the future).
  s3 A loads on every request. s4 the offline optimum evicts the page requested furthest in the
  future, so it loads at most once per k_c requests. s5 the ratio tends to k_c.
M1: relaxed restriction: no view of the future (s2).
  Neutralization (i): repeat each request l+1 times. Each original request is to a page missing
  from A's cache when it enters A's window, so A still pays one load per original request.
  Copies are free for any algorithm that has just served the page, so OPT's cost is unchanged.
  Proof verdict: SURVIVES-BY-REDUCTION (repetition).   Bound in M1: holds, for every l.
M2: relaxed restriction: no view of the future (s2).
  Proof verdict: BREAKS-AT s2: the adversary can no longer choose after A evicts, because the
    window already shows the next l distinct pages. Beating k_c requires using them.
  Why neutralization fails: (i) copies do not count toward the window, and any request placed
    to fill it is a page A sees; (ii) re-randomizing cannot hide what a deterministic A's window
    shows; (iii) nothing in M0 reveals future pages, so no simulation with a loss exists.
  Bound in M2: open.
Hints (conjecture): ACH: on a load, evict a page that is not among the next l distinct pages.
  Repaired IMP: filling windows with pages A already holds costs A nothing and may still force a
  ratio of the form k_c − g(l).
```

The M1 row was frozen and checked once (T015, ISOLATED PASS → L001). An ADVERSARY proposer turns
the repaired-IMP hint into an IMP card for the same cell.

## 4. Scout tables

```
T005 ANCHOR (k = 0 only): exact values of the online game for k_c in {2, 3}, sequences of
  length n ≤ n0 over k_c+1 pages. Sa states only an asymptotic ratio: anchor: trend.
T011 EXPLORE (M2): gain(n), the improvement of l = 1 over l = 0, along n ≤ n0 for k_c in {2, 3};
  n/l small; no padded instances. Label: gain may vanish asymptotically (numerical evidence).
```

## 5. Vetted cards

```
Q05 (OBVIOUS-CONSTRUCTION): "In M1[l], for every l ≥ 0, some deterministic algorithm is
  k_c-competitive."
Skeptic T019: KILL(IMPLIED): by edge M0⪯M1, run LRU and ignore the window (Sa Thm 1). An
  attributed answer (follows from Sa Thm 1 via edge M0⪯M1), never a dead end; no exclusion (the
  code is not FALSE).
```

Had a card claimed "in M1[1] some deterministic algorithm beats k_c", check 3b would return
REFUTE-SKETCH: its negation follows in a few lines from the M1 transfer row.

```
# Q07 — one strong-lookahead step lowers the deterministic ratio    version: 1
Model: M2   Kind: TRADE-OFF   Tier: CORE — answers "what changes" for the main cell.
R1: There is an explicit strictly increasing h with h(1) > 0 such that, for every k_c ≥ 2 and
    every l with 1 ≤ l < k_c, an explicit deterministic algorithm in M2[l] is
    (k_c − h(l))-competitive.
R2: There is a constant δ > 0 such that, for every k_c ≥ 2, an explicit deterministic
    algorithm in M2[1] is (k_c − δ)-competitive.
R3: For k_c = 2, an explicit deterministic algorithm in M2[1] is c-competitive for some c < 2.
D:  For every δ > 0 there is k_c ≥ 2 such that no deterministic algorithm in M2[1] is
    (k_c − δ)-competitive.    D refutes: R2 (hence R1).
Strictness: R1 ⇒ R2 with δ = h(1); R2 can hold while R1 fails (longer windows add nothing).
    R2 ⇒ R3 at k_c = 2; R3 can hold while R2 fails (the gain shrinks as k_c grows). A strong
    window of size l contains one of size 1, so "every l ≥ 1 gives k_c − δ" would equal R2; R1
    asks for growth in l instead. At l = 0 all three rungs fail (Sa Thm 2).
Target cells: M2/l=O(1)/asym/ratio (ACH k_c inherited, IMP trivial) — if true: the ACH side
    drops below k_c, a separation of M0 and M2[1] (class 1); if false: "one strong-lookahead
    step gives no uniform gain" (an IMP).
Evidence: Sa Thm 2 BREAKS-AT s2 in M2 (conjecture, audit T014); scout/T011 (numerical evidence;
    small n/l, gain may vanish asymptotically).
Cheapest falsifier: the T011 game for k_c = 3 at the next length.
Nearest known result: Sb (sources/bounds.md rows).
Skeptic T020: ADVANCE; plausibility mixed (the BREAKS-AT row and T011 point to a gain; nothing
    shows uniformity in k_c). KNOWN: R1's explicit h is not in Sb's rows (search: bundle + T004).
```

Q07 passes the ready gate. Mixed plausibility makes D slots required.

## 6. Lane statement (`lanes/Q07/statement.md`)

```
Background. Read: sources/Sa.md, sources/Sb.md, frontier/model.md, ledger.md. Baseline model M0:
  <M0 tuple>.
New model M2: M0 plus strong lookahead l: when request t arrives, A also sees the shortest
  stretch of following requests that contains l distinct pages other than the current one; the
  window is free. Known in advance: k_c and l, not the length of the sequence.
Known in this model (from the frontier map, with labels): ACH k_c for every l (Sa Thm 1 via edge
  M0⪯M2); IMP 1 (trivial);
  baseline impossibility Sa Thm 2 breaks at step s2 because the window shows the next l distinct
  pages before A evicts (transfer audit, conjecture);
  small-case data (numerical evidence, non-binding): scout/T011/table.md.
Goal. Prove or disprove: <R1>.
Disproof target. D: <D>. D refutes: R2.
Ladder. If you cannot establish R1, first establish R2: <R2>; failing that R3: <R3>;
  then strengthen. Each rung is valuable on its own; label the highest rung you reach.
Ideal shape. No IMP below k_c is known in M2 yet. Once an IMP shows that the gap c(l) − 1 is
  Ω(g(l)), an ideal ACH shows it is O(g(l)).
Constraints. Deterministic algorithms; decisions depend only on k_c, l, past requests and the
  window; no running-time bound; the window counts l distinct pages other than the current one.
Allowed simplifying assumptions (to be removed later): none.
Not accepted: a different model; use of X beyond its charge; existential where explicit required.
Sanity. For k_c in {2, 3}, l = 1, all sequences of length ≤ n0 over k_c+1 pages: the candidate
  algorithm's loads are at most c·OPT + b, with c and b taken from the draft.
Literature. Reviewers may also search: lookahead, strong lookahead, look-ahead paging,
  semi-online paging.
```

## 7. One successor

Suppose C031 (Q07.R2) is accepted: `rung-accepted`, and the lane moves to R1. Later C044
(Q07.R1) is accepted: `top-accepted`; in-flight drafts finish; the lane closes resolved@R1. No
`too_easy` field fires (no verifier reported c-inf or short-proof).
RENEW T060 applies TIGHTNESS:

```
N1 → Q12   parent Q07; operator TIGHTNESS; trigger E9 (top-accepted), C044
Model M2   Kind IMPOSSIBILITY   Tier CORE   Target M2/l=O(1)/asym/ratio (one-side-missing)
R1: There is an explicit constant C such that, for every k_c ≥ 2 and every l with 1 ≤ l < k_c,
    no deterministic algorithm in M2[l] is better than (k_c − C·h(l))-competitive.
R2: R1 for the algorithm of C044 only (its analysis is tight up to the constant C). (R2 can
    hold while R1 fails: another algorithm may beat it.)
R3: R2 for l = 1 only. (R3 can hold while R2 fails: the bound may weaken faster than h.)
D:  ¬R1.    D refutes: R1.
```

R1 is class-wide (every deterministic algorithm with the same window and information); the
converse for C044's own algorithm is only the fallback rung (frontier-method.md §10).
RENEW writes `new/N1-card.md` and `new/N1-statement.md`; the successor gets a light
QUESTION-GATE. Had C044 carried "assumes: ...", a HYPOTHESIS-AUDIT successor would be required.
