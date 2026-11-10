# Working groups

Groups form at the Saturday pitch session and run a first experiment on Sunday morning. Each has a UF scribe.

```
groups/<group-slug>/
  README.md       problem, verifier, members, scribe (templates/group-readme.md)
  notes/          working notes, one file per sitting or per author
  artifacts/      the real thing: Lean statement, leaderboard spec, agent run logs, code
  commitment.md   one deliverable, one owner, one date, one ask of UF (templates/commitment.md)
```

Link the group's `README.md` to the chart entry it grew from, and set that entry's `status: group-formed` and `group: "<group-slug>"`.
