# UF Fall Retreat 2026: AI in Quantum Information Processing

November 13–15, 2026 · Hilltown Commons, Rensselaerville, NY · hosted by [Unitary Foundation](https://unitary.foundation)

This repository is the system of record for the retreat. During the weekend, attendees and their agents read from it and write to it. Afterwards it becomes public and serves as the archive of what we shared, proposed and committed to.

The retreat has three objectives:

1. Swap notes on how best to use AI tools to accelerate research.
2. Coordinate to be more ambitious in the problems we solve together.
3. Discuss structures for doing better research in the new paradigm: agentic leaderboards, Lean repos, zoos, review and credit norms.

## Where things are

| Path | What it holds |
|---|---|
| [`program/`](program/) | Schedule, objectives and ground rules, logistics |
| [`attendees/`](attendees/INDEX.md) | One page per person, generated from the pre-read |
| [`toolbox/`](toolbox/) | The pre-work drops: one reusable thing per person (skill, prompt, harness config, `AGENTS.md`, verifier script) |
| [`charts/problems/`](charts/problems/INDEX.md) | Live chart: problems worth 10x |
| [`charts/tools/`](charts/tools/INDEX.md) | Live chart: tools and tricks |
| [`charts/structures/`](charts/structures/INDEX.md) | Live chart: structures we'd want |
| [`sessions/`](sessions/) | Notes from each session, in schedule order |
| [`groups/`](groups/) | Working groups formed on Saturday: notes, artifacts, commitments |
| [`inbox/`](inbox/) | Unsorted dumps (photos, raw notes, transcripts) waiting to be filed |
| [`templates/`](templates/) | A template for each kind of entry |
| [`scripts/`](scripts/) | Index builder and validator |

## Before you arrive

1. Open your page in [`attendees/`](attendees/INDEX.md) and fill in anything missing, including your GitHub handle.
2. Drop one reusable thing into `toolbox/<your-name>/<thing>/` with a two-line `README.md`. See [`toolbox/README.md`](toolbox/README.md).

## Adding something during the weekend

Every entry is its own small file, so many people and agents can write at the same time without conflicts.

1. Copy the matching file from [`templates/`](templates/) into the right folder.
2. Name it in `lowercase-kebab-case.md` and fill in the front matter at the top.
3. Commit, `git pull --rebase`, push.

Not sure where something goes? Put it in [`inbox/`](inbox/) and it will get filed.

Files named `INDEX.md` are generated from the entries. Do not edit them; they are rebuilt automatically on every push.

## Working with an agent

Point your agent at this repo and it will pick up [`AGENTS.md`](AGENTS.md), which has the full rules: where each kind of entry goes, the front-matter fields, and the commit routine. Good things to ask it:

- "Who here works on QEC, and what problems did they propose?"
- "Add a tools-and-tricks entry for the referee prompt I just described."
- "Summarise what our working group decided and write it to our group folder."

## How an idea moves through the weekend

A problem or structure starts as an entry in `charts/` with `status: idea`. If it is pitched on Saturday, its status becomes `pitched`. If a group forms around it, the status becomes `group-formed` and the entry links to a folder in `groups/`. On Sunday that group records one deliverable, one owner, one date and one ask of UF in its `commitment.md`.

## Privacy

This repo will be public. Do not commit email addresses, phone numbers, wifi or door codes, API keys, or anything a collaborator shared in confidence. Failure autopsies are attributed by default; set `anonymous: true` in the entry if you would prefer not to be named. `scripts/validate.py` flags contact details it finds.
