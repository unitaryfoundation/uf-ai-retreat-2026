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

### Google's Kaggle circuit-compilation challenge and benchmark design

*[Claude: an earlier version of this note called this the "Kaggle QEC challenge". See the corrections in the commentary below.]*

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

- Look up the Markus Müller measurement-free fault tolerance paper, and confirm its platform, qubit count and feed-forward scheme. *[Claude: done; see the corrections in the commentary below.]*
- Draft hardware-constraint specs for neutral-atom and superconducting platforms: gate times, connectivity, fidelities and movement model.
- Define an end-to-end co-design benchmark around a fixed circuit, such as a ripple-carry adder or Shor's algorithm. Its output would be physical spacetime volume at a fixed error rate, with leaky verification acceptable to start.

## Open questions

- Should the first benchmark be single-layer or end-to-end co-design?
- What hardware model should the co-design benchmark assume, given how fast neutral-atom capabilities are changing?
- Is the number of automorphisms a useful code metric?

## Commentary: literature, ideas and future directions

**Everything in this section was added by Claude afterwards, at Will Zeng's request. None of it was said in the room.** Papers marked † were found or confirmed by web search on 2026-11-14, from abstracts and search summaries only. Unmarked references are from Claude's memory and their arXiv numbers were not re-checked today. Nobody has read the full texts for this note, so check a paper before relying on it.

### Two corrections to the notes above

- **The "Kaggle challenge" is a circuit-compilation challenge, not a code-discovery one.** The transcript refers to a Google challenge on Kaggle. That matches Google Quantum AI's [Verifiable Quantum Circuit Compilation competition](https://opensource.googleblog.com/2026/10/announcing-verifiable-quantum-circuit-compilation-competition-on-kaggle.html)†, which runs from October 22, 2026 to January 20, 2027. Entrants use AI agents to shrink fault-tolerant logical circuits, and an open-source fuzz-testing verifier checks them. UF's own [QEC Challenge](https://unitary.foundation/posts/2026_qec_challenge)† is a separate leaderboard for codes, hosted on GitHub. The section heading has been corrected.
- **The measurement-free experiment was on trapped ions.** The first next step can be closed:
  - Theory: Heußen, Locher and Müller, *Measurement-free fault-tolerant quantum error correction in near-term devices*, [arXiv:2307.13296](https://arxiv.org/abs/2307.13296)† (PRX Quantum, 2024).
  - Experiment: [*Demonstration of measurement-free universal logical quantum computation*](https://www.nature.com/articles/s41467-026-68533-x)† (Nature Communications, 2026). It ran on a trapped-ion processor with error-detecting codes, so it is not yet a full error-correction cycle. The "likely superconducting" recollection in the room does not match.
  - Follow-ups: a neutral-atom scheme ([arXiv:2404.11663](https://arxiv.org/abs/2404.11663)†) and a universal toolbox using code switching and concatenation ([arXiv:2410.13568](https://arxiv.org/abs/2410.13568)†).

### Related literature

**Metrics beyond [[n, k, d]], and the cost of logic**

- Jong Yeon Lee's [arXiv:2610.06820](https://arxiv.org/abs/2610.06820)† defines *frame width*, a precise version of the logical-basis-size parameter f from the discussion. The companion paper [*Design Principles for Ultra-High-Rate Quantum Codes*, arXiv:2609.30069](https://arxiv.org/abs/2609.30069)† covers symmetry-aware searches for low-weight logical bases.
- [*Shor's algorithm is possible with as few as 10,000 reconfigurable atomic qubits*, arXiv:2603.28627](https://arxiv.org/abs/2603.28627)†. This is an end-to-end estimate on high-rate qLDPC codes, with logical gates done by Pauli product measurements. It is close to a worked example of the proposed benchmark.
- [*High-rate qLDPC processors*, arXiv:2607.28795](https://arxiv.org/abs/2607.28795)† ("mitten" codes built from non-abelian groups) and [RASCqL, arXiv:2602.14273](https://arxiv.org/abs/2602.14273)† are recent architectures that treat the code as a processor, not only a memory.
- Surgery overhead: Cohen, Kim, Bartlett and Brown (arXiv:2110.10794) for generic qLDPC surgery; Cross et al. (arXiv:2407.18393) for improved surgery; Yoder et al., *Tour de gross* (arXiv:2506.03094), for a full bicycle-code architecture.
- Surface-code baselines to compare against: Gidney's RSA-2048 estimate under a million qubits (arXiv:2505.15917) and Litinski's 256-bit elliptic-curve estimate (arXiv:2306.08585).

**Cheap Cliffords from symmetry**

- Breuckmann and Burton, [*Fold-Transversal Clifford Gates for Quantum Codes*](https://quantum-journal.org/papers/q-2024-06-13-1372/)†.
- Sayginel et al., [*Fault-Tolerant Logical Clifford Gates from Code Automorphisms*, arXiv:2409.18175](https://arxiv.org/abs/2409.18175)†. It gives an algorithm that finds these gates for any stabilizer code.
- Malcolm et al., [*Computing Efficiently in QLDPC Codes*, arXiv:2502.07150](https://arxiv.org/abs/2502.07150)† (SHYPS codes). Automorphisms give CNOTs and diagonal Cliffords at low depth.
- A limit: [arXiv:2602.13395](https://arxiv.org/abs/2602.13395)† argues that automorphisms and fold-transversal gates cannot generate the full Clifford group on more than two logical qubits. Some surgery or code switching is therefore unavoidable.

**Rare-event sampling**

- Bravyi and Vargo, [*Simulation of rare events in quantum error correction*, arXiv:1308.6270](https://arxiv.org/abs/1308.6270)†: the splitting method that the room was describing.
- [*Rare Event Simulation of Quantum Error-Correcting Circuits*, arXiv:2509.13678](https://arxiv.org/abs/2509.13678)† extends it to circuit-level noise.
- [*Fast and accurate rare-event simulation by Markov chain Monte Carlo for general quantum codes*, arXiv:2610.35498](https://arxiv.org/abs/2610.35498)† is from last month.

**Hardware models**

- Beverland et al., *Assessing requirements to scale to practical quantum advantage* (arXiv:2211.07629). This is the basis of the Azure Quantum Resource Estimator, which already takes parameterised hardware profiles. It is a precedent for the per-platform spec file.
- Xu et al., *Constant-overhead fault-tolerant quantum computation with reconfigurable atom arrays* (arXiv:2308.08648), and Bluvstein et al., *Logical quantum processor based on reconfigurable atom arrays* (arXiv:2312.03982), for movement models.
- Zhou et al., *Algorithmic fault tolerance for fast quantum computing* (arXiv:2406.17653), for why cycle time and transversal gates dominate runtime on atoms.

**Self-correcting memories and 4D codes**

- [*A passive self-correcting quantum memory in three dimensions*, arXiv:2605.10943](https://arxiv.org/abs/2605.10943)† (May 2026). The abstract claims a 3D Pauli stabilizer Hamiltonian that stores a qubit for exponential time at non-zero temperature. One secondary report says stability under perturbations is not yet proven. This bears directly on [Will's 10x problem](../../charts/problems/william-zeng-10x.md): if the result holds, the open question shifts from existence to buildability, which is exactly where the room's skepticism about many-body terms applies.
- Earlier candidates: layer codes and Williamson's [*Partial Self-Correction in Layer Codes*, arXiv:2510.09218](https://arxiv.org/abs/2510.09218)†; Lin, Wang and Hsieh, [arXiv:2411.03115](https://arxiv.org/abs/2411.03115)†; cored product codes, [arXiv:2510.05479](https://arxiv.org/abs/2510.05479)†. Review: Brown et al., [arXiv:1411.6643](https://arxiv.org/abs/1411.6643)†.
- The 4D papers mentioned in the room: Microsoft's 4D geometric codes, [arXiv:2506.15130](https://arxiv.org/abs/2506.15130)†, and Quantinuum's [*Experiments with the 4D Surface Code on a QCCD Quantum Computer*, arXiv:2408.08865](https://arxiv.org/abs/2408.08865)†.

### Ideas and future directions

1. **A layered benchmark settles the single-layer versus co-design debate.**
   - Define the end-to-end task once: a fixed circuit, a fixed hardware profile, and spacetime volume at a target failure budget.
   - Ship a deliberately non-optimal reference implementation for every layer (code, compiler, surgery scheme, decoder, magic-state factory).
   - A submission may replace any one layer or several. Single-layer work then counts as progress on the co-design score, and each layer's verifier is the building block the room asked for.
2. **The middle of the stack is the gap.** Google's Kaggle competition scores logical circuits. UF's QEC challenge scores codes. Nothing public scores the step between them: compiling a logical circuit onto a specific code and platform. A UF benchmark could take the best logical circuits from the Kaggle competition as fixed inputs and score only that step.
3. **Verify with witnesses wherever possible.**
   - For f, the submitter supplies a full logical basis. The verifier checks the commutation relations and the weights, which is cheap. That certifies an upper bound on frame width without the verifier having to search for one.
   - Distance upper bounds work the same way: a low-weight logical operator is a witness.
   - Lower bounds and logical error rates have no cheap witness. That is where the leaky verification has to live.
4. **Make leaky verification adversarial.** Claims are expensive to confirm but cheap to refute, because one low-weight logical operator or one failing fault configuration disproves an entry. The leaderboard could give credit for breaking entries as well as for submitting them. It would then tighten over time without UF paying for all the compute.
5. **Require two independent estimates of the logical error rate.** Rare-event samplers have no guarantees and can mix slowly. For top entries, require agreement between a splitting or MCMC estimate and a second method, such as direct sampling at higher error rates with extrapolation. Flag entries where the two disagree. Publish the decoder with each entry so others can reproduce the estimate.
6. **Version the hardware specs and report sensitivity.**
   - Keep one machine-readable spec per platform with named profiles: "rigid row and column moves today", "individual-atom moves", "unconstrained".
   - Report each entry under every profile, so results are not overfitted to one device generation.
   - Report how the score changes with each hardware parameter. That tells hardware teams which improvement buys the most, which is the "field of view grows 20%" question from the discussion.
7. **Use a better symmetry metric than the automorphism count.** Counting automorphisms is crude. A sharper metric is the size of the logical Clifford subgroup that automorphism and fold-transversal gates generate, which the Sayginel et al. algorithm can compute. Sharper still is the fraction of the benchmark circuit's two-qubit Cliffords that can be compiled into those cheap gates. Given the no-go result above, that fraction is always below one for large codes, so it is a meaningful number to climb.
8. **Start with a small fixed circuit.** A ripple-carry adder of a few dozen bits is small enough to verify end to end, and it already has Clifford-heavy structure. It can grow to elliptic-curve point addition and then to full Shor once the verifiers are trusted.
9. **Design for the local-minimum problem.** If incremental improvement from a strong public baseline stalls, a benchmark suite could record each entry's lineage (which earlier entry it started from) and report from-scratch entries separately. Search methods that keep diverse populations would then be visible and rewarded, not only the single best score.
10. **Add measurement-free fault tolerance as a track.** It removes the decoder and the feed-forward latency from the stack, both named as bottlenecks above, and atoms and ions suffer most from slow measurement. A benchmark track with no mid-circuit measurement and a fixed qubit budget would be small enough to verify exactly today.

## Notes

_Participants: add your name, and attribute or correct points above._
