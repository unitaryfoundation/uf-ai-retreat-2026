---
title: "The landscape of repositories for formalized mathematics"
session: "sat-morning-discussion"
people: "Patrick Shafto, William Zeng"
scribe: "William Zeng (via Claude, from a speech-to-text transcript)"
---

# The landscape of repositories for formalized mathematics

Saturday morning, before the framing session. [Patrick Shafto](../../attendees/patrick-shafto.md) described the current state of repositories where new formal math results could go, with an eye to results from quantum information theory.

**How this note was made:** Claude summarised it from a speech-to-text transcript that Will Zeng relayed. Project names were garbled in the transcript and have been corrected to their real names ("MATLib" to Mathlib, "Tau SETI" to Tau Ceti, "FizLib" to Physlib). Links and bracketed notes marked *[Claude]* were added afterwards from a web search, not said in the room. One short interjection came from an unidentified attendee.

## What was discussed

### Where formal results can go today

- **[Mathlib](https://github.com/leanprover-community/mathlib4).** The human-curated effort to formalize mathematics, running since about 2017.
- **[Tau Ceti](https://lean-lang.org/use-cases/tau-ceti).** Announced over the summer as an AI version of Mathlib. Its focus is quality review, to keep machine-written code at a reasonable standard. Many other efforts are one-offs whose code is not maintainable or good enough to build on.
- **[Lean Pool](https://arxiv.org/abs/2609.25199).** Downstream of Tau Ceti: any Lean code for mathematics, whether or not it is polished. Someone in the room added that it does not have to pass Comparator either. *[Claude: the paper describes it as an AI-maintained archive, complementary to Tau Ceti.]*
- **[Palomar](https://terrytao.wordpress.com/2026/08/18/palomar-a-registry-of-lean-verified-mathematics/).** Came out slightly after Tau Ceti. It registers existing formalized mathematics and checks that it passes Comparator. That is a very low bar, but not zero. *[Claude: entries get a mechanical Comparator check, then an LLM check. It is incubated by the Lean FRO and ICARM.]*
- **[Hexagon](https://terrytao.wordpress.com/2026/10/06/hexagon/).** Patrick described it as a new effort out of Johns Hopkins: an archive for math AI papers that also accepts papers by humans, with minimal review, if any. *[Claude: the announcement describes an arXiv-style archive that allows LLM-generated papers and gives them citable identifiers. Submissions are screened, but there is no peer review. I could not confirm the Johns Hopkins link.]*

All of this except Mathlib has appeared since the summer.

### Domain libraries

Besides Mathlib, people are building or discussing:

- **EconLib**, announced recently. *[Claude: probably Axiom's EconLib, [reported by Fortune](https://fortune.com/2026/06/01/axiom-math-econlib-antitrust-economic-theory-verified/) in June 2026.]*
- **[Physlib](https://physlib.io/)**, which has existed for a while.
- **QuantumLib**: there have been rumblings, but Patrick did not know its status, or whether it is part of Physlib. *[Claude: the Lean-QuantumInfo library merged into Physlib in March 2026 and is now its separate `QuantumInfo` build target. See the [comparison of homes for formal QI results](../../charts/structures/home-for-formal-quantum-information-results.md).]*
- **TCSLib**, **Stats and MLLib**, and a separate **StatsLib**. *[Claude: a quick search found no public pages for these.]*

### The abstraction problem

How to organise these libraries is a very hard question. Mathlib has dealt with it by making a choice. The question is how to build a maintainable library of reusable abstractions. Mathlib's answer is to state everything at the maximal level of abstraction and derive anything more specific from that. This has a long history in mathematics.

That works for some of mathematics. But even within math, people doing analysis do not want to work at the maximal level of abstraction; they want definitions suited to analysis. In stats, quantum and other fields, you want the *right* level of abstraction, and what that means is a tricky question.

## Problems, tools or structures that came up

- [Where should formally proven quantum information results live?](../../charts/structures/home-for-formal-quantum-information-results.md) A comparison Will asked for after this discussion.

## Open questions

- What level of abstraction is right for a quantum information library? For example, should states be matrices or operators on an abstract finite-dimensional Hilbert space?
- Is there a QuantumLib effort separate from Physlib's QuantumInfo, and who is behind it?
- How much review does Hexagon actually do?
