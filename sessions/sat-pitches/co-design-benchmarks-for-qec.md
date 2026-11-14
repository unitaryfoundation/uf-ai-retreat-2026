---
title: "Co-design benchmarks for QEC"
session: "sat-pitches"
people: "William Zeng, plus other attendees not yet recorded"
scribe: "William Zeng (Granola recording, written up by Claude)"
---

# Co-design benchmarks for QEC

Unconference group discussion after the Saturday pitch session, from about 2:10 to 3:10 PM.

**How this note was made:** Will Zeng recorded the discussion in Granola. Claude wrote this note from Granola's AI summary, with light editing, and checked it against parts of the transcript. The transcript does not identify speakers, so points are not attributed to individuals. Participants are welcome to add their names and to correct or attribute points under Notes.

## What was discussed

### Code metrics beyond [[n, k, d]]

- The usual [[n, k, d]] framing misses the cost of manipulating logical qubits. It was proposed to report [[n, k, d, w, f]] instead:
  - **w**, the check weight, captures how hard the code is to implement.
  - **f**, the size of the logical basis, can diverge badly from the distance. Bringing f close to d typically means sacrificing something in n, k, d or w.
- For high-rate codes, the surgery gadget for logical operations is often as large as the memory code itself, or larger.
- Clifford gate counts matter more than resource estimates usually assume. In Shor's algorithm and elliptic-curve discrete log, two-qubit Clifford gates outnumber non-Clifford gates by roughly 10 to 1. In the surface code, two-qubit Cliffords are transversal, so nobody counted them. In high-rate LDPC codes, many of them need surgery and become a significant cost.
- Syndrome extraction cycle time is platform-dependent but critical. Ion traps and neutral atoms are the realistic platforms for high-rate codes, and neither [[n, k, d]] nor w captures cycle time. In end-to-end estimates, logical basis size and cycle time were named as the two most important parameters.

### Benchmark design: a single metric or co-design?

- **Proposal:** fix a circuit (for example Shor's algorithm at a reasonable size) and a physical error rate, then minimise physical spacetime volume. This avoids optimising many parameters directly, and it naturally pushes people toward transversal gates, which are about 20 to 30 times cheaper than surgery in spacetime volume.
- **Caveat:** this scores the code together with the submitter's ability to compile into it. The group felt that might be acceptable.
- **Debate:**
  - *Single layer first:* build experience first. Even writing a reliable simulator and verifier is surprisingly hard, so get good at single-layer benchmarks, then compose them.
  - *Co-design now:* single-layer code search is largely within reach once a metric is chosen. The interesting intellectual work is in co-design.
  - *Where the group leaned:* co-design is the right destination, but it needs solid single-layer verifiers as building blocks.

### Hardware design space

- There is no formal hardware spec. People work from rough, cartoonish device models.
- Neutral-atom movement constraints are changing fast:
  - Today, movement is rigid: whole rows or columns move at once, using acousto-optic deflectors (AODs). That limits practical codes to translation-symmetric families.
  - Individual-atom movement is being actively pursued and would change the accessible code space qualitatively. Some argued that AOD-style movement will remain relevant even then.
- **A forward-looking proposal:** assume unconstrained movement, modelled as constant velocity from A to B.
- **Suggested artifact:** a markdown spec per platform (neutral atom, superconducting) giving gate times, connectivity, fidelities and the movement model. It would let people ask questions like "if the field of view grows 20%, how much faster does Shor's run?" and plug different hardware backends into one benchmark suite.

### Structure of the co-design problem

- **Layers of the stack:**
  1. circuit compilation
  2. logical-to-physical mapping
  3. decoding
  4. magic-state supply
  5. heterogeneous architectures (memory regions plus distillation zones)
- **Bottlenecks:**
  - Each code needs its own decoder to map physical error rates to logical error rates.
  - Estimating logical error rates down to about 10⁻¹² needs rare-event sampling.
  - Making a given code universal through magic-state supply is non-trivial.
  - Generic surgery schemes exist, but surgery tailored to the code can give roughly a 10x improvement.
- **Symmetry and group structure** were flagged as an underexplored lever. Translation symmetry or group structure induces useful batched surgery gadgets, and the number of automorphisms might be a useful metric. *[Claude: compare Jong Yeon Lee's work on group-valued codes, linked below.]*

### Rare-event sampling and verification

- Rare-event samplers (Bravyi and collaborators were cited) estimate logical error rates. They are heuristic, with no provable upper or lower bounds, but they work well in practice for well-behaved (ergodic) decoders.
- Their cost likely scales as polylog(1/ε) in good cases, but the mixing time can blow up.
- Failure samples give an upper bound on distance, because each one is a witness for a logical failure. They do not bound the logical error rate itself.
- **Leaky verification for a leaderboard:**
  1. Run coarse verification on every submission.
  2. Spend extra compute re-verifying the top entries.
  3. Accept some leakiness: getting the direction right is enough for hill-climbing.

### Measurement-free fault tolerance and self-correcting memory

- Recent work from Markus Müller's group (recalled in the room as from around 2024) showed fault-tolerant QEC without a decoding algorithm.
  - It was demonstrated on about 8 qubits.
  - It uses non-unital noise, equivalent to measure-and-reset, plus trivial feed-forward: measure a 1, then apply a Z on that site.
  - It is decoder-free in spirit, although measurement still happens.
- **Self-correcting Hamiltonian memories:** there was skepticism. They need 4-, 6- or 8-body interactions, which are hard to engineer without stronger lower-body terms appearing too. The best Rydberg analog simulations are close but limited. Microsoft has a 4D toric code paper, and Quantinuum has implemented a 4D code, though its syndrome extraction was very complex.
- **A distinction was drawn:** a self-correcting memory is not fault-tolerant computing. Measurement-free fault tolerance is the more relevant goal.

### The Kaggle QEC challenge and benchmark design

- The public solution is at about a 25x geometric-mean improvement, and the top of the leaderboard is at about 29x.
  - Improving incrementally from the public solution is surprisingly hard, possibly because it sits in a local minimum.
  - Starting from scratch avoids that trap, but you have to climb the whole tree.
- **Competitive dynamics** came up. A strong public baseline could act as a local-minimum trap, and announcing many breakthroughs (or false ones) could act as misdirection. Even learning that a model is close to solving something is itself a valuable signal; the Collatz conjecture was the example.
- **Preferred design:** a suite of diverse problems rather than a single challenge. A suite is harder to game and gives a better signal on generalisation. A TCS exam benchmark (a mix of Lean problems) was cited as a good model.
- **End-to-end co-design challenge:**
  - Input: a fixed circuit, such as a ripple-carry adder or Shor's algorithm.
  - Output: a full compilation to physical operations, with qubit count and runtime at a given physical error rate.
  - Non-optimal choices are fine; the community fills in the gaps over time.

## Problems, tools or structures that came up

- [Add frame width to the objective for good codes in the UF QEC challenge](../../charts/structures/qec-challenge-frame-width-objective.md). The logical-basis-size parameter f discussed here is the same concern.
- [A buildable self-correcting quantum memory in three dimensions](../../charts/problems/william-zeng-10x.md). The skepticism above about many-body interactions bears on it.
- UF's [agentic leaderboards](https://unitary.foundation/posts/2026_agentic_leaderboards/), the context for the leaky-verification and benchmark-suite discussion.

## Next steps

These come from the Granola summary; no owners were assigned in the recording.

- Look up the Markus Müller measurement-free fault tolerance paper, and confirm its platform, qubit count and feed-forward scheme.
- Draft hardware-constraint specs for neutral-atom and superconducting platforms: gate times, connectivity, fidelities and movement model.
- Define an end-to-end co-design benchmark around a fixed circuit, such as a ripple-carry adder or Shor's algorithm. Its output would be physical spacetime volume at a fixed error rate, with leaky verification acceptable to start.

## Open questions

- Should the first benchmark be single-layer or end-to-end co-design?
- What hardware model should the co-design benchmark assume, given how fast neutral-atom capabilities are changing?
- Is the number of automorphisms a useful code metric?

## Notes

_Participants: add your name, and attribute or correct points above._
