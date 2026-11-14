---
title: "Add frame width to the objective for good codes in the UF QEC challenge"
proposer: "Jong Yeon Lee"
kind: "leaderboard"
status: idea
verifier: "The QEC challenge scores frame width alongside distance and check weight, and top-ranked codes have low-weight logical bases"
group: ""
---

# Add frame width to the objective for good codes in the UF QEC challenge

Idea from [Jong Yeon Lee](../../attendees/jong-yeon-lee.md), raised at [Mathys Rennela's workflow station](../../sessions/sat-workflow-stations/mathys-rennela.md) on Saturday morning. Will Zeng relayed it and Claude wrote it up.

## What it is

Add the code parameter from Jong Yeon's paper to the objective function that the UF QEC challenge uses to score codes. The challenge is part of UF's [agentic leaderboards](https://unitary.foundation/posts/2026_agentic_leaderboards/).

The paper is [*Designing Group-Valued Codes with Full Regular Low-Weight Bases*](https://arxiv.org/abs/2610.06820) (arXiv:2610.06820). Will relayed the parameter as "frame weight". *[Claude, from the abstract only: the paper calls it **frame width**. It is the smallest weight cutoff that still allows a complete canonical basis of logical operators, and the paper treats it as a code parameter alongside distance and check weight.]*

## Who would use it and what it changes

Agents and people submitting codes to the challenge. If the score only rewards rate, distance and check weight, codes can win while their logical operators are high-weight and hard to use fault-tolerantly. Scoring frame width would reward codes whose logical operators are also low-weight.

## What it needs

- A way to compute or bound frame width for submitted codes. The verifier has to be able to check it, not just accept it from the submitter.
- A decision on how to weight it against the existing terms in the objective.
- Jong Yeon's input on the definition and how to compute it.

## Notes and interest

_Add your name if you want in._
