---
title: "Where should formally proven quantum information results live?"
proposer: "William Zeng"
kind: "lean-repo"
status: idea
verifier: "A new QI result is merged or registered, passes Comparator, and its definitions are reused by a second result from a different group"
group: ""
---

# Where should formally proven quantum information results live?

Will Zeng asked for this comparison after [Patrick Shafto's overview of formal math repositories](../../sessions/sat-morning-discussion/formal-math-repositories-landscape.md). **Claude compiled it from web searches on 2026-11-14.** It has not been checked against each project's current contribution rules, so confirm before relying on it, and add corrections under Notes.

## What it is

A choice of where retreat groups (and UF more broadly) put Lean formalizations of quantum information results, so that they stay maintained and others can reuse and cite them, instead of piling up as one-off repos.

## The options

| Home | What it is | Review bar | QI content today | Good for | Watch out for |
|---|---|---|---|---|---|
| [Mathlib](https://github.com/leanprover-community/mathlib4) | Human-curated general math library, since about 2017 | Highest. Human review; AI-written code is largely not accepted as is | Prerequisites: matrices, positive semidefinite operators, trace, inner product spaces | General linear algebra and analysis lemmas that QI depends on | Slow. Everything is stated at the maximal level of abstraction, which is not a natural fit for QI-specific objects |
| [Physlib](https://physlib.io/), `QuantumInfo` target ([repo](https://github.com/leanprover-community/physlib)) | Community physics library. The former Lean-QuantumInfo merged into it in March 2026 and is a separate build target | Human review, with conventions separate from the rest of Physlib for now | The main existing Lean QI library: states, channels, entropies | QI definitions and theorems meant to be shared and reused | Conventions are still converging with the rest of Physlib. Check its AI-contribution policy |
| [Tau Ceti](https://lean-lang.org/use-cases/tau-ceti) ([GitHub](https://github.com/TauCetiProject)) | AI-written library downstream of Mathlib. Humans write roadmaps; AI writes and reviews the code against rubrics; the Lean kernel checks it | Adversarial AI review against human rubrics | Unknown | Large-scale agent-written work steered by a roadmap we write | A roadmap must connect to material already in Mathlib or Tau Ceti. Unclear whether QI fits its scope |
| [Lean Pool](https://arxiv.org/abs/2609.25199) | AI-maintained archive of formalized mathematics, complementary to Tau Ceti | Low; described in the room as "any Lean code", possibly not even Comparator-checked | Unknown | Getting anything agent-generated archived quickly | Little quality guarantee, so it is a weak base to build on |
| [Palomar](https://terrytao.wordpress.com/2026/08/18/palomar-a-registry-of-lean-verified-mathematics/) | Registry (not a library) of commit snapshots of external Lean repos | Mechanical Comparator check, then an LLM check | Whatever gets registered | Citable, checked registration of a finished result that lives in our own repo | Does not host or maintain code; reuse still depends on where that code lives |
| [Hexagon](https://terrytao.wordpress.com/2026/10/06/hexagon/) ([site](https://hexagonmath.org/)) | arXiv-style archive for math papers, including LLM-generated ones | Screening only, no peer review | Papers only | The human-readable paper, with a citable ID and links to the formal proof | Not a code repository |
| [Lean-QIT](https://arxiv.org/abs/2607.09632) | Independent Lean 4 library for finite-dimensional QIT. More than 150k lines as of July 2026, AI-assisted | Project-internal | Broad finite-dimensional QIT | A possible source of definitions, or a place to contribute | A parallel effort to Physlib QuantumInfo; fragmentation risk. Repo URL not verified |
| [Lean-Quantum](https://github.com/Hayata-Yamasaki-Group/lean-quantum) ([paper](https://arxiv.org/abs/2607.05492)) | Yamasaki group's AI-assisted formalization. Includes the data-processing inequality for sandwiched Rényi relative entropy and a missing piece of the generalized quantum Stein's lemma | Project-internal | Specific deep results | An example of a result-driven QI formalization repo | Single-group project; long-term upkeep unclear |
| A new UF-hosted repo | Our own repo for retreat results | Whatever we set | None yet | Speed and full control; a place for agent swarms to work | Creates yet another library. Maintenance falls on UF |

## A possible layered answer

This is Claude's suggestion, not a group decision:

1. **Reusable QI definitions and lemmas** go upstream to Physlib `QuantumInfo`, or to Tau Ceti through a QI roadmap if that turns out to be in scope. General linear algebra goes to Mathlib when it is clean enough.
2. **Each specific result** lives in a small repo that depends on that library and is pinned at a commit.
3. **Register** that commit with Palomar, so it gets a Comparator-checked, citable entry.
4. **Post the paper** to arXiv, or to Hexagon if it is AI-generated, with a link to the registered proof.

The open design question is the one Patrick raised: what level of abstraction is right for QI. Mathlib's "maximal abstraction" answer is probably wrong for working quantum information theorists. Before writing much code, a group should look at how Physlib QuantumInfo and Lean-QIT each represent states and channels.

## Who would use it and what it changes

Any retreat group whose verifier is a Lean proof, for example a formal statement of exponential error suppression for a self-correcting memory ([Will's 10x problem](../problems/william-zeng-10x.md)). Agreeing on a home up front means results build on each other instead of each group inventing its own definitions of a density matrix.

## What it needs

- Someone to check the current contribution and AI policies of Physlib QuantumInfo and Tau Ceti.
- A conversation with the Physlib QuantumInfo maintainers about whether they want agent-generated contributions.
- Possibly an ask of UF: maintainer time or compute for a QI roadmap.

## Notes and interest

_Add your name if you want in, plus corrections. People who know these projects first-hand, please fix anything wrong above._
