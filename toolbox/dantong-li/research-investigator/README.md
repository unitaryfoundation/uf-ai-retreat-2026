# Research Investigator v6.4

A reusable skill for organizing long-running mathematics and theoretical computer science research with a team of agents, independent reviews, and an explicit record of checked results.
Give a compatible agent the [skill instructions](SKILL.md), a research question or direction, and a time or resource limit; use the [illustrated guide](assets/guide.html) and [runtime notes](references/runtime.md) to set up the workflow.

- **Type:** skill, role prompts, and state-management helper
- **Works with:** agents that can read and write files and dispatch independent workers; the optional helper requires Python 3.9+ and uses only the standard library
- **Owner:** [Dantong Li](../../../attendees/dantong-li.md) ([dtlics](https://github.com/dtlics))

## Status

Dantong previously used this version and no longer uses it in his current workflow. The 36 original files from the v6.4 package are included unchanged; this README is the retreat introduction.

## What makes the workflow rigorous

- Authors and reviewers have separate roles. Acceptance requires independent individual and cross-draft reviews, with unresolved major objections blocking acceptance.
- Candidate files are frozen and identified by hashes, so a review applies to a particular version.
- Reusable premises enter a checked ledger; withdrawing a premise also quarantines its dependents.
- Results carry evidence labels that distinguish conjectures, numerical evidence, agent checks, machine checks, and expert verification.
- A skeptic reviews the model, proposed questions, and headline claims; literature and comparison roles check the surrounding context.

These are process safeguards. Agent reviews can still miss mathematical errors. An “agent-checked” result is not a formal proof, and the bookkeeping helper does not judge mathematical correctness. Machine checking or expert review remains a separate step.

## How to use it

1. Keep this folder intact so the skill can find its role prompts and reference files.
2. Read [SKILL.md](SKILL.md) and the [runtime notes](references/runtime.md) to establish the host's capabilities, especially whether reviews can run in fresh contexts.
3. Give the agent a precise conjecture or a broader research direction, its definitions and references, and an explicit time or resource limit. The package supports both focused and research-program modes; its continuation rules deserve particular attention before starting a run.
4. For the helper's available commands, run `python3 scripts/ri.py --help`. The helper maintains run state and review records; it does not launch or supply the agent runtime.

The package also includes a [worked example](references/worked-example.md), [design notes](references/design-notes.md), [changelog](CHANGELOG.md), and tests in `tests/`.

## Test status at contribution

On macOS with Python 3.9.6, the existing suite passed 270 of 271 tests with a short, canonical temporary directory (`TMPDIR=/private/tmp python3 -B -m unittest discover -s tests -v`, run from this folder). `test_p2_intake_budget_rejects_only_absurd_lengths` still encountered the filesystem's path-length limit with an exceptionally long archive path. The first run with the default temporary directory passed 269 of 271 tests; its additional failure compared equivalent paths differently because of a macOS symlink and passed with the canonical directory. No source files were changed. The tests exercise the helper's behavior, not the correctness of mathematical research produced by agents.
