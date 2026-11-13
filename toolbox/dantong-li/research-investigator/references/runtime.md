# Runtime: running the loop on any host

This file maps the orchestrator's behaviour onto the host's spawn, wait and file tools. Read it
at run start, on resume, and after a tool error. Invariants I1–I12 and the control loop are in
SKILL.md; files and `ri.py` commands are in state.md.

## 1. Capability card

Work out the card once, from the tool list you can see, before `ri.py init` (it needs isolation
and K); then fill the placeholder card that init puts at the end of contract.md. Recheck it only
after a tool error or a host change (another machine, or a tool list that differs from the card).

```
## Capability card (checked <date>)
isolation:  L2 via <subagent | separate CLI process | fresh API call> [authorized <date>; flags <...>] | L1 only
dispatch:   blocking-parallel | background+notify | detached-process | sequential
K:          <max concurrent workers>
worker_io:  files <yes|no>; shell <yes|no>; web <yes|no|unknown>
solvers:    <exact arithmetic, LP/ILP, SAT/SMT, CAS available to workers, or none>
file_scope: <yes|no>: workers read run_dir and skill_dir and write in run_dir without prompts
python:     <python3 | python | py -3 | none>
skill_dir:  <absolute path>
run_dir:    <absolute path>
turn_model: text-only reply ends the turn: <yes | no | unknown (treat as yes) | delegated (single return)>
```

Filling notes:
- **isolation**: a separate CLI process or API call spends the user's quota. Ask once whether it
  may be used and which permission flags are acceptable (I11); record the answer. Never add
  approval-bypass flags without it.
- **dispatch**: background+notify whenever the spawn tool has any asynchronous or background
  option, whatever it is called; blocking-parallel only without one.
- **turn_model**: a delegated session that must return one report dispatches blocking-parallel,
  even when background is offered, and treats that return as a forced turn end (§3):
  checkpoint, "interrupted", the resume line.
- **K**: use a documented limit; with none, start with 3–6, and pass it to `ri.py init --k`. K
  changes only after a capacity error (lower it by one) or a host change. `ri.py` keeps the K
  given to init (its queue-low hint uses it): record a lowered K in the card and in
  checkpoint.md's Notes, and reduce a lane's N with `q set --slots` where needed. A card recheck
  never changes a lane's N.
- **worker_io**: "shell yes" means a worker can run code (scouts need it). With "shell no", pass
  `--no-code` to `ri.py init` (§7). Web is `unknown`
  unless the spawn tool documents worker tools; the first SURVEY result confirms it.
- **solvers**: if none, or if the bundle holds the user's code, ask once in the opening message
  (installs; running bundled code in a scout's task directory). Proceed either way; scouts fall
  back to exact enumeration with the standard library.
- **file_scope**: hosts often confine workers to a workspace or ask before outside access. Prefer
  a short RUN inside the host workspace; otherwise ask once to allow RUN and skill_dir. A worker
  refused access returns `blocked`.
- **python**: try `python3`, `python`, `py -3` with `--version`; an error or an installer
  message is a failure. Record the first that prints 3.9 or later. Test it with the same shell
  tool the run will use: a sandbox may run commands as another user and hide a per-user Python.
  If it fails there, also try the absolute path of an interpreter you can see on disk.

## 2. Isolation ladder

| Level | What it is | Gate reviews at this level give |
|---|---|---|
| L2 | A fresh context given only the packet: a subagent; a separate non-interactive process of the host's CLI; or a fresh API call with the user's existing configuration. The last two need the authorization in §1. | I2 holds → "agent-checked" |
| L1 | A labelled role pass inside your own context. | "self-checked (provisional)"; its ledger entries are provisional and labelled so |

Rules:
- Pass the card's level to `ri.py init --isolation`; `task new --start` records it per task
  (`--isolation` overrides). `ri.py accept` derives the label from it. Never record L1 work as L2.
- Messaging or resuming an existing context never makes it fresh. Never give a review to the
  author's context, or to one that has seen another verdict on the same item.
- An L1 pass: announce "Acting as <role> for Txxx"; read only the packet and the paths it names;
  write outputs and result.md in the task directory; return to the orchestrator role. Base later
  decisions on result.md fields and `ri.py` output, never on what the pass saw.

## 3. Dispatch and turn-keeping (I10)

**Dispatch message.** The whole spawn prompt is: "Read `<run>/tasks/Txxx/packet.md` and follow
it. Write only in `<run>/tasks/Txxx/` and in the canonical files your packet says your role owns.
When done, reply with only the result.md header." If the worker cannot read files, paste
packet.md verbatim. A reply that carries file contents (envelope rule 8) is saved as
`tasks/Txxx/stdout.md`; then save each file it holds under the name that heads it, `result.md`
last, and ingest as usual. Workers never spawn workers (envelope rule 9); all dispatch goes
through you, so K and the records stay true.

**Dispatch order, per wave.** (1) `ri.py task new ... --start` for every task of the wave: it
writes the packet and marks the task running, with context = task ID. (2) Rewrite checkpoint.md
(I7). (3) Spawn the wave. (4) Only if the host returns an ID: `ri.py task set RUN Txxx --context
<id>`. No task can run while recorded as queued.

| Style | Use it when | How to dispatch and wait |
|---|---|---|
| blocking-parallel | Several spawn calls fit in one step and return when the workers finish | Put the wave's spawns in one step; its return is the wait. Each wave is a barrier: group tasks of similar length (reviews with reviews, provers with provers). A task that unblocks the next step (MODEL in program mode, MODEL-GATE, SELECT, RENEW, a QUESTION-GATE) never shares a wave with a long task (scout, SURVEY, LANDSCAPE, TRANSFER-AUDIT); long tasks run with provers or with each other (program.md §6.1 orders a fast start). Request priorities decide what to drop under a limit, never the wave order. |
| background+notify (preferred when offered) | Spawns return at once; the host re-invokes you, or offers a wait call, when a worker finishes | Use the wait call. End the turn only if the host will re-invoke you; the last line names the task IDs you wait for. |
| detached-process | No spawn tool, but a non-interactive CLI is authorized (§1) | Below. |
| sequential | One worker at a time | Run the wave's tasks one after another. |

**Detached process + file wait.**
- Launch each worker detached, with working directory `RUN/tasks/Txxx` (so it loads none of the
  user's project instruction files), stdin closed, stdout to `tasks/Txxx/stdout.md` and stderr
  to `tasks/Txxx/stderr.txt`. Record `--context pid:<n>`.
- Wait in slices shorter than the host's command timeout: one call returns when any awaited
  `result.md` exists or after a few minutes. This is waiting, not status polling.
- Give each task a wall-clock limit: its packet's Time line plus about 15 minutes. Past it, kill
  the process tree by PID and treat the task as unknown (§6). On STOP, kill by PID.
- A worker that could not write files leaves its text in stdout.md; file it (envelope rule 8).

Where a text-only reply ends the turn, a progress message *is* the end of the run. Therefore:

| Do | Don't |
|---|---|
| Put progress in progress.md, or in one line next to a tool call. | Send "Round 3 closed, continuing…" as a message on its own. |
| Answer a status question after reconciling, in 3–6 lines, in the same step as the next dispatch. | Stop the loop to answer, or ask "shall I continue?" (I11). |
| Rewrite checkpoint.md before every wait (I7). | Promise background progress the card does not support, or poll with identical status calls. |
| On a forced turn end, rewrite checkpoint.md and progress.md, then send 3–6 lines ending "Resume: continue the research run at <run_dir>". | Call an interrupted run "complete" (I9). |

**Running workers.** If the host can message a running agent, send it nothing after the spawn
message except a cancel, or, if it asks a question, "Follow your packet; no further input will
come." Append each such message to `tasks/Txxx/dispatch.md`. Decide whether a gate counts only
after it returns (verification.md §2).

A timeout or lost connection is an unknown outcome, not a failure; reconcile it (§6) before
dispatching again. After a capacity error, lower K, `ri.py task set RUN Txxx --status queued`,
and retry later; never repeat a failing dispatch unchanged.

## 4. Loop mechanics

The orchestrator is a stateless function of the run directory (I7). Every start (new turn,
compaction, restart) enters the control loop (SKILL.md §6) at step 1; a resume goes through §6
first. Inside a live turn, read `ri.py status RUN --brief` and the output of `ri.py ingest`; read
checkpoint.md in full only at turn start, on resume and after compaction. Near the host's
context limit, rewrite checkpoint.md and progress.md and continue from them, as after a
compaction.

## 5. Stop, pause and hard interrupt

STOP and PAUSE are sentinel files in RUN, matched in any letter case and with any extension:
`STOP`, `stop`, `STOP.txt`, `Stop.md`, `PAUSE.txt` all count. `ri.py status` reports them, and
`ri.py task new` refuses while one exists.

| Signal | How it arrives | What to do |
|---|---|---|
| STOP | The user says stop, or a STOP file exists | If no file exists, run `ri.py stop RUN --reason-file <file>` (the user's words, written with the file tool). Dispatch nothing. Interrupt running workers where the host allows. Ingest every task that has result.md; mark other running tasks `cancelled`, or `unknown` if a worker may still be alive. Rewrite checkpoint.md and progress.md. Reply in 3–6 lines: "This run was stopped at <time> (<reason>). Nothing was dispatched. To restart it, say: resume the stopped run at RUN." No wrap-up report, manuscript or review unless the user asks. |
| PAUSE | The user says pause or hold, or a PAUSE file exists | If no file exists, run `ri.py pause RUN --reason-file <file>`. Dispatch nothing. Let running workers finish; ingest their results on resume. Rewrite checkpoint.md and progress.md, give a 3–6 line status, end. |
| Hard interrupt | The host kills the turn (e.g. the user presses an interrupt key) | Treat it as PAUSE. On the next user message: "continue", "resume", or a research instruction for this run → resume (§6). Anything else → do it, and run `ri.py pause RUN --reason "hard interrupt"` so no later session or driver resumes on its own. |

**A STOP is sticky.** It stays in force until the user explicitly lifts it: "resume the stopped
run", "restart", "undo the stop", or an instruction to remove STOP. The phrase "continue the
research run at RUN" alone does not lift a STOP; it lifts a PAUSE. Lift a PAUSE with
`ri.py resume RUN`, and a STOP with `ri.py resume RUN --stop --reason-file <file>` (the user's
words, written to the file with the file tool).
Reporting that a STOP is in force, and how to lift it, is not asking permission to continue (I11).

## 6. Resume

This is the only resume procedure. Use it on "continue" or "resume", in a new session pointed at
a run directory, and after a compaction or restart.

1. **Control files.** Run `ri.py status RUN --brief`. STOP present: if the current message
   explicitly lifts it (§5), run `ri.py resume RUN --stop --reason-file <file>`; otherwise do
   the STOP handling of §5 and end. PAUSE present and the user said continue or resume:
   `ri.py resume RUN`.
2. **Read** contract.md (with the capability card) and checkpoint.md. Recheck the card if the
   host changed. Open references only as the next action needs them.
3. **Audit.** `ri.py check RUN`. Note findings in checkpoint.md and settle them before any accept.
4. **Reconcile every task that is running, unknown, cancelled, or queued with outputs besides
   packet.md, before any dispatch.** `ri.py status` lists each under its reconcile hints (a
   cancelled one once no STOP or PAUSE is in force); `status --full` lists every task.
   - result.md exists → `ri.py ingest RUN Txxx`;
   - no result.md, and the host shows the worker still alive → keep waiting;
   - otherwise → `ri.py task new RUN --redo Txxx --start` (copies the work, marks Txxx
     superseded). Partial outputs are not results; name their paths with `--extra-file` as prior
     material. A late result.md of a superseded task is extra evidence: file it. `ri.py ingest
     RUN Txxx` on it records nothing; it only marks the result seen, so status stops listing it.
5. **Status question.** If the user asked for status, answer now in 3–6 lines from the refreshed
   `ri.py status`, alongside the next dispatch. Never answer from a checkpoint that still lists
   returned tasks as running.
6. **Continue** at the control loop's step 1. Never restart intake, re-run a finished task, or
   re-open a closed round.

## 7. Degraded modes

| Missing capability | Do instead | Label or record |
|---|---|---|
| Subagents and authorized processes (no L2 route) | L1 role passes, one at a time | Results "self-checked (provisional)"; ledger entries provisional |
| Parallelism (K = 1) | The same tasks, in waves of one (§8) | Labels unchanged |
| Python | Manual files (state.md §7) | Run labelled "unaudited records" |
| Web access | Literature work uses the bundle only | progress.md says "frontier from the supplied bundle only"; novelty claims say "not found in the supplied bundle" |
| Code execution | Pass `--no-code` to `ri.py init`; no scout tasks, not even the opening ANCHOR; counterexamples are gated without a WITNESS check (verification.md) | Assurance profiles say "small-case check: not checkable" |
| Worker file access | Paste packet.md; the worker returns text; save it as in §3 | Nothing |

## 8. Waves and cost

A lane round with N provers costs about **3N + 1** calls (N summarizers, N provers, N INDIVIDUAL
reviews, 1 CROSS-DRAFT review), plus 1 ledger auditor, 1–2 ISOLATED reviews per fragment, 0 to N
scout SANITY tasks and a share of one advisor call: about 17 calls at N = 4, and 100–150 for a
lane run to the default 8 rounds. One lane ≈ the paper's per-problem budget (O(100), up to
O(1000) for the hardest); a program multiplies this by the number of lanes. The opening costs
about 12–30 calls.

When ready tasks exceed K, run them in waves:
- **Outer share.** While outer work is pending, give it at least max(1, ⌊K/3⌋) slots per wave,
  plus any slot no gate or lane stage can use; with K = 1, alternate outer and lane tasks. An
  event or outer task pending for a full wave gets a reserved slot in the next wave. Only the
  latest MODEL, SELECT or RENEW's `tasks_requested` is live: an earlier unstarted request
  expires unless re-listed, so a reserved slot never serves a parked or unselected card.
- **Pipelining.** Under background+notify or detached-process, lanes pipeline with no global
  barrier: an INDIVIDUAL review starts as soon as its draft is frozen, and other lanes use the
  free slots. Under blocking-parallel each wave is a barrier (§3).

Consolidation costs about 4 calls (CLAIM-GATE, comparator, writer, PAPER). Under a finite user
limit (calls, time, money), when the remaining allowance is at most the consolidation cost plus
the gates of work in flight, stop new research (no sweeps, no new lanes) and consolidate first.
Never start a prover whose draft cannot also be reviewed within the limit. In program mode too,
skip the lane-round process advisor when no lane will run another round (proof-lane.md §2.5,
step 4); a run-wide one that `ri.py status` flags still runs.
Never invent token or cost figures the host does not report.

## 9. Optional deterministic driver

A driver is a script that runs the loop's mechanics as code, so "until the user stops" no longer
depends on how the host ends turns. Offer it in one line when the card shows `turn_model: yes`, no
background+notify, and an L2 route through a CLI process or API that the user could authorize. Set
it up only on the user's explicit opt-in, as `RUN/driver.<ext>`, after the normal orchestrator has
run the opening up to the first ready question. Code does scheduling, files and gate checks
(through `ri.py`); LLM tasks make every judgement. One scheduler loop launches work as slots free
up, so no lane waits for another. Task titles are unique keys, so a restart finds existing tasks
instead of repeating steps.

```
# Host-specific: start(T) runs a fresh L2 worker on tasks/T/packet.md (as in §3, detached process)
# and returns a handle; kill(h) ends its process tree. ri(...) runs ri.py under one mutex.
# TIMEOUT[role]: the packet's Time line (state.md §5) plus about 15 minutes.
# control() matches STOP/PAUSE files as ri.py does. Titles: "Q07 r3 brief P2 PROVE Q07.R1".

def main():
    take_lock(f"{RUN}/driver.lock")                         # PID + time; see below
    live = {}                                               # task ID -> (handle, deadline)
    for T in tasks_with_status("running"):                  # restart: reconcile first (§6)
        if has_result(T): ri("ingest", T, "--accept")
        elif pid_alive(T): live[T] = (adopt(T), now() + TIMEOUT[role(T)])
        else: ri("task set", T, "--status", "unknown")      # the main loop redoes it
    while True:
        for T, (h, deadline) in list(live.items()):         # reap
            if h.running() and now() < deadline: continue
            if h.running(): kill(h)                         # per-role timeout
            del live[T]
            if not has_result(T): ri("task set", T, "--status", "unknown"); continue
            ri("ingest", T, "--accept")
            settle(T)   # exclude after an accepted counterexample or D proof; register SELECT/RENEW
                        # cards once each; event --handled; stall or too-easy event from a worker
                        # field or status hint, unless already logged for that lane round
        if control() == "STOP":
            for T, (h, _) in live.items(): kill(h); ri("task set", T, "--status", "cancelled")
            break
        if control() == "PAUSE" or limits_reached():        # launch nothing; let workers finish
            if not live: break
        else:
            for spec in next_work(free=K - len(live)):
                T = task_by_title(spec.title)               # newest in its redo chain
                if T and status(T) not in ("unknown", "cancelled"): continue   # idempotent
                R = ri("task new", "--redo", T, "--start") if T else \
                    ri("task new", *spec.args, "--title", spec.title, "--start")
                live[R] = (start(R), now() + TIMEOUT[spec.role])
            if not live and exhausted(): break              # sweep -> BREADTH -> exhausted
        sleep(5)                                            # short slices: STOP is seen within seconds
    ri("status")                                            # final checkpoint block
    release_lock(f"{RUN}/driver.lock")

def next_work(free):                                        # SKILL.md §6 step 3 order
    work = gate_work()          # INDIVIDUAL/SALVAGE, SANITY/WITNESS, CROSS-DRAFT on a complete
                                # cohort, ADJUDICATE per listed rebuttal
    work += round_close_work()  # auditor, ISOLATED per fragment, ONE advisor per batch of closed
                                # rounds, TARGETED for a stall hold, light gates of successors
    ev = renew_ready_events()   # RENEW types and waits in program.md §7
    if ev and not investigator_live("MODEL", "SELECT", "RENEW"):
        work.append(renew_spec(ev))                         # title keyed by the batch: "renew E12-E15"
    for Q in active_lanes():
        if held(Q): continue                                # stall, lane-budget, literature-hit, new-source
        if lane_ended(Q): close_lane(Q); continue           # q set resolved | refuted when nothing is in flight
        work += lane_stage_work(Q)  # round --open and plan.md by the allocation rules (a filled
                                    # plan.md is reused); briefs; provers with --brief; round r+1
                                    # briefs only after round r's side loops returned
    work += outer_work(share=max(1, K // 3))  # a minimum; too-easy -> skeptic gates; queue-low -> sweep;
                                              # breadth-review -> BREADTH
    return work[:free]
```

`limits_reached()` reads the user limits in contract.md and keeps the §8 reserve. `exhausted()`
follows program.md: a proposal sweep; if nothing becomes ready, a BREADTH review; if BREADTH
reports exhaustion, write progress.md and exit. While `driver.lock` exists and its process lives,
the chat orchestrator only reads and reports.

## 10. Host hygiene

- **Windows paths.** Keep run_dir short, under about 120 characters, such as `C:\ri\<name>` or a
  short folder in the host workspace; `ri.py init` warns above that, and a run cannot move later.
  `ri.py` handles long paths internally on Windows; keep RUN short anyway because other tools may
  not. Write Assignment and note files inside RUN, never in a deep scratch directory. Quote paths
  with spaces. Avoid cloud-synced folders, which hold file locks.
- **Refused file names.** Some hosts refuse subagent files named report.md, analysis.md,
  summary.md or findings.md; no role writes those names; returned text is saved as
  `tasks/Txxx/stdout.md` (envelope rule 8; §3).
- **User configuration.** Never change the user's model, endpoint, reasoning settings or tool
  configuration. Never install software, start paid compute, or configure external services
  without authorization (I11).
