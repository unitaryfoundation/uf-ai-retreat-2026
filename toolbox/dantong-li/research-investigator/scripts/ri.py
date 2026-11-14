#!/usr/bin/env python3
"""ri.py - state-maintaining helper CLI for the research-investigator skill.

The orchestrator calls this script for all bookkeeping: IDs, task packets with
default Assignments, frozen candidates and their SHA-256 hashes, review records,
acceptance gates (invariants I3/I4), the ledger and exclusions, renewal events
and lane holds, the record of attempts, safe bundle intake, ingestion of worker
result headers, filing of source cards, and the status block in checkpoint.md. It never judges
mathematics.

Python 3.9+, standard library only, no network. state.json and generated
markdown are written atomically (temp file + os.replace); log.jsonl is
append-only. Every command that writes holds the lock file RUN/.ri.lock, so run
ri.py commands one at a time. Stored paths are relative to the run directory
RUN; printed absolute paths use os.path.abspath, never resolve(). On Windows,
file I/O on paths of 240 or more characters uses the extended-length form. The skill
directory is the parent of this script's directory, or $RI_SKILL_DIR if set.

Exit codes: 0 ok; 1 gate/audit failure or refused operation; 2 usage error.
Run `ri.py -h` for the command list and `ri.py <command> -h` for options.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import difflib
import hashlib
import json
import os
import re
import sys
import tarfile
import tempfile
import time
import urllib.parse
import zipfile
from pathlib import Path

SCHEMA = 6
ROLES = ("investigator", "literature-reviewer", "scout", "skeptic", "summarizer", "prover",
         "verifier", "ledger-auditor", "process-advisor", "comparator", "writer")
MODES = {
    "investigator": ("MODEL", "PROPOSE", "SELECT", "RENEW", "BREADTH", "EXPLAIN"),
    "literature-reviewer": ("SURVEY", "LANDSCAPE", "TRANSFER-AUDIT", "TARGETED"),
    "scout": ("EXPLORE", "SANITY", "WITNESS", "BUILD", "CERTIFY"),
    "skeptic": ("MODEL-GATE", "QUESTION-GATE", "CLAIM-GATE"),
    "prover": ("PROVE", "DISPROVE", "SPECIAL-CASE", "REPAIR"),
    "verifier": ("INDIVIDUAL", "CROSS-DRAFT", "SECOND-INDEPENDENT", "SALVAGE", "ISOLATED", "PAPER",
                 "ADJUDICATE"),
}
# SALVAGE is an individual-type review of a gap draft that never counts as a pass (D10).
MODE_SCOPE = {"INDIVIDUAL": "individual", "CROSS-DRAFT": "cross", "SECOND-INDEPENDENT": "cross",
              "SALVAGE": "individual", "ISOLATED": "isolated", "PAPER": "paper",
              "ADJUDICATE": "adjudicate", "SANITY": "sanity", "WITNESS": "witness"}
REVIEW_MODES = ("INDIVIDUAL", "CROSS-DRAFT", "SECOND-INDEPENDENT", "SALVAGE")
Q_STATUSES = ("draft", "vetting", "ready", "active", "resolved", "refuted", "parked", "killed")
TIERS = ("SAFE", "CORE", "AMBITIOUS", "EXPLORE")
PLAUSIBILITY = ("supported", "mixed", "doubtful")
TASK_STATUSES = ("queued", "running", "done", "partial", "blocked", "unknown", "cancelled", "superseded",
                 "withdrawn")  # withdrawn: never spawned (task set --note); neither LIVE nor FINISHED
LIVE = ("queued", "running")
FINISHED = ("done", "partial", "blocked")
GONE = ("cancelled", "superseded", "withdrawn")  # tasks that never count as having run
KINDS = ("proof", "construction", "impossibility", "counterexample", "lemma", "manuscript",
         "imported", "transfer")
RUNG_KINDS = ("proof", "construction", "impossibility")
SCOPES = ("individual", "cross", "isolated", "paper", "adjudicate", "sanity", "witness")
GATE_SCOPES = ("individual", "cross", "isolated", "paper", "sanity", "witness")
SCOPE_ROLES = {"individual": ("verifier",), "cross": ("verifier",), "paper": ("verifier",),
               "adjudicate": ("verifier",), "isolated": ("verifier", "literature-reviewer"),
               "sanity": ("scout",), "witness": ("scout",)}
VERDICTS = ("PASS", "PASS_WITH_MINOR", "FAIL", "INCONCLUSIVE")
PASSING = ("PASS", "PASS_WITH_MINOR")
FIDELITIES = ("MATCH", "WEAKER", "DIFFERENT_MODEL")
SEVERITIES = ("CRITICAL", "MAJOR", "MINOR", "COSMETIC")
EVENT_TYPES = ("rung-accepted", "top-accepted", "refuted", "stall", "lane-budget", "new-source",
               "literature-hit", "question-verdict", "too-easy", "model-change", "queue-low", "breadth-review",
               "milestone", "user-input")
HOLD_TYPES = ("stall", "lane-budget", "literature-hit", "new-source")
FOCUSED_END_TYPES = ("rung-accepted", "top-accepted", "refuted", "lane-budget",  # SKILL.md sec. 5 step 4, program.md sec. 3
                     "literature-hit", "new-source")
FOCUSED_HOLD = ("focused mode: hold Q01 (--lane) only if the source refutes the claim or the contract asks whether "
                "it is known (program.md sec. 3); else log it without --lane and tell the user")
FOCUSED_CONTEXT = ("context: its note goes to the lane's next summarizers and the closing CLAIM-GATE; no RENEW "
                   "(program.md sec. 3); the delivery task marks it handled")
RENEW_TYPES = ("top-accepted", "refuted", "stall", "lane-budget", "new-source", "literature-hit",
               "question-verdict", "model-change", "milestone")
EVENT_ACTIONS = {
    "rung-accepted": "lane continues on the next stronger rung (RENEW only if an assumption is open)",
    "top-accepted": "let in-flight drafts finish, close the lane (q set --status resolved), then RENEW",
    "refuted": "close the lane (q set --status refuted), then RENEW",
    "stall": "lane held; literature-reviewer TARGETED on the stuck step (+ scout if checkable), then RENEW",
    "lane-budget": "lane held until RENEW (continue, descend or park)",
    "new-source": "affected lane held (no new round) until RENEW",
    "literature-hit": "affected lane held (no new round) until RENEW",
    "question-verdict": "no hold; RENEW (before the first SELECT: the MODEL naming it, else SELECT) writes a new "
                        "version, a stepping-stone placement or successors",
    "too-easy": "skeptic MODEL-GATE + CLAIM-GATE (two tasks) first, then RENEW",
    "model-change": "quarantine entries whose model changed, then RENEW",
    "queue-low": ("proposal sweep with the 2 least-recently used lenses, one of them constructive (program.md "
                  "sec. 5.1), then SELECT"),
    "breadth-review": "investigator BREADTH in a fresh context",
    "milestone": "skeptic CLAIM-GATE beside the comparator -> writer -> verifier PAPER",
    "user-input": "route by kind (program.md): papers -> intake + SURVEY; scope -> contract; hints -> RENEW",
}
FOCUSED_REFUTED = ("focused: one limited RENEW applies READING first (program.md sec. 3); consolidate only if the "
                   "witness defeats the intended claim")
FOCUSED_VERDICT = ("no hold; one limited RENEW writes the next version (once the lane is active, a successor question; "
                   "SKILL.md sec. 5 focused step 2)")
AFTER_CHOICES = ("continue", "stop")  # focused mode: what follows the delivery (SKILL.md sec. 5 focused step 5)
# Phrases that limit a run to its claim (program.md sec. 3). "The only reference" or "show that X" are not among them.
_CLAIM = r"(?:claim|question|problem|statement|theorem|result|inequality|conjecture|bound|one|it)"
LIMIT_PHRASE_RE = re.compile(
    r"\b(?:only|just|solely)\b[^.;]{0,40}?\b(?:this|that|the|my|one)\s+(?:\w+\s+)?" + _CLAIM + r"\b"
    r"|\b(?:only|just|solely)\s+(?:prove|show|check|verify|answer|solve|settle|decide)\b"
    r"|\b(?:stop|end|finish|halt)\b[^.;]{0,30}\b(?:after|when|once|there)\b|\bthen\s+(?:stop|end|finish|halt)\b"
    r"|\bnothing\s+(?:else|more)\b|\bno\s+(?:further|more|other)\s+(?:work|research|exploration|questions?)\b"
    r"|\b(?:do\s+not|don'?t)\s+(?:continue|go\s+further|go\s+on|explore|keep\s+going)\b", re.I)
STOP_QUOTE_MAX = 200
NOT_A_STOP = ("--after stop needs --stop-quote (or --stop-quote-file): the user's own words that limit the run to this "
              "claim, verbatim (program.md sec. 3). 'Prove', 'show that', 'prove or disprove', a single reference or "
              "'no internet' do not limit the run: keep the default --after continue")
CONVERT_STEPS = ("say in progress.md sec. 1 that the result is delivered and the run continues as a research program "
                 "built on it; then mode RUN --to program --reason-file <file> (program.md sec. 3)")
CONVERT_HINT = "after delivery (PAPER passed, or the report delivered): " + CONVERT_STEPS
ID_WIDTH = {"Q": 2, "C": 3, "L": 3, "T": 3, "S": 2, "E": 0}
ST_BEGIN, ST_END = "<!-- ri:status -->", "<!-- /ri:status -->"
STATUS_LINES, BRIEF_LINES = 60, 15
PLACEHOLDER = ("<orchestrator: write the exact request, inputs by path, what to return, "
               "local stop condition>")
STOP_DEFAULT = {
    "investigator": "your mode's outputs and result.md are written",
    "literature-reviewer": "the requested cards or verdicts and result.md are written, or your search budget is spent",
    "scout": "the check or table covers the stated domain, or you are blocked (not checkable); result.md written",
    "skeptic": "one verdict per item; gate.md and result.md written",
    "summarizer": "briefing.md (at most about 1,200 words) and result.md written",
    "prover": "draft.md, notes.md and result.md written: a complete proof of the rung you claim, or the "
              "strongest result you proved and the obstacle",
    "verifier": "review.md and result.md written for every listed candidate",
    "ledger-auditor": "every confirmed step and step counterexample processed (fragment or skipped); result.md written",
    "process-advisor": "advisor-log.md and result.md written, and instructions.md if a rule changed",
    "comparator": "selection.md and result.md written",
    "writer": "manuscript.md, trace.md and result.md written",
}
RETURN_DEFAULT = "Return: the output files your role instructions prescribe for this mode, and result.md."
LIGHT_GATE = "Light gate: run checks 1-3b only."
LIGHT_MODEL_GATE = "Light gate: run QUESTION-GATE checks 1-3b only on {}; the MODEL-GATE runs in full."
# Time line minutes (state.md sec. 5): roles not listed, and other modes of the LONG_MODES roles, get 45.
ROLE_MINUTES = {"scout": 20, "skeptic": 25, "summarizer": 20, "literature-reviewer": 45, "prover": 90, "writer": 60}
LONG_MODES = {"investigator": ("MODEL", "SELECT"),
              "verifier": ("INDIVIDUAL", "SALVAGE", "CROSS-DRAFT", "SECOND-INDEPENDENT", "PAPER")}
SCOUT_TIME = ("Time: at most about 20 minutes of compute, each run under 5 minutes; save tables after each size "
              "(status partial).")
QUARANTINE_CODES = ("objection", "sanity", "failed-isolated", "model-change", "contradiction", "misquote")
I5_LABELS = ("conjecture", "numerical evidence", "candidate", "self-checked", "agent-checked", "machine-checked",
             "expert-verified")
# Files ri.py task new writes into a task directory (packet inputs), as opposed to worker outputs.
PACKET_FILE_RE = re.compile(r"(?:packet|status|dispatch)\.md|card-Q\d+\.md|object-C\d+\.md", re.I)
LANE_ENDED = ("resolved", "refuted", "killed", "parked")
IS_WINDOWS = os.name == "nt"
PATH_WARN = 120          # characters of abspath(RUN) above which init warns on Windows
LONG_PATH = 240          # Windows: absolute paths this long get the extended-length form for file I/O
LOCK_NAME, LOCK_WAIT, LOCK_STALE = ".ri.lock", 30.0, 600.0
CONTROL_RE = re.compile(r"(stop|pause)(\..*)?", re.I)


# ---------------------------------------------------------------- errors, IDs, IO

class RiError(Exception):
    """An error with an exit code: 1 = refused/gate failure, 2 = usage error."""

    def __init__(self, msg, code=1):
        super().__init__(msg)
        self.code = code


def fail(msg):
    raise RiError(msg, 1)


def usage(msg):
    raise RiError(msg, 2)


def fmt_id(prefix, n):
    width = ID_WIDTH[prefix]
    return f"{prefix}{n:0{width}d}" if width else f"{prefix}{n}"


def norm_id(prefix, text):
    """Normalise 'q7', 'Q007' -> 'Q07' (exit 2 on malformed IDs)."""
    m = re.fullmatch(prefix + r"(\d+)", str(text).strip(), re.I)
    if not m:
        usage(f"malformed {prefix} ID: {text!r}")
    return fmt_id(prefix, int(m.group(1)))


def norm_claim(text):
    """Normalise a claim reference such as 'q7.r2' -> 'Q07.R2' or 'Q07.D'."""
    m = re.fullmatch(r"(Q\d+)\.(R\d+|D)", str(text).strip(), re.I)
    if not m:
        usage(f"malformed claim {text!r}: use Qxx.Ri or Qxx.D")
    rung = m.group(2).upper()
    rung = "D" if rung == "D" else f"R{int(rung[1:])}"
    return f"{norm_id('Q', m.group(1))}.{rung}"


def norm_objection(text):
    m = re.fullmatch(r"(T\d+)\.O(\d+)", str(text).strip(), re.I)
    if not m:
        usage(f"malformed objection reference {text!r}: use Txxx.Ok")
    return f"{norm_id('T', m.group(1))}.O{int(m.group(2))}"


def norm_direction(text):
    """'prove q7.r1' -> 'PROVE Q07.R1'; also DISPROVE Qxx.D, SPECIAL-CASE <case>, REPAIR Cxxx."""
    m = re.fullmatch(r"\s*(PROVE|DISPROVE|SPECIAL-CASE|REPAIR)\s+(.+?)\s*", text or "", re.I | re.S)
    if not m:
        usage(f"malformed direction {text!r}: use PROVE Qxx.Ri | DISPROVE Qxx.D | "
              "SPECIAL-CASE <case> | REPAIR Cxxx")
    verb, arg = m.group(1).upper(), m.group(2)
    if verb in ("PROVE", "DISPROVE"):
        arg = norm_claim(arg)
    elif verb == "REPAIR":
        arg = norm_id("C", arg)
    return f"{verb} {arg}"


def next_id(st, prefix):
    st["counters"][prefix] = st["counters"].get(prefix, 0) + 1
    return fmt_id(prefix, st["counters"][prefix])


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path):
    h = hashlib.sha256()
    with open(xp(path), "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def atomic_write(path, data):
    """Write text/bytes via a temp file in the same directory and os.replace."""
    path = xp(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(6):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:  # Windows: target briefly open elsewhere
                if attempt == 5:
                    raise
                time.sleep(0.05 * (attempt + 1))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def apath(p):
    """Absolute path without resolving links or host redirections (B8)."""
    return Path(os.path.abspath(os.fspath(p)))


def xp(p):
    """Path p for file I/O (B8). On Windows an absolute path of LONG_PATH or more characters becomes the
    extended-length form ('\\\\?\\' + the absolute path, forward slashes converted), which passes the
    260-character MAX_PATH limit; otherwise p is unchanged. Printed and recorded paths keep the normal form."""
    p = Path(p)
    if not IS_WINDOWS:
        return p
    s = os.path.abspath(os.fspath(p)).replace("/", "\\")
    if len(s) < LONG_PATH or s.startswith("\\\\?\\"):
        return p
    return Path("\\\\?\\UNC\\" + s[2:] if s.startswith("\\\\") else "\\\\?\\" + s)


def is_file(p):
    return xp(p).is_file()


def exists(p):
    return xp(p).exists()


def skill_dir():
    env = os.environ.get("RI_SKILL_DIR")
    return apath(env) if env else apath(__file__).parent.parent


def rel(run, path):
    """Path relative to RUN (posix style) when inside RUN, else absolute."""
    p, r = apath(path), apath(run)
    try:
        return p.relative_to(r).as_posix()
    except ValueError:
        return str(p)


def find_input(run, text):
    """Resolve a user-given file: absolute, else relative to RUN, else to the cwd."""
    p = Path(text)
    for cand in ([p] if p.is_absolute() else [Path(run) / p, Path.cwd() / p]):
        if is_file(cand):
            return cand
    usage(f"file not found: {text}")


def text_arg(a, name, run="."):
    """Value of --NAME, or the content of --NAME-file (B9: free text never passes through a shell)."""
    val, path = getattr(a, name, None), getattr(a, name + "_file", None)
    flag = "--" + name.replace("_", "-")
    if val is not None and path:
        usage(f"give {flag} or {flag}-file, not both")
    if path:
        return xp(find_input(run, path)).read_text(encoding="utf-8-sig").rstrip()
    return val


def load_state(run):
    sp = Path(run) / "state.json"
    if not is_file(sp):
        usage(f"{run} is not a run directory (no state.json); run 'ri.py init' first")
    try:
        st = json.loads(xp(sp).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        fail(f"state.json does not parse: {e}")
    if st.get("schema") != SCHEMA:
        fail(f"state.json schema is {st.get('schema')!r}, expected {SCHEMA}")
    return st


def open_run(a):
    run = Path(a.run)
    return run, load_state(run)


def commit(run, st, cmd, args):
    """Bump seq, write state.json atomically, append one line to log.jsonl."""
    st["seq"] += 1
    atomic_write(Path(run) / "state.json", json.dumps(st, indent=1, ensure_ascii=False) + "\n")
    entry = {"seq": st["seq"], "time": now(), "cmd": cmd,
             "args": {k: v for k, v in args.items() if v not in (None, "", [], False)}}
    with open(xp(Path(run) / "log.jsonl"), "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


@contextlib.contextmanager
def run_lock(run):
    """Exclusive lock RUN/.ri.lock (B7): O_CREAT|O_EXCL, backoff up to LOCK_WAIT s, stale after LOCK_STALE s."""
    lp = xp(Path(run) / LOCK_NAME)
    deadline, delay = time.monotonic() + LOCK_WAIT, 0.02
    while True:
        try:
            fd = os.open(str(lp), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except (FileExistsError, PermissionError):
            try:
                age = time.time() - lp.stat().st_mtime
                if age > LOCK_STALE:
                    lp.unlink()
                    print(f"note: removed a stale lock ({int(age)} s old)", file=sys.stderr)
                    continue
            except OSError:
                continue
            if time.monotonic() > deadline:
                try:
                    holder = lp.read_text(encoding="utf-8").strip()
                except OSError:
                    holder = "unknown holder"
                fail(f"the run is locked ({holder}); run ri.py commands one at a time")
            time.sleep(delay)
            delay = min(delay * 2, 0.5)
    with os.fdopen(fd, "w") as f:
        f.write(f"pid {os.getpid()} since {now()}\n")
    try:
        yield
    finally:
        try:
            lp.unlink()
        except OSError:
            pass


def control_flags(run):
    """{'STOP': [paths], 'PAUSE': [paths]}: sentinel files in RUN in any case, with any extension (A1)."""
    out = {"STOP": [], "PAUSE": []}
    try:
        names = sorted(os.listdir(xp(run)))
    except OSError:
        return out
    for name in names:
        p = Path(run) / name
        m = CONTROL_RE.fullmatch(name)
        if m and is_file(p):
            out[m.group(1).upper()].append(p)
    return out


def flag_desc(p):
    """'STOP.txt at <time> (<reason>)' from a sentinel written by ri.py or by hand."""
    try:
        lines = [x.strip() for x in xp(p).read_text(encoding="utf-8", errors="replace").splitlines()]
    except OSError:
        lines = []
    m = re.match(r"(?:STOP|PAUSE)\s+(\S+)$", lines[0]) if lines else None
    if m:
        when, rest = m.group(1), lines[1:]
    else:
        when = datetime.datetime.fromtimestamp(xp(p).stat().st_mtime, datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        rest = lines
    return f"{p.name} at {when} ({' '.join(x for x in rest if x) or 'no reason given'})"


def add_event(st, etype, lane, note):
    eid = next_id(st, "E")
    st["events"].append({"id": eid, "type": etype, "lane": lane, "note": note,
                         "seq": st["seq"] + 1, "handled_by": None,
                         "lane_rounds": st["counters"].get("lane_rounds", 0)})
    return eid


def log_event(st, etype, lane, note):
    """add_event plus a lane hold for stall, lane-budget, literature-hit and new-source (E4)."""
    eid = add_event(st, etype, lane, note)
    if lane and etype in HOLD_TYPES and lane in st["questions"]:
        st["questions"][lane].setdefault("held_by", []).append(eid)
    return eid


def cell(text, limit=90):
    s = " ".join(str(text if text is not None else "-").split()).replace("|", "\\|")
    return s if len(s) <= limit else s[:limit - 3] + "..."


def get(st, table, prefix, text):
    key = norm_id(prefix, text)
    if key not in st[table]:
        usage(f"unknown ID {key}")
    return key


def split_list(text):
    if not text:
        return []
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    sep = ";" if ";" in text else ","
    return [x.strip() for x in text.split(sep) if x.strip() and x.strip().lower() != "none"]


def read(path):
    try:
        return xp(path).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def first_line(path):
    for line in read(path).splitlines():
        s = line.strip().lstrip("#").strip()
        if s:
            return s[:200]
    return "-"


def section_paragraph(path, names=("Theorem", "Statement")):
    """First paragraph under the first '## <name>' heading found (D7); None if absent."""
    lines = read(path).splitlines()
    for name in names:
        for i, line in enumerate(lines):
            if re.match(r"#{2,3}\s+" + re.escape(name) + r"\b", line.strip(), re.I):
                para = []
                for x in lines[i + 1:]:
                    s = x.strip()
                    if s.startswith("#") or (not s and para):
                        break
                    if para and re.match(r"(Rung|Deviations from|Depends on)\b", s):
                        break
                    if s:
                        para.append(s)
                if para:
                    return " ".join(para)[:600]
    return None


def replace_block(text, begin, end, body):
    """Replace text between markers; insert the block after the first line if absent."""
    block = f"{begin}\n{body}\n{end}"
    if begin in text and end in text:
        head, rest = text.split(begin, 1)
        return head + block + rest.split(end, 1)[1]
    lines = text.split("\n", 1)
    return lines[0] + "\n\n" + block + "\n" + (lines[1] if len(lines) > 1 else "")


# ---------------------------------------------------------------- templates

def pointer():
    return f"Driven by research-investigator (skill_dir {skill_dir()}); to resume read SKILL.md §5."


def after_line(a):
    """contract.md's after-delivery line under Mode (focused mode only; SKILL.md sec. 5 focused step 1)."""
    if a.mode != "focused":
        return ""
    if a.after == "stop":
        return f'After delivery: stop - the user\'s words: "{text_arg(a, "stop_quote")}" (program.md sec. 3)\n'
    return ("After delivery: continue - the default: once the claim's result is delivered, the run goes on as a "
            "research program built on it until the user stops it (program.md sec. 3)\n")


CONTINUATION_SCOPE = ("research questions built on the delivered result: stronger and converse results (for the "
                      "whole class it competes in first), other regimes and parameters, and sibling questions in the "
                      "sources (program.md sec. 2.1)")


def contract_md(a, run, objective, keydiff):
    """The contract template; its last section is the runtime.md §1 capability card (C6)."""
    scope = (f"the claim; after its delivery, {CONTINUATION_SCOPE}" if a.mode == "focused" and a.after == "continue"
             else "<models, regimes, problem family>")
    iso = ("L1 only" if a.isolation == "L1" else
           "L2 via <subagent | separate CLI process | fresh API call> [authorized <date>; flags <...>]")
    return f"""# Contract

## Objective (verbatim)
{objective}

## Key difference (verbatim)
{keydiff or '(none given)'}

## From your notes (verbatim, with paths)
(priorities, success criteria, the result the user wants; "none stated" if none)

## Mode
{a.mode} - reason: <why this mode>
{after_line(a)}
## Scope boundaries
- In scope: {scope}
- Out of scope: <...>

## Limits
- User limits: <time, rounds, cost, stop conditions; "none stated" if none>

## Lane budgets
- Default rounds per lane before a lane-budget event: {a.lane_budget}

## Capability card (checked <date>)
isolation:  {iso}
dispatch:   blocking-parallel | background+notify | detached-process | sequential
K:          {a.k if a.k else '<max concurrent workers>'}
worker_io:  files <yes|no>; shell <yes|no>; web <yes|no|unknown>
solvers:    <exact arithmetic, LP/ILP, SAT/SMT, CAS available to workers, or none>
file_scope: <yes|no>: workers read run_dir and skill_dir and write in run_dir without prompts
python:     <python3 | python | py -3 | none>
skill_dir:  {skill_dir()}
run_dir:    {apath(run)}
turn_model: text-only reply ends the turn: <yes | no | unknown (treat as yes) | delegated (single return)>
"""


def checkpoint_md():
    return f"""{pointer()}
# Checkpoint
{ST_BEGIN}
(written by ri.py status; do not edit)
{ST_END}
## Running
## Waiting on
## Pending events
## Next actions
## Notes
"""


def init_files():
    return {
        "checkpoint.md": checkpoint_md(),
        "progress.md": f"""{pointer()}
# Progress (orchestrator-owned; answer first)
State: initialised; nothing dispatched yet.

## 1. What is now known
(nothing established yet)
## 2. Picture
(not yet drawn)
## 3. Frontier before/after (baseline vs with X; a label in every cell)
| Cell | Baseline | With X | Label |
|---|---|---|---|
## 4. Headlines and status
## 5. Results with assurance profiles
## 6. Refuted conjectures and dead ends
## 7. Running now and why
## 8. What needs the user
(nothing)
""",
        "sources/index.md": """# Sources index (orchestrator-owned; `ri.py intake` adds rows)

| ID | Original name | Stored path | Type | Size | Status | Relevance |
|---|---|---|---|---|---|---|
""",
        "frontier/model.md": """# Model cards (investigator-owned; format: references/frontier-method.md §2)

## M0 baseline (<source>)
Instances: ...                     Guarantee, with quantifier order: ...
Information and timing: ...        Known in advance: <n, horizon, distribution, ...>
Randomness: <private/public; what the adversary sees>     Adversary: <oblivious/adaptive>
Interaction/rounds: ...            Objective and measure: <worst/average; exact/approx; max/min>
Efficiency: ...                    c0: <value; regime finite n | per instance | asymptotic; locator>
## M1 = M0 + X (variant: <label>)  [fields that differ, plus:]
Change: relaxation | restriction | replacement; quantitative | on-off
Frame: RESOURCE-CURVE | ON-OFF | COMBINATION (frontier-method.md §1)
X permits: ...  Unit: ...  Amount k (may be k(n)): ...  Charged as: ...  Timing: ...
X depends on (oracle-type X): instance only | instance and coins | adversary-chosen
Trust: trusted | untrusted (quality of X: error measure eta, range)
Ignorable (may protocols ignore X?): yes | no
Endpoints (claims): c(0) = c0 (anchor rule); c(inf) = <value>; k_triv = <least k making the task trivial> | none
MODEL-GATE: <Txxx verdict>
## Lattice
## Degeneracy log
""",
        "frontier/map.md": """# Frontier map — measure: <measure, maximize|minimize> (investigator-owned)
## Grid M1   (each cell: gap class / status / questions)
## Curves: THRESHOLD ... (Q..); SATURATION ... (Q..); TRADE-OFF ... (Q..)
## Invariant checks
## Breadth reviews
""",
        "frontier/transfer.md": """# Transfer audit (investigator-owned; format: references/frontier-method.md §4)

Result | Side | Technique | Model | Proof verdict | Bound in model | Checked | Questions
""",
        "frontier/story.md": """# Story (at most 3 candidate headlines; investigator-owned)

## H1 (leading) — <one-sentence theorem as an expert would state it>
Needs: <Qxx.Ri (status)>    Missing: ...
Skeptic CLAIM-GATE: <Txxx: verdict>
Significance: class <1-5>; expert surprise: <evidence or "no evidence">
""",
        "instructions.md": """# Standing instructions (process-advisor-owned)
revision: 0

<!-- Format (prompts/process-advisor.md), read by `ri.py task new`. A rule is a '## SI<nn>' block
with an applies: line; packets receive only 'SI<nn>: <text>'.
## SI01
applies: prover, verifier
review-safe: yes
text: <the rule, standing alone>
reason: <evidence IDs>
since: <revision>
-->
""",
    }


def question_md(qid, q):
    return f"""# {qid} — {q['title']}    version: 1    status: draft
(investigator-owned; the status that counts is in state.json - see `ri.py status`)
Model: {q.get('model') or '<M#>'}   Kind: <kind>   Tier: {q.get('tier') or '<SAFE | CORE | AMBITIOUS | EXPLORE>'} — <two-line reason>
Serves: <SAFE only: the card it serves>   Certifies: <TRANSFER/SURVIVAL only: row or edge>
R1: <exact: quantifiers in order, parameters, error probability, uniformity, how X counts>
R2: <R1 ⇒ R2; holds where R1 may fail: <regime or class>>
R3: <lowest rung not implied by the nearest known result, closable in 1–2 rounds>
D:  <disproof target; default ¬R1>        D refutes: R1 (default) | Rj
Current rung: R1   Slots: <prover slots per round>
Target cells: <key> — if true: <map change>; if false: <map change>
Evidence: <scout tables with ranges and n/k; transfer rows with labels; analogies and where they break>
Cheapest falsifier: ...   Nearest known result: <locator>; gap step: <the step R1 needs beyond it>
Lineage: parent {q.get('parent') or '<Qxx | user | prior program>'}; operator {q.get('operator') or '<name>'}; trigger <event E#, C###/L###/T###>
Skeptic: <Txxx verdict; plausibility supported/mixed/doubtful; one line>
Park/kill: <reason; resurrection condition>
History: <v1 Txxx created>
"""


def statement_md(qid):
    return f"""# Lane {qid} - statement (investigator-owned; the only problem statement provers see)

Background. Read: <paths to source cards / papers / ledger entries>. Baseline model M0: <tuple>.
New model M<k>: <tuple; what X permits; unit and charging of X; what is known in advance>.
Known in this model (from the frontier map, with labels): ACH ...; IMP ...;
  baseline impossibility <S03 Thm 2> breaks at step s because ... (transfer audit, <label>);
  small-case data (numerical evidence, non-binding): <scout table path>.
Goal. Prove or disprove: <R1>.
Disproof target. D: <D>. D refutes: <R1 | Rj>.
Ladder. If you cannot establish R1, first establish R2: <...>; failing that R3: <...>;
  then strengthen. Each rung is valuable on its own; label the highest rung you reach.
Ideal shape. <if an IMP shows the gap |c(k) - r| is Omega(g(k)), an ideal ACH shows it is O(g(k))>.
Constraints. <solution class; what the protocol may depend on; efficiency; how X is counted>.
Allowed simplifying assumptions (to be removed later): <... | none>.
Not accepted: a different model; use of X beyond its charge; existential where explicit required.
Sanity. <scout check: predicate and small domain> | not checkable (<reason>).
Literature. Reviewers may also search: <aliases of X>.
"""


def lane_budget(st, q):
    """Rounds before a lane-budget event: the lane's own budget (q set --budget), else the run's."""
    return q.get("budget") or st["lane_budget"]


def is_gate_only(q, rnd):
    """Round rnd of question q is a gate-only round (program.md sec. 5.3): no provers."""
    return rnd in (q.get("gate_only") or [])


def in_gate_only_round(q):
    return q["round"] >= 1 and is_gate_only(q, q["round"])


def budget_used(q, upto=None):
    """Prover rounds since opening or the last lane-budget renewal (budget_base), up to round upto
    (default: the current round). Gate-only rounds never count toward the lane's round budget."""
    upto = q["round"] if upto is None else upto
    base = q.get("budget_base", 0)
    return upto - base - sum(1 for r in q.get("gate_only") or [] if base < r <= upto)


def plan_md(st, qid, n):
    q = st["questions"][qid]
    return (f"# {qid} round {n:02d} — N = {q.get('slots') or '<not set: q set --slots>'}; "
            f"rung {q.get('rung') or '<not set>'}; plausibility {q.get('plausibility') or '<not set>'}; "
            f"budget {budget_used(q, n)} of {lane_budget(st, q)}"
            + ("; gate-only (no provers: reviews of a skeptic's argument)" if is_gate_only(q, n) else "") + "\n")


# ---------------------------------------------------------------- standing instructions

def parse_instructions(text):
    """Return (revision, rules) (C5). A rule is a '## ' block with an `applies:` line; blocks without
    it (e.g. '## Removed in revision N') are not rules. Packets get only '<ID>: <text>'."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    m = re.search(r"(?im)^\s*revision\s*:\s*(\d+)", text) or re.search(r"(?i)\brevision\s+(\d+)", text)
    rev = int(m.group(1)) if m else 0
    rules = []
    for b in re.split(r"(?m)^(?=#{2,3}\s)", text):
        hm = re.match(r"#{2,3}\s+(.*)", b.strip())
        if not hm:
            continue
        fields, body = {}, []
        for line in b.strip().splitlines()[1:]:
            fm = re.match(r"\s*([A-Za-z][\w-]*)\s*:\s*(.*)$", line)
            key = fm.group(1).lower() if fm else None
            if key in ("applies", "review-safe", "text", "reason", "since"):
                fields.setdefault(key, fm.group(2).strip())
            elif line.strip():
                body.append(line.strip())
        if "applies" not in fields:
            continue
        rid = (hm.group(1).split() or ["SI"])[0]
        roles = [x.lower() for x in re.findall(r"[A-Za-z*][A-Za-z\-:*]*", re.sub(r"\(.*?\)", "", fields["applies"]))]
        safe = (fields.get("review-safe", "").split() or [""])[0].lower() in ("yes", "true")
        rules.append({"id": rid, "text": f"{rid}: {fields.get('text') or ' '.join(body)}".strip(),
                      "applies": roles or ["all"], "review_safe": safe})
    return rev, rules


def rule_applies(rule, role, mode):
    for tok in rule["applies"]:
        r, _, m = tok.partition(":")
        if r in ("all", "*", "everyone") or r in (role, role + "s"):
            if not m or (mode and m.upper() == mode):
                return True
    return False


# ---------------------------------------------------------------- gates

def reviews_of(st, cid):
    return [r for r in st["reviews"] if r["cand"] == cid]


def task_ctx(st, tid):
    return (st["tasks"].get(tid) or {}).get("context")


def task_iso(st, tid):
    return (st["tasks"].get(tid) or {}).get("isolation") or st.get("isolation_default", "L2")


def same_l2_context(st, a, b, b_ctx=None):
    """True when tasks a and b are recorded with the same context at isolation L2."""
    ca, cb = task_ctx(st, a), b_ctx or task_ctx(st, b)
    return bool(ca and cb and ca == cb and task_iso(st, a) == "L2" and task_iso(st, b) == "L2")


def authors_of(st, c):
    """(task, recorded context) pairs that must not review candidate c."""
    out = [(c["author"], c.get("author_context"))]
    if c.get("from") and c["from"] in st["candidates"]:
        src = st["candidates"][c["from"]]
        out.append((src["author"], src.get("author_context")))
    return out


def independence_problem(st, reviewer, c):
    for author, actx in authors_of(st, c):
        if reviewer == author:
            return f"{reviewer} authored this item (or its source)"
        if same_l2_context(st, reviewer, author, actx):
            return f"{reviewer} shares context {task_ctx(st, reviewer)!r} with author {author}"
    return None


def is_salvage(st, r):
    """A SALVAGE review: recorded as individual, never a pass (D10)."""
    return r["scope"] == "individual" and (
        "salvage" in (r.get("note") or "").lower() or (st["tasks"].get(r["task"]) or {}).get("mode") == "SALVAGE")


def blocks(ob):
    """A CRITICAL/MAJOR objection blocks unless rejected (adjudicated) or withdrawn."""
    return ob["severity"] in ("CRITICAL", "MAJOR") and not (
        ob["status"] == "resolved" and ob.get("how") in ("rejected", "withdrawn"))


def blocking_objections(st, cid):
    return [(r, o) for r in reviews_of(st, cid) for o in r["objections"] if blocks(o)]


def effective_verdict(r):
    """FAIL/INCONCLUSIVE whose every CRITICAL/MAJOR objection was rejected or withdrawn
    counts as a pass; INCONCLUSIVE without objections (unchecked step) stays."""
    v = r["verdict"]
    if v in ("FAIL", "INCONCLUSIVE"):
        heavy = [o for o in r["objections"] if o["severity"] in ("CRITICAL", "MAJOR")]
        if heavy and not any(blocks(o) for o in heavy):
            return "PASS_WITH_MINOR" if any(o["severity"] == "MINOR" for o in r["objections"]) else "PASS"
    return v


def is_fragment(c):
    return c["kind"] in ("manuscript", "imported", "transfer") or (c["kind"] == "lemma" and bool(c.get("from")))


def single_gate(c):
    if c["kind"] == "manuscript":
        return "paper"
    if c["kind"] in ("imported", "transfer") or (c["kind"] == "lemma" and c.get("from")):
        return "isolated"
    return None


def witness_waived(st, cid):
    """No WITNESS gate (verification.md sec. 1, runtime.md sec. 7) when the run has no code execution
    (init --no-code) or a scout WITNESS task on the candidate returned blocked: the witness is not
    machine-checkable (prompts/scout.md)."""
    if st.get("code") is False:
        return True
    return any(t["role"] == "scout" and t.get("mode") == "WITNESS" and t["status"] == "blocked"
               and cid in (t.get("cands") or []) for t in st["tasks"].values())


def needed_scopes(st, cid):
    """Required gate scopes by kind; a tuple entry means 'any of'. Gap drafts get SALVAGE + CROSS."""
    c = st["candidates"][cid]
    if c.get("gap"):
        return ["individual", "cross"]
    if single_gate(c):
        return [single_gate(c)]
    if c["kind"] == "counterexample":  # every counterexample, a skeptic's witness too (verification.md sec. 1, 8)
        return ["individual", "cross"] if witness_waived(st, cid) else ["individual", "witness", "cross"]
    return ["individual", "cross"]


def delta_review_of(st, c):
    """K76: the parent's PAPER review that a fills-only manuscript revision counts as its own, or None."""
    p = st["candidates"].get(c.get("revises") or "")
    if not (c.get("delta_review") and p):
        return None
    return next((r for r in reviews_of(st, c["revises"]) if r["task"] == c["delta_review"]
                 and r["scope"] == "paper" and r["sha256"] == p["sha256"]), None)


def missing_scopes(st, cid):
    """Gate scopes with no review at all yet (for dispatch suggestions)."""
    have = {r["scope"] for r in reviews_of(st, cid)}
    if delta_review_of(st, st["candidates"][cid]):
        have.add("paper")
    out = []
    for need in needed_scopes(st, cid):
        opts = need if isinstance(need, tuple) else (need,)
        if not have.intersection(opts):
            out.append("/".join(opts))
    return out


def attachment_problems(run, c):
    """K42: hashed attachments (cand add --attach) that are missing or changed since the freeze."""
    return [f"attachment {x['path']} changed since freeze (stale): add a new candidate"
            for x in c.get("attachments") or []
            if not is_file(Path(run) / x["path"]) or sha256_file(Path(run) / x["path"]) != x["sha256"]]


SECOND_PASS = "needs a second ISOLATED pass (new_argument: yes)"


def gate_check(st, run, cid):
    """Return (problems, label). No problems means the acceptance gate holds."""
    c = st["candidates"][cid]
    probs = []
    if c.get("gap"):
        probs.append(f"gap declared ({c['gap']}): a gap draft is never accepted (salvage via auditor)")
    path = Path(run) / c["path"]
    if not is_file(path):
        probs.append(f"candidate file {c['path']} is missing")
    elif sha256_file(path) != c["sha256"]:
        probs.append(f"candidate file {c['path']} changed since freeze (stale): add a new candidate")
    probs += attachment_problems(run, c)
    revs = [r for r in reviews_of(st, cid) if r["sha256"] == c["sha256"]]
    delta = delta_review_of(st, c) if c["kind"] == "manuscript" else None
    if delta:  # a fills-only revision: its parent's PAPER review counts as its PAPER pass
        revs.append(delta)
    single = single_gate(c)

    def fidelity_ok(r):
        # I3: the two main gates of a lane result must report fidelity MATCH explicitly;
        # for single-gate items (fragment, imported, transfer, manuscript) fidelity is optional.
        if not single and r["scope"] in ("individual", "cross"):
            return r.get("fidelity") == "MATCH"
        return r.get("fidelity") in (None, "", "MATCH")

    for r in revs:  # AND gate: any non-pass blocks
        if r["scope"] not in GATE_SCOPES:
            continue
        ev = effective_verdict(r)
        if ev not in PASSING:
            probs.append(f"{r['scope']} review by {r['task']}: {ev}")
        if not fidelity_ok(r):
            probs.append(f"{r['scope']} review by {r['task']}: fidelity {r.get('fidelity') or 'not reported'} "
                         f"(MATCH needed for {c.get('claims') or cid})")
    heavy = blocking_objections(st, cid) + [(delta, o) for o in (delta or {}).get("objections", []) if blocks(o)]
    for r, o in heavy:
        probs.append(f"objection {o['id']} {o['severity']} is {o['status']}" + (f" ({o['how']})" if o.get("how") else ""))

    def good(r):
        return (effective_verdict(r) in PASSING and fidelity_ok(r) and not is_salvage(st, r)
                and independence_problem(st, r["task"], c) is None)

    passes = {s: [r for r in revs if r["scope"] == s and good(r)] for s in SCOPES}
    counted = []
    if single:
        counted = passes[single][:1]
        if not counted:
            probs.append(f"needs {single.upper()} pass from a task that authored neither the item nor its source")
        elif c["kind"] == "transfer" and any(r.get("new_argument") for r in revs if r["scope"] == "isolated"):
            # K43: a transfer that rests on a new argument needs two passes from distinct fresh tasks
            pair = next(([i, j] for i in passes["isolated"] for j in passes["isolated"]
                         if i["task"] != j["task"] and not same_l2_context(st, i["task"], j["task"])), None)
            if pair is None:
                probs.append(SECOND_PASS)
            counted = pair or counted
    elif not c.get("gap"):
        needs_witness = c["kind"] == "counterexample" and not witness_waived(st, cid)
        second = passes["cross"]
        pair = next(([i, j] for i in passes["individual"] for j in second
                     if i["task"] != j["task"] and not same_l2_context(st, i["task"], j["task"])), None)
        if not passes["individual"]:
            probs.append("needs INDIVIDUAL pass from a non-author task")
        if not second:
            probs.append("needs CROSS pass from a non-author task")
        if passes["individual"] and second and pair is None:
            probs.append("INDIVIDUAL and second-gate passes must come from different tasks and contexts")
        counted = pair or []
        if needs_witness:
            if passes["witness"]:
                counted = counted + passes["witness"][:1]
            else:
                probs.append("needs WITNESS pass from a non-author scout task (every counterexample; waived "
                             "only if a WITNESS task returns blocked or the run was initialised with --no-code)")
    label = "agent-checked"
    for r in counted:
        if task_iso(st, r["task"]) == "L1":
            label = "self-checked"
    for d in c.get("deps") or []:
        e = st["ledger"].get(d)
        if e is None:
            probs.append(f"dependency {d} is not a ledger entry")
        elif e["status"] != "active":
            probs.append(f"dependency {d} is {e['status']}")
        elif e.get("label") == "self-checked":
            label = "self-checked"
    if c["status"] == "proposed":  # a scout check aimed at the candidate holds acceptance until it returns
        probs += [f"{t['mode'].lower()} check {k} still running" for k, t in sorted(st["tasks"].items())
                  if t["role"] == "scout" and t.get("mode") in ("SANITY", "WITNESS") and t["status"] in LIVE
                  and cid in (t.get("cands") or [])]
    return list(dict.fromkeys(probs)), label


def cand_assumes(st, cid):
    """D6: union of the allowed assumptions reported by the candidate's current gate reviews."""
    c = st["candidates"][cid]
    out = []
    for r in reviews_of(st, cid):
        a = r.get("assumes")
        if a and r["scope"] in GATE_SCOPES and r["sha256"] == c["sha256"] and a not in out:
            out.append(a)
    return out


def assumes_note(items, sep=" "):
    return f"{sep}(assumes: {'; '.join(items)})" if items else ""


def superseded_by(st, cid):
    return [k for k, c in st["candidates"].items() if c.get("revises") == cid]


def outcome(st, run, cid):
    c = st["candidates"][cid]
    if c["status"] == "accepted":
        lid = ledger_of(st, cid)
        return f"accepted ({lid or c.get('label')})"
    if c["status"] == "quarantined":
        return "quarantined"
    if c.get("gap"):
        return "gap declared"
    revs = [r for r in reviews_of(st, cid) if r["scope"] in GATE_SCOPES and not is_salvage(st, r)]
    verdicts = [effective_verdict(r) for r in revs]
    heavy = blocking_objections(st, cid)
    if "FAIL" in verdicts or any(o["severity"] == "CRITICAL" for _, o in heavy):
        return "failed"
    if "INCONCLUSIVE" in verdicts or heavy or any(r.get("fidelity") not in (None, "", "MATCH") for r in revs):
        return "inconclusive"
    return "ready to accept" if not gate_check(st, run, cid)[0] else "pending review"


def ledger_of(st, cid):
    return next((k for k, e in sorted(st["ledger"].items())
                 if e["cand"] == cid and e["kind"] != "exclusion" and e["status"] == "active"), None)


def load_bearing(st):
    """Ledger IDs in the dependency closure of accepted top-rung (R1) results and of the presented
    candidates (K43: st["selected"], the comparator's selection or a writer's --cand without one)."""
    seen, stack, sel = set(), [], set(st.get("selected") or [])
    for k, c in st["candidates"].items():
        if c["status"] == "accepted" and (k in sel or (c["kind"] in RUNG_KINDS
                                                       and (c.get("claims") or "").endswith(".R1"))):
            stack.extend(c.get("deps") or [])
    while stack:
        lid = stack.pop()
        if lid in seen or lid not in st["ledger"]:
            continue
        seen.add(lid)
        stack.extend(st["ledger"][lid].get("deps") or [])
    return seen


def needs_second_isolated(st, lid):
    e = st["ledger"][lid]
    c = st["candidates"].get(e["cand"], {})
    if not (c.get("kind") in ("imported", "transfer") or (c.get("kind") == "lemma" and c.get("from"))):
        return False
    tasks = {r["task"] for r in reviews_of(st, e["cand"])
             if r["scope"] == "isolated" and effective_verdict(r) in PASSING}
    return len(tasks) < 2


def quarantine_closure(st, roots_l, roots_c):
    """Transitive closure: entries' own candidates, dependants via deps."""
    ql, qc = set(roots_l), set(roots_c)
    qc.update(st["ledger"][lid]["cand"] for lid in roots_l)
    changed = True
    while changed:
        changed = False
        for lid, e in st["ledger"].items():
            if lid not in ql and (e["cand"] in qc or set(e.get("deps") or []) & ql):
                ql.add(lid)
                changed = True
        for cid, c in st["candidates"].items():
            if cid not in qc and c["status"] == "accepted" and set(c.get("deps") or []) & ql:
                qc.add(cid)
                changed = True
    return ql, qc


# ---------------------------------------------------------------- exclusions (D2, D3)

def covers(e):
    """Claims an exclusion covers: Q.R1..Rj, since refuting Rj refutes every stronger rung."""
    if e.get("covers"):
        return e["covers"]
    x = e.get("excludes") or ""
    q, _, r = x.partition(".")
    return [f"{q}.R{i}" for i in range(1, int(r[1:]) + 1)] if re.fullmatch(r"R\d+", r) else [x]


def span(claims):
    if len(claims) < 2:
        return claims[0] if claims else "-"
    return f"{claims[0]}..{claims[-1].split('.')[1]}"


def excluded_by(st, claim):
    for lid, e in sorted(st["ledger"].items()):
        if e["kind"] == "exclusion" and e["status"] == "active" and claim in covers(e):
            return lid
    return None


def exclusion_of(st, cid):
    return next((k for k, e in sorted(st["ledger"].items())
                 if e["kind"] == "exclusion" and e["cand"] == cid and e["status"] == "active"), None)


def d_refutes(run, qid):
    """The rung D refutes: the lane statement's 'D refutes: Rj' line, else R1."""
    m = re.search(r"(?i)D refutes\W*?:?\s*(R\d+)", read(Path(run) / "lanes" / qid / "statement.md"))
    return f"{qid}.R{int(m.group(1)[1:])}" if m else f"{qid}.R1"


def exclusion_problem(st, run, claim, cid):
    """D2: None if candidate cid may exclude claim, else the reason."""
    c = st["candidates"][cid]
    qid, rung = claim.split(".")
    if rung == "D":
        return f"{claim}: D itself is never excluded"
    if c.get("lane") != qid:
        return f"{claim} is not in the lane of {cid} ({c.get('lane') or 'no lane'})"
    if c["kind"] == "counterexample":
        if c.get("claims") != claim:
            return f"a counterexample excludes exactly the rung it claims to refute ({c.get('claims')}), not {claim}"
    elif c["kind"] in RUNG_KINDS and c.get("claims") == f"{qid}.D":
        want = d_refutes(run, qid)
        if claim != want:
            return f"a proof of {qid}.D excludes exactly the rung D refutes ({want}, from the lane statement)"
    else:
        return (f"{cid} is a {c['kind']} claiming {c.get('claims') or '-'}: exclude needs an accepted "
                f"counterexample or an accepted proof of {qid}.D")
    return None


CONTRA_TAIL = ("Quarantine both (quarantine --code contradiction; it logs model-change), dispatch a TARGETED "
               "review and a fresh SECOND-INDEPENDENT review of the accepted proof (verification.md sec. 8)")


def is_rung_claim(claim):
    return bool(re.fullmatch(r"Q\d+\.R\d+", claim or ""))


def refutation_target(run, c):
    """The rung a counterexample or a proof of D refutes (D2): its own claim, or the 'D refutes' rung."""
    cl = c.get("claims") or ""
    if c["kind"] == "counterexample" and is_rung_claim(cl):
        return cl
    if c["kind"] in RUNG_KINDS and cl.endswith(".D") and c.get("lane"):
        return d_refutes(run, c["lane"])
    return None


def refuted_by(st, run, claim, skip=None):
    """An accepted counterexample or proof of D whose (recorded or still pending) exclusion covers claim."""
    for k, x in sorted(st["candidates"].items()):
        if k != skip and x["status"] == "accepted":
            t = refutation_target(run, x)
            if t and claim in covers({"excludes": t}):
                return k
    return None


def accept_conflict(st, run, cid):
    """D3: why accepting cid would contradict an exclusion or an accepted result; None if it would not.
    Exclusions are never automatic, so an accepted refutation whose exclusion is pending counts too."""
    c = st["candidates"][cid]
    claims = c.get("claims") or ""
    if c["kind"] in RUNG_KINDS and is_rung_claim(claims):
        lid = excluded_by(st, claims)
        if lid:
            return f"{claims} is excluded by {lid} (witness {st['ledger'][lid]['cand']})"
        w = refuted_by(st, run, claims, skip=cid)
        if w:
            return f"{claims} is refuted by accepted {w} (exclusion not yet recorded)"
    tgt = refutation_target(run, c)
    if tgt:
        cov = covers({"excludes": tgt})
        clash = [k for k, x in sorted(st["candidates"].items()) if k != cid and x["status"] == "accepted"
                 and x["kind"] in RUNG_KINDS and x.get("claims") in cov]
        if clash:
            return f"{st['candidates'][clash[0]]['claims']} is accepted ({clash[0]}) and {cid} refutes it"
    return None


def contradictions(st, run):
    """(claim, cid, by): an accepted rung result whose claim an active exclusion (Lyyy) covers, or an
    accepted counterexample or proof of D (Cyyy) whose exclusion is still pending (D3)."""
    out = []
    for k, c in sorted(st["candidates"].items()):
        cl = c.get("claims") or ""
        if c["status"] == "accepted" and c["kind"] in RUNG_KINDS and is_rung_claim(cl):
            by = excluded_by(st, cl) or refuted_by(st, run, cl, skip=k)
            if by:
                out.append((cl, k, by))
    return out


def pending_conflicts(st, run):
    """(cid, why): proposed candidates whose gates hold but whose acceptance accept refuses (D3)."""
    out = []
    for k, c in sorted(st["candidates"].items()):
        if (c["status"] == "proposed" and not superseded_by(st, k)
                and (c["kind"] in RUNG_KINDS or c["kind"] == "counterexample") and not gate_check(st, run, k)[0]):
            why = accept_conflict(st, run, k)
            if why:
                out.append((k, why))
    return out


def contradiction_text(claim, cid, by):
    if by.startswith("L"):
        return f"{claim} accepted ({cid}) and excluded ({by})"
    return f"{claim} accepted ({cid}) and refuted by accepted {by} (exclusion pending)"


# ---------------------------------------------------------------- generated views

def split_objection(text):
    """Split objection text into (location, tag, rest).

    Canonical form: '<location> [<TAG>] - <one line>', e.g. 'Lemma 3 [PROB] - union bound ...'.
    Also accepted: '<location>: <one line>' and '<location> - <one line>'. Location is '' when
    it cannot be identified (or is implausibly long)."""
    text = (text or "").strip()
    m = re.match(r"^(?P<loc>[^\[\]]*?)\s*\[(?P<tag>[A-Za-z][A-Za-z-]*)\]\s*(?:-|:)?\s*(?P<rest>.*)$", text)
    if m:
        loc, tag, rest = m.group("loc").strip(" :-"), m.group("tag").upper(), m.group("rest")
    else:
        tag = ""
        parts = re.split(r"\s+-\s+|:\s+", text, maxsplit=1)
        loc, rest = (parts[0], parts[1]) if len(parts) == 2 else ("", text)
    if len(loc) > 60:
        loc, rest = "", text
    return loc, tag, rest


def claim_key(claim):
    m = re.fullmatch(r"Q\d+\.(R(\d+)|D)", claim or "")
    if not m:
        return (3, 0, claim or "")
    return (1, 0, "") if m.group(1) == "D" else (0, int(m.group(2)), "")


def direction_target(st, direction, depth=0):
    """The claim a direction aims at (D8): PROVE/DISPROVE -> its claim; REPAIR -> the repaired
    candidate's target; SPECIAL-CASE -> the claim it names, else the case text."""
    if not direction or depth > 50:
        return None
    verb, _, arg = direction.partition(" ")
    if verb in ("PROVE", "DISPROVE"):
        return arg
    if verb == "REPAIR":
        c = st["candidates"].get(arg, {})
        return direction_target(st, c.get("direction"), depth + 1) or c.get("claims")
    m = re.search(r"\bQ\d+\.(?:R\d+|D)\b", arg, re.I)
    return norm_claim(m.group(0)) if m else f"SPECIAL-CASE {arg}"


def failing_step(run, st, k, target):
    """The draft's obstacle when it claims less than its target, else the decisive objection's location."""
    c = st["candidates"][k]
    if c.get("claims") and target and c["claims"] != target:
        ob = section_paragraph(Path(run) / c["path"], ("Obstacle to the assigned target",))
        if ob:
            return "obstacle: " + ob
    if c.get("gap"):
        return c["gap"]
    heavy = sorted(blocking_objections(st, k), key=lambda ro: SEVERITIES.index(ro[1]["severity"]))
    return (split_objection(heavy[0][1]["text"])[0] or "-") if heavy else "-"


def holds_desc(st, q):
    ev = {e["id"]: e for e in st["events"]}
    return ", ".join(f"{h} ({ev[h]['type']})" if h in ev else h for h in q.get("held_by") or [])


def regenerate_record(run, st, qid):
    """Write lanes/Qxx/record.md: attempts grouped by direction target (D8)."""
    q, C, L = st["questions"][qid], st["candidates"], st["ledger"]
    mine = sorted(k for k, c in C.items() if c.get("lane") == qid)
    attempts = [k for k in mine if not is_fragment(C[k])]
    frags = [k for k in mine if is_fragment(C[k]) and C[k]["kind"] != "manuscript"]
    acc = [f"{C[k]['claims']}" + (" refuted" if C[k]["kind"] == "counterexample" else "")
           + f" by {k} ({C[k].get('label')}"
           + (f"; assumes: {'; '.join(C[k]['assumes'])}" if C[k].get("assumes") else "") + ")"
           for k in attempts if C[k]["status"] == "accepted" and C[k].get("claims")
           and C[k]["kind"] in RUNG_KINDS + ("counterexample",)]
    exc = [f"{span(covers(e))} by {lid} (witness {e['cand']})" for lid, e in sorted(L.items())
           if e["kind"] == "exclusion" and e["status"] == "active" and covers(e)[0].startswith(qid + ".")]
    out = [f"# Record of attempts — {qid} (generated)", "",
           f"Generated by ri.py from state.json (seq {st['seq']}); regenerate with `ri.py record RUN {qid}`. "
           "Attempt records are experience, never premises.",
           f"Question: {q['title']} | status {q['status']} | round {q['round']} | model {q.get('model') or '-'} | "
           f"N {q.get('slots') or '-'} | plausibility {q.get('plausibility') or '-'}"
           + (f" | HELD by {holds_desc(st, q)}" if q.get("held_by") else ""),
           f"Accepted: {', '.join(acc) or 'none'}", f"Exclusions: {', '.join(exc) or 'none'}"]
    groups = {}
    for k in attempts:
        c = C[k]
        groups.setdefault(direction_target(st, c.get("direction")) or c.get("claims") or "other", []).append(k)
    for target in sorted(groups, key=claim_key):
        out += [f"## Target {target}",
                "| Cand | Rd | Prover | Claimed | Method | Outcome | Failing step | Decisive objection(s) |",
                "|---|---|---|---|---|---|---|---|"]
        for k in groups[target]:
            c = C[k]
            heavy = sorted(blocking_objections(st, k), key=lambda ro: SEVERITIES.index(ro[1]["severity"]))

            def obj_cell(r, o):
                loc, tag, rest = split_objection(o["text"])
                return (f"{o['id']} {o['severity']}" + (f" [{tag}]" if tag else "")
                        + f" {cell((loc + ' ' if loc else '') + rest, 70)} ({r.get('report') or 'no report'})")
            claimed = (c.get("claims") or "-") + ("" if c["kind"] == "proof" else f" ({c['kind']})") + (
                f", revises {c['revises']}" if c.get("revises") else "")
            out.append(f"| {k} | {c.get('round') or '-'} | {c['author']} | {cell(claimed)} | {cell(c.get('method'), 60)} | "
                       f"{outcome(st, run, k)} | {cell(failing_step(run, st, k, target), 70)} | "
                       f"{cell('; '.join(obj_cell(r, o) for r, o in heavy) or '-', 400)} |")
    fl = []
    for k in frags:
        c, lid = C[k], ledger_of(st, k)
        stmt = (L[lid].get("statement") if lid else None) or section_paragraph(Path(run) / c["path"]) or ""
        kind = "dead end" if re.match(r"\W*dead end", stmt, re.I) else c["kind"]
        src = f", from {c['from']}" + (f" {c['step']}" if c.get("step") else "") if c.get("from") else ""
        fl.append(f"- {lid or '(not in ledger)'} {kind} ({k}{src}): {outcome(st, run, k)} | {cell(stmt, 120)}")
    conf = {}
    for r in st["reviews"]:
        if r["cand"] in mine and C[r["cand"]]["kind"] != "manuscript":  # K81: a PAPER review confirms no step
            for s in r.get("confirmed") or []:
                conf.setdefault((r["cand"], s), []).append(r["task"])
    cl = []
    for (cid, s), tasks in conf.items():
        line = f"- {cid} {s} ({', '.join(dict.fromkeys(tasks))})"
        for f in sorted(k for k, c in C.items() if c.get("from") == cid and (c.get("step") or "").lower() == s.lower()):
            line += f" -> {f}" + (f" -> {ledger_of(st, f)}" if ledger_of(st, f) else "")
        cl.append(line)
    opens = [f"- {o['id']} {o['severity']} on {r['cand']}: {cell(o['text'], 120)} ({r.get('report') or 'no report'})"
             + (f" [{r['cand']} superseded by {', '.join(superseded_by(st, r['cand']))}]" if superseded_by(st, r["cand"]) else "")
             for r in st["reviews"] if r["cand"] in mine for o in r["objections"]
             if o["status"] == "open" and o["severity"] in ("CRITICAL", "MAJOR")]
    out += ["## Ledger fragments"] + (fl or ["(none)"])
    out += ["## Confirmed steps"] + (cl or ["(none)"])
    out += ["## Open objections"] + (opens or ["(none)"])
    atomic_write(Path(run) / "lanes" / qid / "record.md", "\n".join(out) + "\n")


def regenerate_ledger(run, st):
    """Write ledger.md: active entries, exclusions, quarantined, retracted."""
    lb = load_bearing(st)
    out = ["# Ledger", "", f"Generated by ri.py (seq {st['seq']}); regenerate with `ri.py ledger RUN`. "
           "Only active entries are usable premises (I4).", "", "## Active entries", ""]
    rows = []
    for lid, e in sorted(st["ledger"].items()):
        if e["status"] == "active" and e["kind"] != "exclusion":
            flag = " (load-bearing: needs 2nd isolated review)" if lid in lb and needs_second_isolated(st, lid) else ""
            rows.append(f"| {lid} | {e['kind']} | {cell(e.get('statement'), 160)} | {e.get('model') or '-'} | "
                        f"{e.get('label')}{flag} | {', '.join(e.get('deps') or []) or '-'} | {e['cand']} |")
    out += (["| ID | Kind | Statement | Model | Label | Deps | Source |", "|---|---|---|---|---|---|---|"] + rows) if rows else ["(none)"]
    rows = [f"| {lid} | {span(covers(e))} | {e['cand']} | {e.get('label')} | {cell(e.get('note'))} |"
            for lid, e in sorted(st["ledger"].items()) if e["status"] == "active" and e["kind"] == "exclusion"]
    out += ["", "## Exclusions (refuted rungs)", ""]
    out += (["| ID | Excludes | Witness | Label | Note |", "|---|---|---|---|---|"] + rows) if rows else ["(none)"]
    for title, status in (("Quarantined", "quarantined"), ("Retracted", "retracted")):
        rows = [f"| {lid} | {e['kind']} | {cell(e.get('statement'), 100)} | "
                f"{cell((e['code'] + ': ' if e.get('code') else '') + (e.get('reason') or '-'))} |"
                for lid, e in sorted(st["ledger"].items()) if e["status"] == status]
        out += ["", f"## {title}", ""]
        out += (["| ID | Kind | Statement | Reason |", "|---|---|---|---|"] + rows) if rows else ["(none)"]
    atomic_write(Path(run) / "ledger.md", "\n".join(out) + "\n")


def refresh_lane(run, st, lane):
    if lane and lane in st["questions"]:
        regenerate_record(run, st, lane)


def model_of(st, lane):
    return st["questions"].get(lane, {}).get("model") if lane else None


def best_rung(st, qid):
    """(rung, candidate) of the strongest accepted rung result of a lane, or (None, None)."""
    best = None
    for k, c in sorted(st["candidates"].items()):
        cl = c.get("claims") or ""
        if (c.get("lane") == qid and c["status"] == "accepted" and c["kind"] in RUNG_KINDS
                and cl.startswith(qid + ".R")):
            n = int(cl.split(".R")[1])
            if best is None or n < best[0]:
                best = (n, k)
    return (f"R{best[0]}", best[1]) if best else (None, None)


# ---------------------------------------------------------------- commands: setup and questions

def cmd_init(a):
    run = Path(a.run)
    if exists(run / "state.json"):
        fail(f"{run / 'state.json'} already exists: this run is initialised (resume it; do not re-init)")
    objective, keydiff = text_arg(a, "objective"), text_arg(a, "key_difference")
    if not objective:
        usage("init needs --objective or --objective-file")
    if a.lane_budget < 1:
        usage("--lane-budget must be >= 1")
    quote = text_arg(a, "stop_quote")
    if a.mode == "focused" and a.after == "stop":
        q = " ".join((quote or "").split())
        if not q:
            usage(NOT_A_STOP)
        if len(q) > STOP_QUOTE_MAX or q.lower() not in " ".join(objective.split()).lower():
            usage(f"--stop-quote must be the user's limiting words copied from the Objective, at most {STOP_QUOTE_MAX} "
                  "characters (the phrase that limits the run, not the whole request): " + NOT_A_STOP)
        if not LIMIT_PHRASE_RE.search(q):
            usage(f"the stop quote {q[:80]!r} contains no phrase that limits the run (for example 'only this claim', "
                  "'just prove', 'then stop', 'nothing else'): " + NOT_A_STOP)
    elif quote:
        usage("--stop-quote goes only with --mode focused --after stop")
    if a.k is not None and a.k < 1:
        usage("--k must be >= 1")
    for d in ("sources/raw", "frontier", "questions", "lanes", "candidates", "tasks", "scout", "reports"):
        xp(run / d).mkdir(parents=True, exist_ok=True)
    st = {"schema": SCHEMA, "objective": objective, "key_difference": keydiff or "",
          "mode": a.mode, "after": a.after, **({"after_quote": quote} if quote else {}), "isolation_default": a.isolation, "lane_budget": a.lane_budget, "k": a.k,
          "code": not a.no_code,
          "counters": {k: 0 for k in ("Q", "C", "L", "T", "S", "E", "lane_rounds")},
          "questions": {}, "tasks": {}, "candidates": {}, "reviews": [], "ledger": {},
          "events": [], "seq": 0}
    files = dict(init_files(), **{"contract.md": contract_md(a, run, objective, keydiff)})
    for name, text in files.items():
        if not exists(run / name):
            atomic_write(run / name, text)
    xp(run / "log.jsonl").touch()
    commit(run, st, "init", {"objective": objective[:200], "mode": a.mode, "after": a.after, "isolation": a.isolation,
                             "lane_budget": a.lane_budget, "k": a.k, "no_code": a.no_code})
    if not exists(run / "ledger.md"):
        regenerate_ledger(run, st)
    print(f"initialised {apath(run)} (mode {a.mode}"
          + (f", after delivery: {a.after}" if a.mode == "focused" else "")
          + f", isolation {a.isolation}, lane budget {a.lane_budget}"
          + (f", K {a.k}" if a.k else "") + (", no code execution: counterexamples gated without WITNESS"
                                              if a.no_code else "") + ")")


def norm_model(text):
    m = re.fullmatch(r"M(\d+)", (text or "").strip(), re.I)
    if not m:
        usage(f"malformed model ID {text!r}: use M0, M1, ...")
    return f"M{int(m.group(1))}"


def cmd_q_add(a):
    run, st = open_run(a)
    parent = get(st, "questions", "Q", a.parent) if a.parent else None
    model = norm_model(a.model) if a.model else None
    qid = next_id(st, "Q")
    q = {"title": a.title, "tier": a.tier, "status": "draft", "parent": parent, "operator": a.operator,
         "model": model, "rung": None, "round": 0, "note": None, "priority": a.priority,
         "created_seq": st["seq"] + 1}
    st["questions"][qid] = q
    if not exists(run / "questions" / f"{qid}.md"):
        atomic_write(run / "questions" / f"{qid}.md", question_md(qid, q))
    commit(run, st, "q add", {"id": qid, "title": a.title, "tier": a.tier, "parent": parent,
                              "operator": a.operator, "model": model, "priority": a.priority})
    print(f"{qid}  questions/{qid}.md  status draft" + ("  (secondary seed)" if a.priority == "secondary" else ""))


def kill_park_block(st, qid):
    """Why question qid may not be killed or parked (program.md sec. 5.3): its R1 is accepted, or a
    review or scout task on one of its candidates is live. None when it may."""
    C = st["candidates"]
    top = [k for k, c in sorted(C.items()) if c["status"] == "accepted" and c["kind"] in RUNG_KINDS
           and c.get("claims") == f"{qid}.R1"]
    if top:
        return f"its R1 is accepted ({top[0]})"
    live = sorted(filter(None, {in_flight(st, k, s) for k, c in C.items() if c.get("lane") == qid for s in SCOPES}))
    return f"{', '.join(live)} still reviewing or checking its candidates" if live else None


def cmd_q_set(a):
    run, st = open_run(a)
    qid = get(st, "questions", "Q", a.qid)
    q = st["questions"][qid]
    note = text_arg(a, "note", run)
    if not any((a.status, a.rung, a.tier, note, a.slots, a.plausibility, a.model, a.title)) and a.budget is None:
        usage("q set needs --status, --rung, --tier, --slots, --budget, --plausibility, --model, --title or --note")
    for name in ("slots", "budget"):
        if getattr(a, name) is not None and getattr(a, name) < 1:
            usage(f"--{name} must be >= 1")
    if a.status in ("killed", "parked"):
        why = kill_park_block(st, qid)
        if why:
            fail(f"{qid} cannot be set {a.status}: {why}; route by program.md sec. 5.3")
    if a.status:
        if a.status == "active" and q["status"] not in ("ready", "active", "parked"):
            print(f"note: {qid} was '{q['status']}'; the ready gate expects 'ready' before a lane opens "
                  "(a fast start, program.md sec. 6.1, opens first: its provers wait for the light gate)",
                  file=sys.stderr)
        q["status"] = a.status
        if a.status == "active" and not exists(run / "lanes" / qid / "statement.md"):
            atomic_write(run / "lanes" / qid / "statement.md", statement_md(qid))
        if a.status == "resolved" and not a.rung:
            q["rung"] = best_rung(st, qid)[0] or q.get("rung")
    if a.rung:
        m = re.fullmatch(r"R(\d+)|D", a.rung.strip(), re.I)
        if not m:
            usage(f"malformed rung {a.rung!r}: use R1, R2, ... or D")
        q["rung"] = f"R{int(m.group(1))}" if m.group(1) else "D"
    for key, val in (("tier", a.tier), ("note", note), ("slots", a.slots), ("budget", a.budget),
                     ("plausibility", a.plausibility), ("model", norm_model(a.model) if a.model else None),
                     ("title", a.title)):
        if val is not None:
            q[key] = val
    commit(run, st, "q set", {"id": qid, "status": a.status, "rung": a.rung, "tier": a.tier, "note": note,
                              "slots": a.slots, "budget": a.budget, "plausibility": a.plausibility,
                              "model": q.get("model") if a.model else None, "title": a.title})
    if q["status"] == "active":
        regenerate_record(run, st, qid)
    shown = q["status"] + (f"@{q['rung']}" if q["status"] == "resolved" and q.get("rung") else "")
    extra = "".join(f"  {k} {q[k]}" for k in ("slots", "budget", "plausibility", "model") if q.get(k))
    print(f"{qid} status {shown}{extra}" + (f"  lane lanes/{qid}/" if q["status"] == "active" else ""))


def cmd_round(a):
    if not a.open:
        usage("round needs --open")
    run, st = open_run(a)
    qid = get(st, "questions", "Q", a.qid)
    q = st["questions"][qid]
    if q["status"] != "active":
        fail(f"{qid} is '{q['status']}', not active: run 'q set {qid} --status active' first")
    held = q.get("held_by") and not a.override_hold
    if held and not a.gate_only:
        fail(f"{qid} is HELD by {holds_desc(st, q)} until RENEW: no new round "
             "(--override-hold only on the investigator's decision)")
    live = [k for k, t in st["tasks"].items()
            if t.get("lane") == qid and t.get("round") == q["round"] and t["status"] in LIVE]
    q["round"] += 1
    n = q["round"]
    q.setdefault("round_seqs", {})[str(n)] = st["seq"] + 1
    if a.gate_only:  # the breadth trigger and the round budget count prover rounds only
        q.setdefault("gate_only", []).append(n)
    else:
        st["counters"]["lane_rounds"] = st["counters"].get("lane_rounds", 0) + 1
    plan = run / "lanes" / qid / f"round-{n:02d}" / "plan.md"
    if not exists(plan):
        atomic_write(plan, plan_md(st, qid, n))
    roles = {t["role"] for t in st["tasks"].values() if t.get("lane") == qid and t.get("round") == n - 1}
    commit(run, st, "round", {"lane": qid, "round": n, "override_hold": a.override_hold, "gate_only": a.gate_only})
    print(n)
    if "summarizer" in roles and "prover" not in roles and not is_gate_only(q, n - 1):  # e.g. a non-ADVANCE light gate
        print(f"note: round {n - 1} of {qid} had briefings but no provers; it still counts toward the lane budget "
              f"(q set {qid} --budget to add a round)", file=sys.stderr)
    if live:
        print(f"note: round {n - 1} of {qid} still has live tasks: {', '.join(live)}", file=sys.stderr)
    if held:
        print(f"note: {qid} is HELD by {holds_desc(st, q)}; a gate-only round dispatches no provers, so it opens "
              "anyway (program.md sec. 5.3)", file=sys.stderr)
    if not a.gate_only and budget_used(q, n) > lane_budget(st, q):
        print(f"note: round {n} passes the lane budget ({lane_budget(st, q)} rounds since the last renewal): "
              f"a lane-budget event is due (event --type lane-budget --lane {qid})", file=sys.stderr)


# ---------------------------------------------------------------- default Assignments (B2)

def cited_sources(run, paths):
    out = []
    for p in paths:
        for n in re.findall(r"\bS(\d{2,})\b", read(Path(run) / p)):
            s = f"sources/S{int(n):02d}.md"
            if s not in out and is_file(Path(run) / s):
                out.append(s)
    return out


def dep_lines(st, cids):
    out = []
    for cid in cids:
        for d in st["candidates"][cid].get("deps") or []:
            e = st["ledger"].get(d)
            line = f"- candidates/{e['cand']}.md (ledger entry {d})" if e else f"- ledger entry {d} (not found)"
            if line not in out:
                out.append(line)
    return out


def rebuttal_lines(run, st, cid, oid):
    out = []
    for k, c in sorted(st["candidates"].items()):
        if oid in (c.get("rebuttals") or []) or (
                c.get("revises") == cid and re.search(r"(?ms)^#+\s*Rebuttals\b.*" + re.escape(oid), read(Path(run) / c["path"]))):
            out.append(f"- candidates/{k}.md, section '## Rebuttals' ({oid}): the prover's rebuttal")
    return out


def objection_cand(st, oid, cands=()):
    """The candidate objection oid was raised on; cands (that candidate or a revision of it) disambiguate."""
    on = sorted({r["cand"] for r in st["reviews"] for o in r["objections"] if o["id"] == oid})
    if not on:
        usage(f"unknown objection {oid}")
    if cands:
        near = [c for c in on if any(c == x or c in revision_ancestors(st, x) for x in cands)]
        on = near or on
    if len(on) > 1:
        usage(f"{oid} was raised on several candidates ({', '.join(on)}); give --cand")
    return on[0]


def cohort(st, qid, rnd):
    """Drafts of one lane round: the CROSS-DRAFT cohort."""
    return sorted(k for k, c in st["candidates"].items()
                  if c.get("lane") == qid and c.get("round") == rnd and not is_fragment(c))


def latest_task(st, role, mode=None, exclude=None):
    ts = [(t.get("created_seq", 0), k) for k, t in st["tasks"].items()
          if t["role"] == role and (mode is None or t.get("mode") == mode) and k != exclude]
    return max(ts)[1] if ts else None


def last_advisor_log(run, st, exclude=None):
    """(task, log path) of the latest process-advisor task that is done and wrote advisor-log.md (a pre-6.2
    analysis.md also counts); cancelled or superseded ones skipped. (None, None) if there is none."""
    ts = []
    for k, t in st["tasks"].items():
        if t["role"] == "process-advisor" and k != exclude and t["status"] == "done":
            name = next((n for n in ("advisor-log.md", "analysis.md") if is_file(Path(run) / "tasks" / k / n)), None)
            if name:
                ts.append((t.get("created_seq", 0), k, f"tasks/{k}/{name}"))
    return max(ts)[1:] if ts else (None, None)


def object_copy(run, tid, st, cid):
    """A scout's view of a candidate with a '## Object' section (skeptic arguments): its '## Statement' and
    '## Object' sections, never the proof, written to tasks/<tid>/object-Cxxx.md. Returns that path or None."""
    lines = read(Path(run) / st["candidates"][cid]["path"]).splitlines()
    obj = section_span(lines, "Object", prefix=True)
    if not obj:
        return None
    parts = [f"# Object of {cid} (copied by ri.py from candidates/{cid}.md: the claim and the object, not the proof)"]
    for name, sp in (("Statement", section_span(lines, "Statement", prefix=True)), ("Object", obj)):
        if sp:
            body = lines[sp[0]:sp[1]]
            cut = next((i for i, x in enumerate(body) if HEADING_RE.fullmatch(x)
                        and heading_key(HEADING_RE.fullmatch(x).group(2)).startswith("proof")), len(body))
            parts += ["", f"## {name}", "\n".join(body[:cut]).strip()]
    path = f"tasks/{tid}/object-{cid}.md"
    atomic_write(Path(run) / path, "\n".join(parts) + "\n")
    return path


def placeholder_value(text):
    """True for an empty value or a template placeholder such as '<R1>.' or '<exact: ...>'."""
    s = (text or "").strip().strip("*_").strip().rstrip(".").strip()
    return not s or bool(re.fullmatch(r"<[^<>]*>", s))


def has_r1(run, qid):
    """K14: an exact R1 exists: a filled 'R1:' line in questions/Qxx.md or lanes/Qxx/statement.md, or a filled
    'Goal. Prove or disprove:' line in the statement (a fast start copies the claim there)."""
    card, stmt = read(Path(run) / "questions" / f"{qid}.md"), read(Path(run) / "lanes" / qid / "statement.md")
    r1 = r"(?m)^[\s>*_-]*R1\b[^:\n]{0,30}:(.*)$"
    vals = (re.findall(r1, card) + re.findall(r1, stmt)
            + re.findall(r"(?mi)^[\s>*_-]*Goal\.?[\s*_]*Prove or disprove\s*:(.*)$", stmt))
    return any(not placeholder_value(v) for v in vals)


SAFEGUARD = ("No-prover safeguard: deliver at least one question ready at a rung no named result implies, or an R1 "
             "for a primary direction seed; give a one-line reason per event if none.")
SAFEGUARD_TASKS = 20     # K02: finished tasks without a prover task before the safeguard is due
SCALE_ROWS = 2000        # K38: sources/index.md rows above which literature, investigator and skeptic packets get a note
BUNDLED_CODE_OK = "Authorized (contract.md): run copies of the bundle's code in your task directory only."


def no_prover_safeguard(st):
    """K02: why the no-prover safeguard is due, else None. Program mode, no prover task, and either the latest
    finished SELECT's QUESTION-GATEs have returned with no ready or active question, or 20 tasks have finished.
    A run converted after a focused delivery counts only tasks created since its conversion (program.md sec. 2.1).
    Computed from state each time; nothing is stored."""
    since0 = (converted(st) or {}).get("seq", 0)
    T, Q = {k: t for k, t in st["tasks"].items() if t.get("created_seq", 0) > since0}, st["questions"]
    if st["mode"] != "program" or any(t["role"] == "prover" for t in T.values()):
        return None
    fin = sum(t["status"] in FINISHED for t in T.values())
    if fin >= SAFEGUARD_TASKS:
        return f"{fin} tasks finished"
    sel = [(t.get("created_seq", 0), k) for k, t in T.items()
           if t["role"] == "investigator" and t.get("mode") == "SELECT" and t["status"] in FINISHED]
    if not sel or any(q["status"] in ("ready", "active") for q in Q.values()):
        return None
    since, k = max(sel)
    gates = [t for t in T.values() if t["role"] == "skeptic" and t.get("mode") == "QUESTION-GATE"
             and t.get("created_seq", 0) > since and t["status"] not in GONE]
    if any(t["status"] in LIVE for t in gates) or (
            not gates and any(q.get("created_seq", 0) > since for q in Q.values())):  # SELECT's cards not gated yet
        return None
    return f"SELECT {k}'s QUESTION-GATEs left nothing ready"


def index_row_count(run):
    """sources/index.md rows, duplicate ('| - |') rows included."""
    return len(re.findall(r"(?m)^\|\s*(?:S\d+|-)\s*\|", read(Path(run) / "sources" / "index.md")))


def auto_lines(run, st, role, mode):
    """Lines ri.py adds to every packet of a kind (default, --assignment-file or --redo): the K02 safeguard
    (investigator SELECT, RENEW), the K38 scale note, and the K57 scout authorization."""
    out = []
    if role == "investigator" and mode in ("SELECT", "RENEW") and no_prover_safeguard(st):
        out.append(SAFEGUARD)
    n = index_row_count(run)
    if n > SCALE_ROWS and role in ("literature-reviewer", "investigator", "skeptic"):
        out.append(f"Scale note: sources/index.md has {n} rows; search it for the rows named here; never read it whole.")
    if role == "scout" and re.search(r"(?im)^\W*Bundled code:\s*allowed\b", read(Path(run) / "contract.md")):
        out.append(BUNDLED_CODE_OK)
    return out


PATCH_DIR_PACKETS = (("skeptic", "QUESTION-GATE"), ("skeptic", "MODEL-GATE"), ("investigator", "PROPOSE"),
                     ("investigator", "SELECT"), ("investigator", "RENEW"), ("investigator", "MODEL"),
                     ("literature-reviewer", "TRANSFER-AUDIT"))  # state.md sec. 5 rows that read the patches
PATCH_DIR_LINE = "- frontier/patches/ (filed MODEL-GATE patches, verbatim; each counts as gated)"


def patch_inputs(st, run, role, mode, lane, cands):
    """K17: input lines naming filed MODEL-GATE patches. The PATCH_DIR_PACKETS get frontier/patches/ once it
    holds a file; every packet of a lane whose model is a filed patch (or on a transfer candidate stated in
    one) gets that patch file and the patches it builds on, base first."""
    models = st.get("models") or {}
    if (role, mode) in PATCH_DIR_PACKETS:
        pdir = xp(Path(run) / "frontier" / "patches")
        has = pdir.is_dir() and any(p.suffix.lower() == ".md" for p in pdir.iterdir())
        return [PATCH_DIR_LINE] if has else []
    C, chain = st["candidates"], []
    for m in [model_of(st, lane)] + [model_of(st, C[c].get("lane")) for c in cands] + [C[c].get("model") for c in cands]:
        seen = []
        while m in models and m not in seen + chain:
            seen.insert(0, m)
            m = models[m].get("base")
        chain += seen
    return [f"- {models[m]['path']} (patch of {models[m]['base']}, verbatim; it amends the statement's model)"
            for m in chain]


def id_ranges(ids):
    """['T005', 'T006', 'T007', 'T009'] -> 'T005-T007, T009' (IDs of one prefix)."""
    p, nums, out = ids[0][0], sorted(int(x[1:]) for x in ids), []
    i = 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(fmt_id(p, nums[i]) + ("" if i == j else f"-{fmt_id(p, nums[j])}"))
        i = j + 1
    return ", ".join(out)


def done_tasks(st, role, modes=None, since=0):
    """[(ID, task)] of finished tasks of a role (and modes) created or ingested after seq since, in ID order."""
    return [(k, t) for k, t in sorted(st["tasks"].items())
            if t["role"] == role and t["status"] in FINISHED and (modes is None or t.get("mode") in modes)
            and max(t.get("created_seq", 0), t.get("ingested_seq") or 0) > since]


def result_field(run, tid, key):
    """The value of a top-level field of tasks/<tid>/result.md's header ('' if absent)."""
    return next((v for k, a, v in read_result(Path(run) / "tasks" / tid / "result.md") or [] if k == key and a is None), "")


def task_file_lines(run, items, name, what=None):
    """'- tasks/<ID>/<name> (<what>, default: role and mode)' for each (ID, task) whose file exists."""
    return [f"- tasks/{k}/{name} ({what or (t['role'] + ' ' + (t.get('mode') or '')).strip()})"
            for k, t in items if is_file(Path(run) / "tasks" / k / name)]


def existing(run, *paths):
    return [f"- {p}" for p in paths if is_file(Path(run) / p)]


def last_outer_seq(st, exclude=None):
    """created_seq of the latest investigator SELECT or RENEW task other than exclude (0 if none)."""
    ks = [latest_task(st, "investigator", m, exclude=exclude) for m in ("SELECT", "RENEW")]
    return max([st["tasks"][k].get("created_seq", 0) for k in ks if k], default=0)


def follow_up_lines(run, st, since):
    """K53: result.md of each finished literature task since seq since whose follow_ups is not none."""
    out = []
    for k, t in done_tasks(st, "literature-reviewer", since=since):
        v = result_field(run, k, "follow_ups")
        if word(v).strip("[]").lower() not in ("", "none", "-"):
            out.append(f"- tasks/{k}/result.md (literature-reviewer {t.get('mode') or ''}: follow_ups)".replace(" :", ":"))
    return out


def patches_line(run):
    """frontier/patches/ when it holds a filed patch."""
    pd = xp(Path(run) / "frontier" / "patches")
    return [PATCH_DIR_LINE] if pd.is_dir() and any(pd.iterdir()) else []


def frontier_lines(run):
    return [f"- frontier/{p.name}" for p in sorted(xp(Path(run) / "frontier").glob("*.md"))] + patches_line(run)


def index_rows(run):
    """sources/index.md rows: [{'id', 'name', 'path', 'type', 'status'}]."""
    rows = []
    for line in read(Path(run) / "sources" / "index.md").splitlines():
        cs = [x.strip() for x in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
        if len(cs) >= 6 and re.fullmatch(r"S\d+", cs[0]):
            rows.append({"id": cs[0], "name": cs[1], "path": cs[2], "type": cs[3], "status": cs[5]})
    return rows


def source_ids(text):
    """S-IDs named in text, ranges such as 'S01-S04' expanded."""
    out = []
    for m in re.finditer(r"\bS(\d+)(?:\s*[-–]\s*S?(\d+))?\b", text or ""):
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        out += [fmt_id("S", i) for i in range(a, b + 1)] if 0 <= b - a <= 50 else [fmt_id("S", a)]
    return list(dict.fromkeys(out))


def source_cards(run):
    return [f"sources/{p.name}" for p in sorted(xp(Path(run) / "sources").glob("S*.md")) if re.fullmatch(r"S\d+\.md", p.name)]


def m0_filled(run):
    """frontier/model.md has an M0 entry with its source named (not the init template)."""
    m = re.search(r"(?m)^##\s*M0\b.*$", read(Path(run) / "frontier" / "model.md"))
    return bool(m and "<source>" not in m.group(0))


def m0_card_lines(run):
    text = read(Path(run) / "frontier" / "model.md")
    m = re.search(r"(?ms)^##\s*M0\b.*?(?=^##\s|\Z)", text)
    ids = source_ids(m.group(0)) if m else []
    out = [f"- sources/{s}.md (M0 source card)" for s in ids if is_file(Path(run) / "sources" / f"{s}.md")]
    return out or ["- the M0 source cards frontier/model.md cites"]


def gate_card(text):
    """K69: a question card without its Tier text (from 'Tier:' to the end of its line) and its Skeptic,
    Plausibility and Forecast lines; indented continuation lines right after a removed part go too."""
    out, cut = [], False
    for line in text.splitlines():
        if cut and line[:1] in (" ", "\t") and line.strip():
            continue
        cut = bool(re.match(r"\s*(?:[-*]\s+)?(?:Skeptic|Plausibility|Forecast)\s*:", line))
        if cut:
            continue
        m = re.search(r"\bTier\s*:", line)
        if m:
            cut, line = True, line[:m.start()].rstrip()
            if not line.strip():
                continue
        out.append(line)
    return "\n".join(out) + "\n"


def pending_statement(run, st, qid):
    """SKILL.md sec. 5 focused step 3, program.md sec. 6.1: (task, path, gate) of the newest new/Qxx-statement.md
    that a finished MODEL or RENEW task wrote for active lane qid, while it differs from lanes/Qxx/statement.md and
    no gate created after it returned anything but ADVANCE; gate is (task, verdict code or None) of the latest
    skeptic gate on qid created after it, or None. None when no new statement waits."""
    T, q = st["tasks"], st["questions"].get(qid)
    if not q or q["status"] != "active":
        return None
    for k, t in sorted(T.items(), reverse=True):
        rel_path = f"tasks/{k}/new/{qid}-statement.md"
        if not (t["role"] == "investigator" and t.get("mode") in ("MODEL", "RENEW") and t["status"] in FINISHED
                and is_file(Path(run) / rel_path)):
            continue
        if read(Path(run) / rel_path).strip() == read(Path(run) / "lanes" / qid / "statement.md").strip():
            return None  # installed
        seq = finished_seq(t)
        codes = [v["code"] for v in q.get("verdicts") or [] if v["seq"] > seq]
        if any(c != "ADVANCE" for c in codes):
            return None  # rejected: its verdict is routed instead
        gates = sorted((x.get("created_seq", 0), g) for g, x in T.items() if x["role"] == "skeptic"
                       and x.get("mode") in ("QUESTION-GATE", "MODEL-GATE") and qid in (x.get("questions") or [])
                       and x["status"] not in GONE and x.get("created_seq", 0) > seq)
        g = gates[-1][1] if gates else None
        return k, rel_path, (g, next((v["code"] for v in q["verdicts"] if v["task"] == g), None)) if g else None
    return None


def question_gate_inputs(st, run, tid, questions):
    """Per question: a gate copy of its card (written to tasks/<tid>/card-Qxx.md) and its lane statement - for an
    active lane with a new statement not yet installed (pending_statement), that new statement."""
    out = []
    for q in questions:
        card = Path(run) / "questions" / f"{q}.md"
        if is_file(card):
            atomic_write(Path(run) / "tasks" / tid / f"card-{q}.md", gate_card(read(card)))
            out.append(f"- tasks/{tid}/card-{q}.md (the question card, gate copy)")
        new = pending_statement(run, st, q)
        out.append(f"- {new[1]} (the new version to gate; lanes/{q}/statement.md is the one in force)" if new
                   else f"- lanes/{q}/statement.md")
    return out


def dep_closure(st, cids):
    """Ledger IDs in the dependency closure of candidates cids, in ID order."""
    L, seen = st["ledger"], set()
    stack = [d for c in cids for d in st["candidates"][c].get("deps") or []]
    while stack:
        lid = stack.pop()
        if lid in L and lid not in seen:
            seen.add(lid)
            stack.extend(L[lid].get("deps") or [])
    return sorted(seen)


def model_inputs(st, run):
    """investigator MODEL opening inputs (state.md sec. 5)."""
    rows, Q = index_rows(run), st["questions"]
    carded = {Path(p).stem for p in source_cards(run)}
    docs = [r for r in rows if r["id"] not in carded and r["type"] not in ("user-notes", "archive", "code", "data")]
    other = [r for r in rows if r["id"] not in carded and r["type"] in ("code", "data")]
    out = [f"- {r['path']} (user-notes {r['id']}: read in full)" for r in rows if r["type"] == "user-notes"]
    out += ["- contract.md", "- sources/index.md"] + existing(run, "sources/bounds.md") + [f"- {p}" for p in source_cards(run)]
    out += [f"- {r['path']} ({r['id']}, uncarded)" for r in docs]
    if other:
        out.append(f"- sources/index.md: {len(other)} code or data file(s) without a card (by name only)")
    out += task_file_lines(run, done_tasks(st, "literature-reviewer", ("LANDSCAPE",)), "landscape.md", "LANDSCAPE")
    out += task_file_lines(run, [(k, t) for k, t in done_tasks(st, "scout", ("EXPLORE",))
                                 if (t.get("title") or "").upper().startswith("ANCHOR")], "table.md", "ANCHOR")
    out += task_file_lines(run, [(k, t) for k, t in done_tasks(st, "skeptic", ("QUESTION-GATE",)) if t.get("light")],
                           "gate.md", "seed light gate")
    out += [f"- tasks/{k}/result.md (literature-reviewer {t.get('mode') or ''}: found settles)".replace(" :", ":")
            for k, t in done_tasks(st, "literature-reviewer") if word(result_field(run, k, "found")).lower() == "settles"]
    for q, x in sorted(Q.items()):
        if x["status"] in ("draft", "vetting") and x.get("priority") != "secondary":
            out.append(f"- questions/{q}.md (primary seed, {x['status']})")
            if is_file(Path(run) / "lanes" / q / "statement.md"):
                out.append(f"- lanes/{q}/statement.md")
    return out


def event_lines(st, skip=()):
    evs = [e for e in st["events"] if not e.get("handled_by") and e["type"] not in skip]
    return evs, ([f"- {e['id']} {e['type']}" + (f" {e['lane']}" if e.get("lane") else "") + f": {e.get('note') or '-'}"
                  for e in evs] or ["- none"])


def carried_lines(st, run, skip=None):
    """program.md sec. 2.1: what a focused run wrote before its delivery for later - the 'Stronger (after R1)' items
    (none of a refuted question: they are false too) and the parked questions other than skip, by path."""
    Q = st["questions"]
    paths = list(dict.fromkeys(p for k in sorted(Q) if Q[k]["status"] != "refuted" for p in stronger_paths(run, st, k)))
    return ([f"- {p} (its 'Stronger (after R1)' items)" for p in paths]
            + [f"- questions/{k}.md (parked)" for k, q in sorted(Q.items()) if q["status"] == "parked" and k != skip])


ACCEPT_OPS = ("the After-ACCEPT operators (frontier-method.md sec. 10), TIGHTNESS first: the converse for the whole class "
              "the result competes in (every algorithm, protocol or mechanism with the same constraints, information, "
              "incentives and resource accounting); the converse for this specific object is its fallback rung")
GRID_LINE = ("If frontier/map.md has no grid (a focused MODEL writes none), write the M1 grid first (investigator.md "
             "MODEL step 5, frontier-method.md sec. 3) around the delivered result, with its endpoints and transfer "
             "rows, and story.md's first headline.")


def continuation_ops(run, st, qid):
    """program.md sec. 2.1: (short label, full text) of the continuation RENEW's operators, by what was delivered.
    A refutation: After-REFUTE (READING already ran in focused mode). The target rung accepted: After-ACCEPT, TIGHTNESS
    first, with the open stronger rungs R1..R(best-1) beside it. Only a weaker rung accepted (lane budget, a user
    limit) or none (a failure report): After-STALL on the open target first, then After-ACCEPT on the delivered rung."""
    q = st["questions"].get(qid or "") or {}
    best = best_rung(st, qid)[0] if q else None
    n, t = int(best[1:]) if best else 0, int(target_rung(run, st, qid)[1:]) if q else 1
    above = (f"rungs R1..R{n - 1} of lanes/{qid}/statement.md are", "candidates") if n > 2 else (
        f"rung R1 of lanes/{qid}/statement.md is", "a candidate")
    if q.get("status") == "refuted":
        ran = (q.get("operator") or "").upper() == "READING" or any(
            e["type"] == "refuted" and e.get("lane") == qid
            and st["tasks"].get(e.get("handled_by") or "", {}).get("role") == "investigator" for e in st["events"])
        refute = "the After-REFUTE operators (frontier-method.md sec. 10" + (
            "; READING already ran in focused mode: skip it)" if ran else ")")
        if best:
            return (f"After-REFUTE, then After-ACCEPT on {best}",
                    f"{refute} to the refutation, and to the accepted {best} {ACCEPT_OPS}")
        return "After-REFUTE", refute
    if best and n <= t:
        return "After-ACCEPT (TIGHTNESS first)", ACCEPT_OPS + (
            f"; the stronger {above[0]} still open: {above[1]} beside TIGHTNESS" if n > 1 else "")
    stall = f"the After-STALL operators (frontier-method.md sec. 10) to the open target R{t}"
    if best:
        return (f"After-STALL on the open target R{t}, then After-ACCEPT on {best}",
                f"{stall} first (the {above[0]} open), then to the accepted {best} {ACCEPT_OPS}")
    return "After-STALL", f"{stall} (no rung was accepted)"


def continuation_renew_assignment(st, run, c, std):
    """program.md sec. 2.1: the RENEW on the delivered result of a focused run converted to program mode."""
    Q = st["questions"]
    qid = c.get("question")
    q = Q.get(qid or "", {})
    best, cid = best_rung(st, qid) if qid in Q else (None, None)
    what = f"{qid or '-'} {q.get('status', '-')}" + (f"@{best}" if best else "") + (f" ({cid})" if cid else "")
    carried = carried_lines(st, run, skip=qid)
    lane = ([f"- questions/{qid}.md (the delivered question)"] if qid and is_file(Path(run) / "questions" / f"{qid}.md")
            else []) + [x for x in existing(run, *(f"lanes/{qid}/{n}" for n in ("statement.md", "record.md") if qid))
                        if not any(line.startswith(x + " (") for line in carried)]
    return ([f"Request: RENEW on the delivered result {what} (continuation from focused delivery, program.md sec. 2.1): "
             f"apply {continuation_ops(run, st, qid)[1]}; at most 3 successors, each as new/N#-card.md and "
             "new/N#-statement.md. They go to SELECT by path as its first candidates (not registered now); SELECT "
             "handles pending events.", GRID_LINE, "Inputs (open by path):"]
            + lane + carried + reports_lines(run) + ["- ledger.md"] + frontier_lines(run)
            + ["- contract.md"] + follow_up_lines(run, st, c["seq"])
            + [std, "Return: renew.md, the new/ files and result.md with the investigator fields."])


def new_cards(run, tid):
    """The N#-card.md files a SELECT or RENEW task wrote in its new/ directory."""
    return sorted(p.name for p in xp(Path(run) / "tasks" / tid / "new").glob("N*-card.md"))


def continuation_select_lines(st, run):
    """The continuation SELECT's first inputs: the continuation RENEW's successors and what the focused run carried."""
    out = []
    for k in continuation_tasks(st, "investigator", "RENEW"):
        if st["tasks"][k]["status"] in FINISHED:
            out += ([f"- tasks/{k}/new/ (RENEW {k}: successors of the delivered result; the first candidates)"]
                    if new_cards(run, k) else [f"- (RENEW {k} returned no successor cards)"])
            out += existing(run, f"tasks/{k}/renew.md")
    return out + carried_lines(st, run)


def reports_lines(run, label=""):
    """'- reports/<name><label>' for each delivered report (reports/*.md)."""
    rd = xp(Path(run) / "reports")
    return [f"- reports/{p.name}{label}" for p in sorted(rd.glob("*.md"))] if rd.is_dir() else []


def continuation_propose_lines(st, run, c):
    """A PROPOSE packet during the continuation opening: the delivered result and the continuation RENEW's output."""
    qid = c.get("question") or ""
    return (existing(run, f"lanes/{qid}/statement.md") if qid else []) + reports_lines(run, " (delivered)") \
        + ["- contract.md"] + [f"- tasks/{k}/renew.md (the continuation RENEW: successors of the delivered result; "
                               "propose beyond them)" for k in continuation_tasks(st, "investigator", "RENEW")
                               if is_file(Path(run) / "tasks" / k / "renew.md")]


def default_assignment(st, run, tid, role, mode, lane, rnd, cands, direction, brief, questions, objection, title=None):
    """B2: inputs by path and what to return, for mechanical roles and modes; None = orchestrator writes it."""
    C, T, Q = st["candidates"], st["tasks"], st["questions"]
    std = "- standing instructions: the last section of this packet"
    lanes = sorted({C[c]["lane"] for c in cands if C[c].get("lane")})
    stmts = [f"- lanes/{q}/statement.md (rung texts)" for q in lanes]
    cited = [f"- {s} (cited)" for s in cited_sources(run, [C[c]["path"] for c in cands])]
    review_never = ("Never open: the record of attempts, the prover's result or notes, briefings, other reviews, "
                    "reports, rankings or rulings, the question card, investigator or skeptic rationale.")
    if role == "verifier" and mode in REVIEW_MODES and cands:
        what = {"INDIVIDUAL": "INDIVIDUAL review (line by line)",
                "CROSS-DRAFT": "CROSS-DRAFT review of the whole cohort (a verdict per draft, ranking, shared failing step)",
                "SECOND-INDEPENDENT": "SECOND-INDEPENDENT review (single-draft round: break-it angle)",
                "SALVAGE": "SALVAGE review of a gap draft (skip the declared gaps and the assembly, fully check each "
                           "lemma marked proved, list CONFIRMED_STEPS; the verdict never accepts)"}[mode]
        return ([f"Request: {what} of {', '.join(cands)}.", "Inputs (open by path):"]
                + [x for c in cands for x in [f"- candidates/{c}.md (frozen; claims {C[c].get('claims') or '-'})"]
                   + [f"- {a['path']} (attachment of {c}, frozen)" for a in C[c].get("attachments") or []]]
                + stmts + ["- frontier/model.md"] + dep_lines(st, cands) + cited + [std, review_never,
                "Return: review.md and result.md with the verifier header: one `review Cxxx:` line per candidate; "
                "objection numbers unique across the whole review."])
    if role == "verifier" and mode == "ISOLATED" and cands:
        tr = [c for c in cands if C[c]["kind"] == "transfer"]
        what = ("the transfer verdict or edge argument against the original proof steps" if len(tr) == len(cands)
                else "whether each item stands alone under its stated hypotheses and model" if not tr
                else "for each transfer, its verdict or edge argument against the original proof steps; for each "
                     "other item, whether it stands alone under its stated hypotheses and model")
        kind = {c: "fragment" if C[c]["kind"] == "lemma" and C[c].get("from") else C[c]["kind"] for c in cands}
        return ([f"Request: ISOLATED check of {', '.join(cands)}: {what}.", "Inputs (open by path):"]
                + [f"- candidates/{c}.md ({kind[c]})" for c in cands] + ["- frontier/model.md"] + dep_lines(st, cands)
                + cited + [std, "Never open: any other candidate, review, report, record or result file.",
                           "Return: review.md and result.md with the verifier header (scope: ISOLATED): one "
                           "`review Cxxx:` line per candidate; objection numbers unique across the whole review."])
    if role == "verifier" and mode == "ADJUDICATE" and objection:
        cid = objection_cand(st, objection, cands)
        o = next(o for r in st["reviews"] if r["cand"] == cid for o in r["objections"] if o["id"] == objection)
        q = C[cid].get("lane")
        return ([f"Request: ADJUDICATE objection {objection} on {cid}: rule UPHELD or REJECTED, with reasons.",
                 "Inputs (open by path):", f"- candidates/{cid}.md",
                 f"- the objection, copied from state: {objection.split('.')[1]} {o['severity']}: {o['text']}"]
                + (rebuttal_lines(run, st, cid, objection) or ["- the prover's rebuttal: none recorded (add its path with --extra)"])
                + ([f"- lanes/{q}/statement.md"] if q else [])
                + [f"- {s} (cited)" for s in cited_sources(run, [C[cid]["path"]])] + [std,
                   "Never open: other objections, reviews or rulings, the record of attempts.",
                   f"Return: review.md and result.md with `ruling {objection}: UPHELD | REJECTED`."])
    if role == "verifier" and mode == "PAPER" and cands:
        ms = [c for c in cands if C[c]["kind"] == "manuscript"]
        sel = [c for c in cands if c not in ms]
        sl = sorted({C[c]["lane"] for c in sel if C[c].get("lane")})
        return ([f"Request: PAPER review of {', '.join(ms) or 'the manuscript'} against the accepted candidates "
                 "and statements (phase 1), then its history claims against the records (phase 2).",
                 "Inputs, phase 1 (open by path):"] + [f"- candidates/{c}.md (manuscript)" for c in ms]
                + [f"- tasks/{C[c]['author']}/trace.md: only its '## Expansions' table in phase 1" for c in ms]
                + [f"- candidates/{c}.md (accepted; claims {C[c].get('claims') or '-'})" for c in sel]
                + [f"- lanes/{q}/statement.md" for q in sl] + ["- frontier/model.md", std,
                   "Phase 2 only, after the phase-1 review is saved:"]
                + [f"- tasks/{C[c]['author']}/trace.md (the rest)" for c in ms] + [f"- lanes/{q}/record.md" for q in sl]
                + ["- ledger.md", "Return: review.md (phase 1, then phase 2) and result.md with the verifier header."])
    if role == "summarizer" and direction and lane:
        return [f"Request: one briefing for the prover of {direction}.", "Inputs (open by path):",
                f"- direction: {direction}", f"- lanes/{lane}/statement.md", f"- lanes/{lane}/record.md (record of attempts)",
                "- ledger.md", "- scout/ (filed tables; read what the record or the statement cites)", std,
                "Never open: the question card.", "Return: briefing.md and result.md."]
    if role == "prover" and direction and lane:
        ins = [f"- direction: {direction}"]
        if brief:
            ins.append(f"- tasks/{brief}/briefing.md (your briefing; read it first)")
        ins += [f"- lanes/{lane}/statement.md (the exact problem; it wins over the briefing)",
                "- ledger.md (usable premises: active entries only)", "- sources/ (source cards, by the paths cited)",
                "- scout/ (filed tables: cite them instead of recomputing)"]
        if direction.startswith("REPAIR "):
            ins.append(f"- candidates/{direction.split()[1]}.md (the draft to repair)")
        return [f"Request: {direction}.", "Inputs (open by path):"] + ins + [std,
                "Return: draft.md (lemma DAG; add '## Obstacle to the assigned target' whenever you claim less than "
                "the direction's target), notes.md, and result.md with the prover header."]
    if role == "scout" and mode in ("SANITY", "WITNESS") and cands:
        ass = [x for c in cands for x in cand_assumes(st, c)]
        objs = {c: object_copy(run, tid, st, c) for c in cands}
        return ([f"Request: {mode} check of " + ", ".join(f"{c} ({C[c].get('claims') or '-'})" for c in cands) + ".",
                 "Inputs (open by path):"]
                + [f"- {objs[c]} (the claim and the protocol or witness object of {c}, copied from it; not the proof)"
                   if objs[c] else f"- candidates/{c}.md (read only the claim and the protocol or witness object, not the proof)"
                   for c in cands] + stmts + ["- frontier/model.md", std]
                + (["Domain: only instances that meet the candidate's assumptions: " + "; ".join(dict.fromkeys(ass))] if ass else [])
                + ["Never open: the record of attempts, reviews, reports, prover notes or briefings.",
                   "Return: result.md with `check Cxxx: outcome=...; exact=...` per candidate and "
                   "`blocking Cxxx: O<n> CRITICAL: ...` per contradiction; code and tables in this directory."])
    if role == "ledger-auditor" and lane and rnd:
        ks = cohort(st, lane, rnd)
        reps = list(dict.fromkeys(r["report"] for r in st["reviews"] if r["cand"] in ks and r.get("report")))
        return ([f"Request: audit lane {lane} round {rnd}: each confirmed step becomes a self-contained fragment; "
                 "each verifier-confirmed counterexample to a step becomes a dead-end fragment (its statement is the "
                 "negation).", "Inputs (open by path):"] + [f"- {p} (review report)" for p in reps]
                + [f"- candidates/{k}.md" for k in ks] + ["- ledger.md", std,
                   "Return: the fragment files, provenance.md and result.md with the ledger-auditor fields."])
    if role == "process-advisor":
        prev, log = last_advisor_log(run, st, exclude=tid)
        last = T[prev]["created_seq"] if prev else 0
        reps = list(dict.fromkeys(r["report"] for r in st["reviews"] if r["seq"] > last and r.get("report")))
        wide, wide_rule = [], []
        if "run-wide" in (title or "").lower():  # K41: results since the previous advisor; standing rules only
            seq, before = last_advisor(st, exclude=tid)
            done = [k for k in finished_since(st, seq, exclude_role="process-advisor")
                    if is_file(Path(run) / "tasks" / k / "result.md")]
            since = f"advisor {before}" if before else "the run start"
            wide = ([f"- tasks/{k}/result.md ({T[k]['role']}" + (f" {T[k]['mode']}" if T[k].get("mode") else "") + ")"
                     for k in done] if len(done) <= 10 else
                    [f"- tasks/<T>/result.md for T in {id_ranges(done)} ({len(done)} tasks finished since {since})"])
            wide_rule = ["Run-wide: standing instructions only; allocation_advice: none unless a lane round closed."]
        return ([f"Request: review how the run works since {'advisor task ' + prev if prev else 'the run start'}; "
                 "rewrite instructions.md if a rule changes; give allocation advice per lane.", "Inputs (open by path):"]
                + [f"- lanes/{q}/record.md" for q in sorted(Q) if is_file(Path(run) / "lanes" / q / "record.md")]
                + [f"- {p}" for p in reps] + wide + ([f"- {log} (your previous advisor log)"] if prev else [])
                + ["- instructions.md (current revision; do not edit it in place)", f"- tasks/{tid}/status.md (ri.py status output)"]
                + wide_rule + [
                   f"Return: advisor-log.md, result.md with the process-advisor fields, and, if a rule changed, the complete new "
                   f"instructions.md written in tasks/{tid}/ (the orchestrator files it with ri.py ingest)."])
    if role == "investigator" and mode == "RENEW":
        cont = continuation_open(st)
        if cont and not [k for k in continuation_tasks(st, "investigator", "RENEW") if k != tid]:
            return continuation_renew_assignment(st, run, cont, std)
        evs = [e for e in st["events"] if not e.get("handled_by") and e["type"] not in ("queue-low", "breadth-review")]
        prev = latest_task(st, "investigator", "RENEW", exclude=tid)
        since = T[prev]["created_seq"] if prev else 0
        notes = [f"- {t.get('notes') or f'tasks/{k}/notes.md'} (prover {k})" for k, t in sorted(T.items())
                 if t["role"] == "prover" and t.get("created_seq", 0) > since
                 and (t.get("notes") or is_file(Path(run) / "tasks" / k / "notes.md"))]
        skept = [f"- tasks/{k}/result.md (skeptic {t.get('mode') or ''})".replace(" )", ")") for k, t in sorted(T.items())
                 if t["role"] == "skeptic" and t.get("created_seq", 0) > since and t["status"] in FINISHED
                 and is_file(Path(run) / "tasks" / k / "result.md")]
        lit = [f"- tasks/{k}/targeted.md (literature-reviewer TARGETED" + (f" {t['lane']}" if t.get("lane") else "") + ")"
               for k, t in sorted(T.items()) if t["role"] == "literature-reviewer" and t.get("mode") == "TARGETED"
               and t.get("created_seq", 0) > since and t["status"] in FINISHED]
        return ([f"Request: RENEW for {'events ' + ', '.join(e['id'] for e in evs) if evs else 'the run (no pending events)'}: "
                 "successors (new/N#-card.md and new/N#-statement.md in your task directory) and lane decisions.", "Pending events:"]
                + ([f"- {e['id']} {e['type']}" + (f" {e['lane']}" if e.get("lane") else "") + f": {e.get('note') or '-'}"
                    for e in evs] or ["- none"]) + ["Inputs (open by path):"]
                + [f"- lanes/{q}/record.md" for q in sorted({e['lane'] for e in evs if e.get('lane')})]
                + notes + ["- ledger.md"] + frontier_lines(run) + skept + lit
                + follow_up_lines(run, st, last_outer_seq(st, exclude=tid)) + [std,
                   "Return: the new/ files and result.md with the investigator fields."])
    if role == "investigator" and mode == "SELECT":
        since = last_outer_seq(st, exclude=tid)
        cont = continuation_open(st)
        if cont:  # program.md sec. 2.1: the continuation RENEW is no SELECT boundary; its cards come first
            since = min(since, cont["seq"])
        evs, ev_lines = event_lines(st, skip=("breadth-review",))
        k, qs = st.get("k"), ", ".join(f"{q} {x['status']}" for q, x in sorted(Q.items()))
        return (["Request: SELECT (investigator.md Mode SELECT) over the cards below"
                 + (f"; handle events {', '.join(e['id'] for e in evs)}." if evs else ".")
                 + (" Continuation from focused delivery (program.md sec. 2.1): the RENEW's successors of the delivered "
                    "result are the first candidates, TIGHTNESS first." if cont else ""), "Pending events:"] + ev_lines
                + [f"Capacity: K = {k}; active lanes at most {max(2, k // 2)}." if k else
                   "Capacity: K not set; active lanes at most 2.", "Inputs (open by path):"]
                + (continuation_select_lines(st, run) if cont else [])
                + task_file_lines(run, done_tasks(st, "investigator", ("PROPOSE",), since), "cards.md", "PROPOSE")
                + frontier_lines(run)
                + [f"- questions/ (statuses: {cell(qs or 'none', 300)})", "- ledger.md"]
                + existing(run, "sources/bounds.md")
                + task_file_lines(run, done_tasks(st, "literature-reviewer", ("LANDSCAPE",)), "landscape.md", "LANDSCAPE")
                + task_file_lines(run, done_tasks(st, "literature-reviewer", ("TRANSFER-AUDIT",), since), "audit.md",
                                  "TRANSFER-AUDIT")
                + ["- scout/ (filed scout tables)"]
                + task_file_lines(run, done_tasks(st, "investigator", ("BREADTH",))[-1:], "breadth.md", "latest BREADTH")
                + task_file_lines(run, done_tasks(st, "skeptic", since=since) + done_tasks(st, "scout", since=since), "result.md")
                + follow_up_lines(run, st, since) + [std,
                   "Return: select.md, new/N#-card.md and new/N#-statement.md for each card in lanes_to_open, and "
                   "result.md with the investigator fields."])
    if role == "investigator" and mode == "PROPOSE":
        m = re.match(r"\s*lens\s+(\S.*)$", title or "", re.I)
        if not m:
            return None
        cont = continuation_open(st)
        return ([f"Request: PROPOSE with the lens {m.group(1).strip()} (investigator.md Mode PROPOSE).",
                 "Inputs (open by path):"] + frontier_lines(run)
                + (continuation_propose_lines(st, run, cont) if cont else [])
                + task_file_lines(run, done_tasks(st, "literature-reviewer", ("TRANSFER-AUDIT",)), "audit.md",
                                  "TRANSFER-AUDIT")
                + ["- scout/ (filed scout tables)", "- ledger.md"] + existing(run, "sources/bounds.md")
                + task_file_lines(run, done_tasks(st, "literature-reviewer", ("LANDSCAPE",)), "landscape.md", "LANDSCAPE")
                + [f"- questions/{q}.md ({x['status']})" for q, x in sorted(Q.items()) if x["status"] in ("killed", "parked")]
                + [std, "Never open: other proposers' cards.md.", "Return: cards.md and result.md with the investigator fields."])
    if role == "investigator" and mode == "MODEL":
        t = (title or "").lower()
        fq = lane or (min(Q) if Q else "Q01")
        if "apply" in t:
            degen = [(k, x) for k, x in done_tasks(st, "skeptic", ("MODEL-GATE",))
                     if "DEGENERATE" in read(Path(run) / "tasks" / k / "result.md")]
            return (["Request: MODEL, apply gate verdicts (investigator.md MODEL step 7): the DEGENERATE verdicts below; "
                     "edit the full reading.", "Inputs (open by path):"]
                    + task_file_lines(run, degen, "gate.md", "MODEL-GATE: DEGENERATE") + frontier_lines(run) + [std,
                       "Return: reading.md and result.md with the investigator fields."])
        if "focused fast start" in t:
            what = ("M0 and M1 only; keep R1 verbatim and keep its name; add weaker fallbacks R2.. below it, refine D, "
                    "and list stronger variants under 'Stronger (after R1)' (with the converse for the whole class "
                    "when one is plausible, frontier-method.md sec. 10 TIGHTNESS); write the statement in your task "
                    f"directory as new/{fq}-statement.md.")
            ins, ret = [f"- lanes/{fq}/statement.md (the fast-start statement)"], f"new/{fq}-statement.md, reading.md"
        elif "focused" in t:
            what = (f"M0 and M1 only; seed {fq}: the user's problem as target rung Rt; optional stronger rungs R1..Rt-1 "
                    "above it, marked optional (Rt = R1 if there are none); weaker fallbacks below; D with "
                    "'D refutes: Rt'.")
            ins, ret = [], f"questions/{fq}.md and lanes/{fq}/statement.md edited in place, reading.md"
        else:
            what = "M0, M1 and variants, endpoints, lattice, map, transfer rows, and the primary seeds' cards and statements."
            ins, ret = [], "reading.md"
        opening = (st["mode"] == "program" and "focused" not in t and not first_select_done(st)
                   and not converted(st))
        evs = [e for e in st["events"] if opening and not e.get("handled_by") and (  # program.md sec. 7
            e["type"] == "literature-hit" or (e["type"] == "question-verdict" and Q.get(e.get("lane") or "", {})
                                              .get("priority") != "secondary"
                                              and not (e.get("note") or "").startswith("KILL(IMPLIED)")))]
        pend = (["Pending events (apply them: step 8 for seed verdicts; list them in events_handled):"]
                + [f"- {e['id']} {e['type']}" + (f" {e['lane']}" if e.get("lane") else "") + f": {e.get('note') or '-'}"
                   for e in evs] if evs else [])
        return ([f"Request: MODEL ({title or 'opening'}): {what}"] + pend + ["Inputs (open by path):"]
                + model_inputs(st, run) + ins
                + [std, "Opening budget: investigator.md MODEL.",
                   f"Return: {ret}, and result.md with the investigator fields (tasks_requested ranked)."])
    if role == "skeptic" and mode == "QUESTION-GATE" and questions:
        return ([f"Request: QUESTION-GATE of {', '.join(questions)}: one verdict per question, with plausibility.",
                 "Inputs (open by path):"] + question_gate_inputs(st, run, tid, questions)
                + ["- frontier/model.md", "- frontier/map.md", "- frontier/transfer.md"] + patches_line(run)
                + ["- ledger.md", "- contract.md (\"From your notes\")", std,
                   "Return: gate.md and result.md with the skeptic fields."])
    if role == "skeptic" and mode == "MODEL-GATE":
        models = list(dict.fromkeys(norm_model(x) for x in re.findall(r"\bM\d+\b", title or "")))
        what = ", ".join(models) or "the models in frontier/model.md without a MODEL-GATE line"
        qs = ([f"Request: QUESTION-GATE of {', '.join(questions)}: one verdict per question, with plausibility."]
              if questions else [])
        return ([f"Request: MODEL-GATE of {what}: one verdict per model."] + qs + ["Inputs (open by path):", "- frontier/model.md"]
                + existing(run, *[f"frontier/patches/{x}.md" for x in models]) + patches_line(run)
                + ["- contract.md (the key difference)"] + m0_card_lines(run)
                + (question_gate_inputs(st, run, tid, questions) + ["- frontier/map.md", "- frontier/transfer.md", "- ledger.md"]
                   if questions else []) + [std,
                   "Return: gate.md (with patch-<Mx>.md or degenerate-<Mx>.md where a verdict needs one) and result.md "
                   "with the skeptic fields."])
    if role == "literature-reviewer" and mode in ("SURVEY", "LANDSCAPE", "TRANSFER-AUDIT"):
        rows = {r["id"]: r for r in index_rows(run)}
        named = [s for s in source_ids(title) if s in rows]
        model = ["- frontier/model.md"] if m0_filled(run) else []
        if mode == "SURVEY":
            focused = st["mode"] == "focused"
            return (["Request: SURVEY of one source family: a card per source and bounds.md rows (literature-reviewer.md "
                     "Mode SURVEY).", "Inputs (open by path):", "- contract.md",
                     "- sources/index.md (only the rows this Assignment names)"]
                    + [f"- {rows[s]['path']} ({s})" for s in named] + model + [std]
                    + (["Settles check: yes (the claim in contract.md's Objective)."] if focused else [])
                    + ["Return: the source cards, bounds.md and result.md with the literature-reviewer fields."])
        if mode == "LANDSCAPE":
            return (["Request: LANDSCAPE: prior work on the task with X under every alias (literature-reviewer.md Mode "
                     "LANDSCAPE).", "Inputs (open by path):", "- contract.md", "- sources/index.md"]
                    + [f"- {r['path']} (user-notes {s})" for s, r in rows.items() if r["type"] == "user-notes"] + model
                    + [std, "Return: landscape.md, the NEW- cards, bounds.md and result.md with the literature-reviewer fields."])
        if not title:
            return None
        return ([f"Request: TRANSFER-AUDIT of {title} (literature-reviewer.md Mode TRANSFER-AUDIT).", "Inputs (open by path):"]
                + [x for s in named for x in existing(run, f"sources/{s}.md") + [f"- {rows[s]['path']} ({s})"]]
                + ["- frontier/model.md"] + patches_line(run)
                + ["- contract.md", std, "Return: audit.md, one transfer-<model>.md per model and result.md with the "
                                         "literature-reviewer fields."])
    if role == "scout" and mode == "EXPLORE":
        if (title or "").upper().startswith("ANCHOR"):
            rows = {r["id"]: r for r in index_rows(run)}
            src = [f"- {rows[s]['path']} (the baseline source file, {s})" if s in rows else
                   f"- the baseline source file of {s} (sources/index.md)" for s in source_ids(title)]
            return ([f"Request: {title}: the baseline at k = 0 only (scout.md Mode EXPLORE, opening variant ANCHOR).",
                     "Inputs (open by path):"] + (src or ["- the baseline source file named in this Assignment"])
                    + [std, "Return: setup.md, table.md and result.md with the scout fields."])
        return ([f"Request: EXPLORE {title or 'the cell named below'}: exact small-case values (scout.md Mode EXPLORE); "
                 "the grid given below, else the smallest nontrivial parameters.", "Inputs (open by path):",
                 "- frontier/model.md", "- frontier/map.md", std, "Return: setup.md, table.md and result.md with the scout fields."])
    if role == "writer" and cands:
        clos = dep_closure(st, cands)
        closc = [st["ledger"][d]["cand"] for d in clos if st["ledger"][d]["cand"] in C]
        revs = [r for c in cands + closc for r in reviews_of(st, c)
                if r["scope"] in GATE_SCOPES and r["sha256"] == C[c]["sha256"] and r.get("report")]
        return ([f"Request: manuscript of {', '.join(cands)}; no comparator ran: take the selection, MINOR fills and "
                 "assurance facts from the candidate, its dependency closure and its gate reviews (writer.md Inputs).",
                 "Inputs (open by path):"]
                + [f"- candidates/{c}.md ({C[c]['status']}; claims {C[c].get('claims') or '-'})" for c in cands]
                + [f"- candidates/{c}/ (its attachments)" for c in cands if xp(Path(run) / "candidates" / c).is_dir()]
                + [f"- candidates/{st['ledger'][d]['cand']}.md (ledger entry {d})" for d in clos]
                + list(dict.fromkeys(f"- {r['report']} ({r['scope']} review of {r['cand']})" for r in revs))
                + stmts + ["- frontier/model.md", "- contract.md"]
                + [f"- {s} (cited)" for s in cited_sources(run, [C[c]["path"] for c in cands + closc])]
                + [std, "Word budget: framing about 800 words (writer.md); in all, about the presented candidates' "
                        "length plus 1,200 words.",
                   "Return: manuscript.md, trace.md (with its '## Expansions' table), gaps.md if needed, and result.md "
                   "with the writer fields."])
    return None


# Exact forbidden paths only (never substrings such as advice-notes.md); '/' or '\' separators.
QUESTION_CARD = r"(?<![\w-])questions[/\\]Q\d+\.md(?![\w-])"
NEVER_GATE = (r"(?<![\w-])tasks[/\\]T\d+[/\\](?:result|report|review|briefing|notes)\.md(?![\w-])",
              r"(?<![\w-])lanes[/\\]Q\d+[/\\]record\.md(?![\w-])", QUESTION_CARD,
              r"(?:^|(?<=[\s\"'`/\\]))(?:record|notes)\.md(?![\w-])")


CAND_PATH = re.compile(r"(?<![\w-])candidates[/\\](C\d+)(?:\.md|[/\\])", re.I)
TASK_DIR = re.compile(r"(?<![\w-])(tasks|scout)[/\\](T\d+)(?![\w-])", re.I)


def gate_exposure(st, role, cands, text):
    """K42, K77: (path, why) of the first gate input text names that the never-include list forbids beyond
    NEVER_GATE: another cohort candidate's file or attachments, a prover's task directory, and, for a
    verifier, the output of a scout SANITY or WITNESS check on one of the candidates. None if clean."""
    C, T, L = st["candidates"], st["tasks"], st["ledger"]
    deps = {L[d]["cand"] for c in cands for d in C[c].get("deps") or [] if d in L}
    group = {k for c in cands if C[c].get("lane") and C[c].get("round") for k in cohort(st, C[c]["lane"], C[c]["round"])}
    for m in CAND_PATH.finditer(text or ""):
        k = fmt_id("C", int(m.group(1)[1:]))
        if k in group and k not in cands and k not in deps:
            return m.group(0), f"another cohort candidate, {k}"
    for m in TASK_DIR.finditer(text or ""):
        t = T.get(fmt_id("T", int(m.group(2)[1:]))) or {}
        if t.get("role") == "prover" and m.group(1).lower() == "tasks":
            return m.group(0), "a prover's task directory"
        if (role == "verifier" and t.get("role") == "scout" and t.get("mode") in ("SANITY", "WITNESS")
                and set(t.get("cands") or []) & set(cands)):
            return m.group(0), "a scout check's output on the same candidate"
    return None


def never_include(st, role, mode, cands, text):
    """B2: refuse orchestrator-written text that names an input verification.md §2 forbids."""
    pats = []
    gate = (role == "verifier" and mode in REVIEW_MODES + ("ISOLATED",)) or (role == "scout" and mode in ("SANITY", "WITNESS"))
    if gate:
        pats += list(NEVER_GATE)
    if role == "summarizer":
        pats.append(QUESTION_CARD)
    if role == "verifier" and mode == "ISOLATED":
        pats += [r"\b" + c + r"\b" for c in {st["candidates"][x].get("from") for x in cands} if c]
    for p in pats:
        m = re.search(p, text or "", re.I)
        if m:
            fail(f"never-include (verification.md sec. 2): a {role} {mode or ''} packet must not name {m.group(0)!r}".replace("  ", " "))
    hit = gate_exposure(st, role, cands, text) if gate else None
    if hit:
        fail(f"never-include (verification.md sec. 2): a {role} {mode} packet must not name {hit[0]!r} ({hit[1]})")


CITATION_RES = (("arXiv ID", re.compile(r"\b\d{4}\.\d{4,5}(?:v\d+)?\b")),
                ("DOI", re.compile(r"\b10\.\d{4,9}/[^\s)]+")),
                ("author-year", re.compile(r"\b(?P<name>[A-Z][A-Za-z-]+)(?: et al\.| and [A-Z][A-Za-z-]+)?,? "
                                           r"\(?(?P<year>(?:19|20)\d{2})(?!\.?\d)\)?")))  # not inside 1907.01234
STEERING_RE = re.compile(r"\b(likely|unlikely|promising|probably|expected?|should be easy|do not pretend)\b", re.I)


def lint_assignment(run, role, mode, text):
    """I1 lint of hand-written Assignment text (warn only, never refuses): citation-like tokens found in no
    sources/index.md row or sources/S*.md card, and steering words. Returns the warning lines."""
    if not (text or "").strip():
        return []
    files = [read(Path(run) / "sources" / "index.md").lower()] + [read(Path(run) / p).lower() for p in source_cards(run)]
    out = []
    for kind, rx in CITATION_RES:
        for m in rx.finditer(text):
            tok = m.group(0).rstrip(".,;:")
            keys = ([m.group("name").lower(), m.group("year")] if kind == "author-year"
                    else [re.sub(r"v\d+$", "", tok).lower()])
            if not any(all(k in f for k in keys) for f in files):
                out.append(f"warning (I1): {kind} {tok!r} is in no sources/ card or index row; an Assignment carries IDs, "
                           "paths and verbatim user or worker text only")
    out += [f"warning (I1): steering word {m.group(0)!r}; an Assignment carries no opinion about the outcome"
            for m in STEERING_RE.finditer(text)]
    return list(dict.fromkeys(out))


def role_minutes(role, mode=None):
    """Minutes of work in a packet's Time line (state.md sec. 5)."""
    if role in LONG_MODES:
        return 60 if mode in LONG_MODES[role] else 45
    return ROLE_MINUTES.get(role, 45)


def time_line(role, mode=None):
    if role == "scout":
        return SCOUT_TIME
    return f"Time: return within about {role_minutes(role, mode)} minutes of work; save partial work first (status partial)."


def compose_assignment(body, extra, role, mode=None):
    """Body lines + extra lines, ending with 'Stop condition: ...' (the default unless the body has one).
    Extra lines go right after the first Inputs list when the body has one (they are usually inputs by
    path), else just before the stop condition. Without a line starting 'Return', RETURN_DEFAULT is
    added just before the stop condition; then, without a 'Time:' line, the role's Time line (K16)."""
    lines = body.rstrip("\n").split("\n") if isinstance(body, str) else list(body)
    h = next((n for n, x in enumerate(lines) if re.match(r"\s*Inputs\b[^:]*:\s*$", x)), None)
    if h is not None and extra:
        j = h + 1
        while j < len(lines) and lines[j].lstrip().startswith("- "):
            j += 1
        lines, extra = lines[:j] + extra + lines[j:], []
    if not any(re.match(r"\s*Return\b", x) for x in lines + extra):
        extra = extra + [RETURN_DEFAULT]
    if not any(re.match(r"\s*Time\s*:", x, re.I) for x in lines + extra):
        extra = extra + [time_line(role, mode)]
    i = next((n for n, x in enumerate(lines) if re.match(r"\s*Stop condition\s*:", x, re.I)), None)
    if i is None:
        return "\n".join(lines + extra + [f"Stop condition: {STOP_DEFAULT[role]}."])
    return "\n".join(lines[:i] + extra + lines[i:])


def packet_assignment(run, t):
    m = re.search(r"\n## Assignment\n\n(.*?)\n\n## Role instructions\n", read(Path(run) / t["packet"]), re.S)
    return m.group(1).strip() if m else PLACEHOLDER


def default_title(role, mode, direction, cands, questions, objection):
    if direction:
        return f"brief {direction}" if role == "summarizer" else direction
    if objection:
        return f"ADJUDICATE {objection}"
    if questions:
        return f"{mode or role} {', '.join(questions)}"
    if cands:
        return f"{mode or role} {', '.join(cands)}"
    return None


# ---------------------------------------------------------------- commands: tasks

def build_packet(run, st, tid, role, mode, lane, rnd, title, assignment):
    """Compose packet.md per the worker envelope (header, assignment, prompts, rules)."""
    sk = skill_dir()
    role_p, env_p = sk / "prompts" / f"{role}.md", sk / "prompts" / "_envelope.md"
    for p in (role_p, env_p):
        if not is_file(p):
            fail(f"missing prompt file {p} (skill dir {sk}; set RI_SKILL_DIR if the skill lives elsewhere)")
    ip = Path(run) / "instructions.md"
    rev, rules = parse_instructions(read(ip)) if is_file(ip) else (0, [])
    if rev > 0 and not rules:
        print(f"note: instructions.md is at revision {rev} but has no parseable rules ('## SI<nn>' blocks "
              "with applies:, review-safe: and text: lines); packets get none", file=sys.stderr)
    review = role in ("verifier", "skeptic")
    chosen = [r["text"] for r in rules if rule_applies(r, role, mode) and (r["review_safe"] or not review)]
    head = [f"# Task {tid} — {role}" + (f" ({mode})" if mode else ""),
            f"Run: {apath(run)}        Skill: {sk}"]
    if lane:
        head.append(f"Lane: {lane}   Round: {rnd}   Direction/target: {title or '-'}")
    elif title:
        head.append(f"Target: {title}")
    head.append(f"Output directory (write only here): tasks/{tid}/ (relative to Run)")
    si = "\n".join(chosen) or "(none apply)"
    if review:
        si = "(review packet: only rules marked review-safe are included)\n\n" + si
    return ("\n".join(head) + f"\n\n## Assignment\n\n{assignment.strip()}\n\n## Role instructions\n\n"
            + xp(role_p).read_text(encoding="utf-8").strip() + "\n\n---\n\n"
            + xp(env_p).read_text(encoding="utf-8").strip()
            + f"\n\n## Standing instructions (revision {rev})\n\n{si}\n")


def refuse_on_control(run, what):
    flags = control_flags(run)
    for name in ("STOP", "PAUSE"):
        if flags[name]:
            fail(f"{name} in force ({flag_desc(flags[name][0])}): {what} refused. Only the user lifts it "
                 "(resume RUN for PAUSE; resume RUN --stop --reason-file <file> for STOP)")


def refuse_batched_review(st, mode, cands):
    """K61: result reviews are never batched: INDIVIDUAL, SALVAGE and SECOND-INDEPENDENT take one candidate,
    and a CROSS-DRAFT covers one lane round's cohort."""
    if mode in ("INDIVIDUAL", "SALVAGE", "SECOND-INDEPENDENT") and len(cands) > 1:
        fail(f"{mode} takes one candidate per task (result reviews are never batched, program.md sec. 5.2): "
             f"one task each for {', '.join(cands)}")
    rounds = sorted({(st["candidates"][c].get("lane") or "-", st["candidates"][c].get("round") or 0) for c in cands})
    if mode == "CROSS-DRAFT" and len(rounds) > 1:
        fail(f"a CROSS-DRAFT covers one lane round's cohort (program.md sec. 5.2); {', '.join(cands)} span "
             + ", ".join(f"{q} r{r}" for q, r in rounds))


def gap_step_missing(run, st, qid):
    """K12: a successor card (parent or operator) or a card added after the first finished SELECT whose
    'gap step:' is empty or still the template placeholder."""
    q = st["questions"][qid]
    sel = [t.get("created_seq", 0) for t in st["tasks"].values()
           if t["role"] == "investigator" and t.get("mode") == "SELECT" and t["status"] in FINISHED]
    if not (q.get("parent") or q.get("operator") or (sel and q.get("created_seq", 0) > min(sel))):
        return False
    m = re.search(r"(?im)\bgap step\s*:[ \t]*(.*)$", read(Path(run) / "questions" / f"{qid}.md"))
    val = m.group(1).strip() if m else ""
    return not val or val.startswith("<")


def cmd_task_new(a):
    run, st = open_run(a)
    refuse_on_control(run, "new dispatch")
    T, C = st["tasks"], st["candidates"]
    old, oid = None, None
    if a.redo:
        oid = get(st, "tasks", "T", a.redo)
        old = T[oid]
        if old.get("superseded_by"):
            fail(f"{oid} is already superseded by {old['superseded_by']}")
        if old["status"] == "done":
            fail(f"{oid} is done; nothing to redo")
        if is_file(run / "tasks" / oid / "result.md") and old["status"] not in ("partial", "blocked"):
            fail(f"tasks/{oid}/result.md exists: ingest it first (ri.py ingest RUN {oid})")
    o = old or {}
    role = a.role or o.get("role")
    if not role:
        usage("task new needs --role (or --redo Txxx)")
    mode = a.mode.upper() if a.mode else o.get("mode")
    if role == "scout" and mode == "ANCHOR":
        usage('the scout ANCHOR is the EXPLORE opening variant: --mode EXPLORE --title "ANCHOR <source>"')
    if mode and role in MODES and mode not in MODES[role]:
        usage(f"mode {mode} is not valid for {role}; use one of {', '.join(MODES[role])}")
    light = a.light or bool(o.get("light"))
    questions = [get(st, "questions", "Q", x) for x in split_list(a.question)] if a.question else list(o.get("questions") or [])
    if light and not (role == "skeptic" and (mode == "QUESTION-GATE" or (mode == "MODEL-GATE" and questions))):
        usage("--light is only for a skeptic QUESTION-GATE, or a MODEL-GATE with --question")
    cands = [get(st, "candidates", "C", x) for x in split_list(a.cand)] if a.cand else list(o.get("cands") or [])
    direction = norm_direction(a.direction) if a.direction else o.get("direction")
    brief = get(st, "tasks", "T", a.brief) if a.brief else o.get("brief")
    bare = [q for q in questions if not has_r1(run, q)] if role == "skeptic" and mode in ("QUESTION-GATE", "MODEL-GATE") else []
    if bare:  # K14: a QUESTION-GATE needs an exact R1 (card R1 line or statement Goal line)
        fail(f"{', '.join(bare)} {'has' if len(bare) == 1 else 'have'} no R1 yet: MODEL step 8 or RENEW writes it "
             "first (a filled 'R1:' line in the card, or 'Goal. Prove or disprove:' line in lanes/Qxx/statement.md)")
    objection = norm_objection(a.objection) if a.objection else o.get("objection")
    if objection:
        cands = [objection_cand(st, objection, cands)]
    if role == "verifier":
        refuse_batched_review(st, mode, cands)
    lane = get(st, "questions", "Q", a.lane) if a.lane else o.get("lane")
    rnd = a.round if a.round is not None else o.get("round")
    target = direction_target(st, direction)
    if not lane and target and re.fullmatch(r"Q\d+\.(R\d+|D)", target):
        lane = get(st, "questions", "Q", target.split(".")[0])
    if not lane and cands and len({C[c].get("lane") for c in cands}) == 1:
        lane = C[cands[0]].get("lane")
        if rnd is None and len({C[c].get("round") for c in cands}) == 1:
            rnd = C[cands[0]].get("round")
    if rnd is None and lane:
        rnd = st["questions"][lane]["round"]
    title = a.title or (f"redo of {oid}" + (f": {o['title']}" if o.get("title") else "") if old else
                        default_title(role, mode, direction, cands, questions, objection))
    extra = list(a.extra or [])
    if a.extra_file:
        extra += xp(find_input(run, a.extra_file)).read_text(encoding="utf-8-sig").rstrip().split("\n")
    tid = next_id(st, "T")  # not saved unless commit() runs
    hand = "\n".join(extra)  # hand-written text, linted for I1 (never the defaults)
    if a.assignment_file:
        body = xp(find_input(run, a.assignment_file)).read_text(encoding="utf-8-sig")
        never_include(st, role, mode, cands, body)
        hand = body + "\n" + hand
    elif old:
        body = packet_assignment(run, old)
    else:
        body = default_assignment(st, run, tid, role, mode, lane, rnd, cands, direction, brief, questions, objection,
                                  title=title)
        if body is None:
            body, extra = (extra, []) if extra else ([PLACEHOLDER], [])
            never_include(st, role, mode, cands, "\n".join(body))
    text = body if isinstance(body, str) else "\n".join(body)
    have = "\n".join([text] + extra)
    extra += [x for x in patch_inputs(st, run, role, mode, lane, cands) if x.split()[1] not in have]
    lg = LIGHT_GATE if mode == "QUESTION-GATE" else LIGHT_MODEL_GATE.format(", ".join(questions))
    if light and lg not in text:
        extra.append(lg)
    never_include(st, role, mode, cands, "\n".join(extra))
    extra += [x for x in auto_lines(run, st, role, mode) if x.split(":")[0] + ":" not in text + "\n".join(extra)]
    assignment = compose_assignment(body, extra, role, mode)
    if a.start and PLACEHOLDER in assignment and not a.force_empty:
        fail("--start refused: the Assignment is still the placeholder. Write it to a file and pass "
             "--assignment-file (or --extra-file); --force-empty only for recovery")
    packet = build_packet(run, st, tid, role, mode, lane, rnd, direction or title, assignment)
    if role == "process-advisor":
        atomic_write(run / "tasks" / tid / "status.md", "\n".join(build_status(run, st, full=True)) + "\n")
    atomic_write(run / "tasks" / tid / "packet.md", packet)
    pk = apath(run / "tasks" / tid / "packet.md")
    spawn = (f"dispatch: Read {pk} and follow it. Write only in {apath(run / 'tasks' / tid)}{os.sep} "
             "and in the canonical files your packet says your role owns. "
             "When done, reply with only the result.md header.")
    if a.start:  # K33: the log of every message sent to the worker starts with the spawn line
        atomic_write(run / "tasks" / tid / "dispatch.md", spawn + "\n")
    iso = a.isolation or st["isolation_default"]
    T[tid] = {"role": role, "mode": mode, "lane": lane, "round": rnd, "title": title,
              "status": "running" if a.start else "queued",
              "context": (a.context or tid) if a.start else a.context, "isolation": iso,
              "packet": f"tasks/{tid}/packet.md", "created_seq": st["seq"] + 1, "cands": cands,
              "direction": direction, "brief": brief, "questions": questions, "objection": objection,
              "light": light, "redo_of": oid, "note": None}
    if old:
        old.update(status="superseded", superseded_by=tid)
    if role == "writer" and cands:  # K43: with no comparator, the writer's candidates are the presented ones
        st["selected"] = list(dict.fromkeys((st.get("selected") or []) + cands))
    commit(run, st, "task new", {"id": tid, "role": role, "mode": mode, "lane": lane, "round": rnd,
                                 "title": title, "cands": cands, "direction": direction, "redo_of": oid,
                                 "light": light, "start": a.start, "context": T[tid]["context"], "isolation": iso})
    print(f"{tid}  {pk}" + (f"  (supersedes {oid})" if oid else ""))
    if (role, mode) == ("investigator", "BREADTH") and not old and not any(
            e["type"] == "breadth-review" and not e.get("handled_by") for e in st["events"]):
        print("note: BREADTH is scheduled by the breadth-review event (program.md §7), before an exhaustion claim, "
              "or on a user request", file=sys.stderr)
    if role == "skeptic" and mode == "QUESTION-GATE":
        for qid in questions:
            if gap_step_missing(run, st, qid):
                print(f"note: {qid} has no gap step (FM §5); the skeptic tests it first; ask the next SELECT or "
                      "RENEW to fill it", file=sys.stderr)
    if a.start:
        print(f"running  context {T[tid]['context']}  isolation {iso}")
        print(spawn)
    for w in lint_assignment(run, role, mode, hand):
        print(w, file=sys.stderr)


def cmd_task_set(a):
    run, st = open_run(a)
    toks, status = list(a.ids), a.status
    if len(toks) > 1 and toks[-1].lower() in TASK_STATUSES:
        pos = toks.pop().lower()
        if status and status.lower() != pos:
            usage("conflicting status values")
        status = pos
    status = status.lower() if status else None
    tids = [get(st, "tasks", "T", x) for x in toks]
    if status and status not in TASK_STATUSES:
        usage(f"status must be one of {', '.join(TASK_STATUSES)}")
    if status == "superseded":
        usage("superseded is set by 'task new --redo'")
    note = text_arg(a, "note", run)
    if not any((status, a.context, a.isolation, note)):
        usage("task set needs a status, --context, --isolation or --note")
    if status == "withdrawn":  # K79: a task that was never spawned
        if not note:
            usage("withdrawn needs --note (why the task was never spawned)")
        for tid in tids:
            t = st["tasks"][tid]
            if t["status"] not in LIVE or is_file(run / "tasks" / tid / "result.md"):
                fail(f"{tid} is {t['status']}" + (" with a result.md" if t["status"] in LIVE else "")
                     + ": only a queued or running task without result.md can be withdrawn")
    if status == "running":
        refuse_on_control(run, "marking a task running")
        for tid in tids:
            if PLACEHOLDER in read(run / st["tasks"][tid]["packet"]) and not a.force_empty:
                fail(f"{tid}: the packet's Assignment is still the placeholder; write it before dispatch "
                     "(--force-empty only for recovery)")
    for tid in tids:
        t = st["tasks"][tid]
        for key, val in (("status", status), ("context", a.context), ("isolation", a.isolation), ("note", note)):
            if val:
                t[key] = val
    commit(run, st, "task set", {"ids": tids, "status": status, "context": a.context,
                                 "isolation": a.isolation, "note": note})
    for tid in tids:
        t = st["tasks"][tid]
        print(f"{tid} {t['status']}  context {t.get('context') or '-'}  isolation {t['isolation']}")
        if status in FINISHED and not is_file(run / "tasks" / tid / "result.md"):
            print(f"note: tasks/{tid}/result.md is missing; save the worker's returned text there", file=sys.stderr)


# ---------------------------------------------------------------- commands: candidates and reviews

def norm_citer(st, text):
    """--for: 'q7' -> 'Q07', 'c5' -> 'C005' (both must exist), 'h1' -> 'H1' (a story.md headline)."""
    m = re.fullmatch(r"([QC])\d+|H(\d+)", (text or "").strip(), re.I)
    if not m:
        usage(f"malformed --for {text!r}: use Qxx, Hn or Cxxx")
    if m.group(2):
        return f"H{int(m.group(2))}"
    return get(st, "questions" if m.group(1).upper() == "Q" else "candidates", m.group(1).upper(), text)


def is_implied(c):
    """A skeptic's KILL(IMPLIED) certificate (implied-Qxx.md): easy by design, so never too-easy."""
    return bool(re.search(r"(?:^|/)implied-Q\d+\.md$", c.get("source") or "", re.I))


FILL_RE = re.compile(r"\s*FILL\s+(O\d+)\s+in\s+(.+?)\s*$")
HEADING_RE = re.compile(r"(#{1,6})\s+(.*?)\s*#*\s*$")


def parse_fills(text):
    """[(objection, heading, text)] from a PAPER review's 'FILL O<n> in <heading>' ... 'END FILL' blocks."""
    out, cur = [], None
    for line in text.splitlines():
        m = FILL_RE.fullmatch(line) if cur is None else None
        if m:
            cur = (m.group(1).upper(), m.group(2), [])
        elif cur is not None and line.strip() == "END FILL":
            out.append((cur[0], cur[1], "\n".join(cur[2]).strip()))
            cur = None
        elif cur is not None:
            cur[2].append(line)
    return out


def heading_key(text):
    return " ".join(text.strip().strip("`'\"").lstrip("#").split()).casefold()


def section_span(lines, heading, prefix=False):
    """(start, end): the lines under the markdown heading named heading (prefix: a heading starting with that
    word), up to the next heading of the same or a higher level; None if there is no such heading."""
    key = heading_key(heading)
    for i, x in enumerate(lines):
        m = HEADING_RE.fullmatch(x)
        k = heading_key(m.group(2)) if m else None
        if k is not None and (re.match(re.escape(key) + r"\b", k) if prefix else k == key):
            end = len(lines)
            for j in range(i + 1, len(lines)):
                n = HEADING_RE.fullmatch(lines[j])
                if n and len(n.group(1)) <= len(m.group(1)):
                    end = j
                    break
            return i + 1, end
    return None


def fills_only(old, new, fills):
    """None when new is old with some fills inserted verbatim (each at most once, whitespace-trimmed), each
    inside the section under its heading; else what else changed."""
    a, b = old.splitlines(), new.splitlines()
    unused = list(fills)
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        if op != "insert":
            return f"{op} at line {i1 + 1} of the parent"
        block = "\n".join(b[j1:j2]).strip()
        if not block:
            continue
        hit = None
        for f in unused:
            span_ = section_span(a, f[1]) if f[2] == block else None
            if span_ and span_[0] <= i1 <= span_[1]:
                hit = f
                break
        if hit is None:
            return f"lines {j1 + 1}-{j2} are not a fill of the review inside its named section"
        unused.remove(hit)
    return None


def minor_paper_review(st, cid):
    """The latest PAPER review of cid with verdict PASS_WITH_MINOR on its current sha256, or None."""
    sha = (st["candidates"].get(cid) or {}).get("sha256")
    revs = [r for r in reviews_of(st, cid) if r["scope"] == "paper" and r["sha256"] == sha
            and effective_verdict(r) == "PASS_WITH_MINOR"]
    return revs[-1] if revs else None


def fill_revision(st, run, cid, new_text):
    """K76: a manuscript revision whose diff only inserts its parent's PAPER fill blocks counts that review
    as its own PAPER pass (c['delta_review']); otherwise it needs a DELTA PAPER review. Message suffix."""
    c = st["candidates"][cid]
    r = minor_paper_review(st, c["revises"])
    if r is None:
        return ""
    fills = parse_fills(read(Path(run) / r["report"])) if r.get("report") else []
    why = (fills_only(read(Path(run) / st["candidates"][c["revises"]]["path"]), new_text, fills) if fills
           else f"the PAPER review by {r['task']} has no FILL blocks")
    if why:
        return f"\nnote: revision changes more than the fills ({why}): dispatch a DELTA PAPER review"
    c["delta_review"] = r["task"]
    return f"  [fills only: {r['task']}'s PAPER review of {c['revises']} counts as its PAPER pass]"


def claims_line(path):
    """The value of the file's first 'claims:' line (a transfer file names its claim there; markdown emphasis
    such as '**claims:**' allowed), or ''."""
    m = re.search(r"(?im)^[\s>*_#-]*claims[*_]*\s*:[*_]*\s*(.+?)\s*$", read(path))
    return m.group(1).strip("`'\" ") if m else ""


def frozen_labels(text, labels=True):
    """K15, K34: what a file being frozen holds that belongs in result.md: a result.md header block (task:,
    role: and status: between '---' lines), a line whose value is only an I5 label (not checked when labels
    is False: a manuscript's template asks for labels), a verdict line. A prover's 'Status: proved | uses
    G<i>' template lines are none of these."""
    out, lines = [], text.splitlines()
    marks = [i for i, x in enumerate(lines) if x.strip() == "---"]
    for a, b in zip(marks, marks[1:]):
        keys = {m.group(1).lower() for x in lines[a + 1:b] for m in [re.match(r"\s*([A-Za-z_]+)\s*:", x)] if m}
        if {"task", "role", "status"} <= keys:
            out.append("a result.md header block")
            break
    if labels and re.search(r"(?im)^\s*(?:[-*]\s+)?[^:\n]{1,40}:\s*\**(?:" + "|".join(I5_LABELS) + r")\**\.?\s*$", text):
        out.append("an I5 label line")
    if re.search(r"(?m)^\s*(?:[-*]\s+)?(?:[A-Za-z][\w -]{0,30}\s*[:=]\s*)?\**(?:PASS(?:_WITH_MINOR)?|FAIL|INCONCLUSIVE|"
                 r"ADVANCE|KILL(?:\([A-Z-]+\))?)\**\.?\s*$", text):
        out.append("a verdict line")
    return out


def do_cand_add(st, run, src_path, author, kind=None, claims=None, lane=None, method=None, deps=(),
                revises=None, from_=None, rnd=None, gap=None, direction=None, step=None,
                allow_pending=False, rebuttals=None, for_=None, attach=()):
    """Freeze a draft as candidates/Cxxx.md (cand add and ingest), with its data files as hashed attachments
    under candidates/Cxxx/ (K42). Returns (cid, message)."""
    names = [Path(p).name for p in attach]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        usage(f"two attachments are named {dup[0]}: rename one (attachments keep their file names)")
    for_ = norm_citer(st, for_) if for_ else None
    if re.fullmatch(r"implied-Q\d+\.md", Path(src_path).name, re.I) and not for_:
        fail("KILL(IMPLIED) facts are certified only for a named citer, program.md sec. 5.3: "
             "add --for Qxx|Hn|Cxxx (the question, headline or candidate that cites it)")
    src = get(st, "candidates", "C", from_) if from_ else None
    kind = kind or ("lemma" if src else "proof")
    if src and kind != "lemma":
        usage("--from is only for --kind lemma (auditor fragments and dead ends)")
    author = get(st, "tasks", "T", author)
    direction = norm_direction(direction) if direction else None
    if direction and direction.startswith("REPAIR ") and not revises:
        revises = direction.split()[1]
    revises = get(st, "candidates", "C", revises) if revises else None
    model = None
    if kind == "transfer":
        claims = (claims or "").strip() or claims_line(src_path)
        if not claims:
            usage("kind transfer needs --claims or a first 'claims:' line in the file (free text, e.g. "
                  "'claims: transfer:S03 Thm 2@M1')")
        at_models = re.findall(r"@\s*M(\d+)\b", claims, re.I)  # K40, K80: the model the transfer row is stated in
        model = f"M{int(at_models[-1])}" if at_models else None
    else:
        claims = norm_claim(claims) if claims else None
    lane = get(st, "questions", "Q", lane) if lane else None
    if kind != "transfer":
        lane = lane or (claims.split(".")[0] if claims else None) or (st["candidates"][src].get("lane") if src else None)
    if lane and lane not in st["questions"]:
        usage(f"unknown question {lane}")
    if kind in RUNG_KINDS + ("counterexample",) and not claims:
        usage(f"--claims Qxx.Ri|Qxx.D is required for kind {kind}")
    if kind == "counterexample" and claims.endswith(".D"):
        usage("a counterexample claims the rung it refutes (Qxx.Rj), never Qxx.D")
    if kind == "lemma" and not src and not lane:
        usage("a lemma without --from needs --lane (it is gated like a proof)")
    if claims and kind != "transfer" and claims.split(".")[0] != lane:
        usage(f"claim {claims} is not in lane {lane}")
    tgt = direction_target(st, direction)
    if tgt and re.fullmatch(r"Q\d+\.(R\d+|D)", tgt) and tgt.split(".")[0] != lane:
        usage(f"direction {direction} is not in lane {lane}")
    deps = [norm_id("L", d) for d in deps]
    bad = [d for d in deps if st["ledger"].get(d, {}).get("status") != "active"]
    if bad and not allow_pending:
        fail(f"dependencies are not active ledger entries: {', '.join(bad)} "
             "(--allow-pending-deps records them anyway; acceptance still requires them active)")
    data = xp(src_path).read_bytes()
    cid = next_id(st, "C")
    dest = Path(run) / "candidates" / f"{cid}.md"
    if exists(dest):
        fail(f"{dest} already exists although state.json does not know {cid}; run 'ri.py check'")
    atomic_write(dest, data)
    marks = frozen_labels(data.decode("utf-8", errors="replace"), labels=kind != "manuscript")
    if marks:
        print(f"warning: candidates/{cid}.md holds {', '.join(marks)}: labels and verdicts belong in result.md "
              "(envelope rule 4); gates ignore them", file=sys.stderr)
    atts = []
    for p, name in zip(attach, names):
        blob = xp(p).read_bytes()
        atomic_write(Path(run) / "candidates" / cid / name, blob)
        atts.append({"path": f"candidates/{cid}/{name}", "sha256": hashlib.sha256(blob).hexdigest()})
    at = st["tasks"][author]
    rnd = rnd if rnd is not None else (
        at.get("round") if at.get("lane") == lane and at.get("round") is not None
        else (st["questions"][lane]["round"] if lane else None))
    digest = hashlib.sha256(data).hexdigest()
    st["candidates"][cid] = {"lane": lane, "claims": claims, "kind": kind, "path": f"candidates/{cid}.md",
                             "sha256": digest, "author": author, "author_context": at.get("context"),
                             "method": method, "deps": deps, "revises": revises, "from": src, "round": rnd,
                             "gap": gap, "direction": direction, "step": step, "rebuttals": list(rebuttals or []),
                             "assumes": None, "status": "proposed", "label": None, "seq": st["seq"] + 1,
                             "source": rel(run, src_path), "for": for_}
    if model:
        st["candidates"][cid]["model"] = model
    if atts:
        st["candidates"][cid]["attachments"] = atts
    msg = (f"{cid} frozen  {claims or kind} ({kind})" + (f"  direction {direction}" if direction else "")
           + f"  round {rnd if rnd is not None else '-'}  sha256 {digest[:12]}"
           + (f"  for {for_}" if for_ else "")
           + (f"  attachments {', '.join(x['path'] for x in atts)}" if atts else "")
           + ("  [gap declared: SALVAGE + CROSS-DRAFT + auditor only]" if gap else "")
           + (f"  [pending deps {', '.join(bad)}]" if bad else ""))
    if kind == "manuscript" and revises:
        msg += fill_revision(st, run, cid, data.decode("utf-8-sig", errors="replace"))
    return cid, msg


def cmd_cand_add(a):
    run, st = open_run(a)
    cid, msg = do_cand_add(st, run, find_input(run, a.file), a.author, kind=a.kind, claims=a.claims, lane=a.lane,
                           method=a.method, deps=split_list(a.deps), revises=a.revises, from_=a.from_, rnd=a.round,
                           gap=a.gap, direction=a.direction, step=a.step, allow_pending=a.allow_pending_deps,
                           for_=a.for_, attach=[find_input(run, x) for x in a.attach or []])
    c = st["candidates"][cid]
    commit(run, st, "cand add", {"id": cid, "lane": c["lane"], "claims": c["claims"], "kind": c["kind"],
                                 "author": c["author"], "sha256": c["sha256"], "deps": c["deps"],
                                 "revises": c["revises"], "from": c["from"], "gap": c["gap"],
                                 "direction": c["direction"], "step": c["step"], "for": c["for"],
                                 "source": c["source"], "delta_review": c.get("delta_review"),
                                 "model": c.get("model"), "attachments": c.get("attachments")})
    refresh_lane(run, st, c["lane"])
    print(msg)
    if c["kind"] == "transfer" and not c.get("for"):
        print("note: name the citer (--for Qxx|Hn|Cxxx): transfer rows are gated only when cited (program.md §5.4)",
              file=sys.stderr)


def parse_blocking(tid, text):
    """Parse 'O1 CRITICAL: <location> [<TAG>] - <one line>; O2 MAJOR: ...' (C7). Severities count only
    in uppercase right after O<n>, at the start or after ';', ',' or '['; a trailing ']' is kept."""
    if not text or text.strip().lower() in ("none", "[]", "-"):
        return []
    text = text.strip()
    if text.startswith("[") and text.endswith("]") and re.match(r"\[\s*O\d+\s", text):
        text = text[1:-1]
    ms = list(re.finditer(r"(?:^|[;,\[])\s*O(\d+)\s*:?\s*(CRITICAL|MAJOR|MINOR|COSMETIC)\b", text))
    if not ms:
        usage('--blocking format: "O1 CRITICAL: <location> [<TAG>] - <one line>; O2 MAJOR: ..."')
    out = []
    for i, m in enumerate(ms):
        body = text[m.end():ms[i + 1].start() if i + 1 < len(ms) else len(text)]
        body = body.strip().lstrip(":").strip().rstrip(";,").strip()
        oid = f"{tid}.O{int(m.group(1))}"
        if any(o["id"] == oid for o in out):
            usage(f"duplicate objection {oid} in --blocking")
        out.append(new_objection(oid, m.group(2), body or "(see report)"))
    return out


def new_objection(oid, severity, text):
    return {"id": oid, "severity": severity, "text": text, "status": "open",
            "resolved_by": None, "how": None, "note": None}


def check_reviewer(st, cid, tid, scope):
    """Refuse reviews that break I2 (non-author, distinct contexts, one scope per task)."""
    t = st["tasks"][tid]
    if t["role"] not in SCOPE_ROLES[scope]:
        fail(f"scope {scope} must come from a {' or '.join(SCOPE_ROLES[scope])} task; {tid} is a {t['role']}")
    problem = independence_problem(st, tid, st["candidates"][cid])
    if problem:
        fail(f"independence (I2): {problem}")
    prior = reviews_of(st, cid)
    if any(r["task"] == tid for r in prior):
        fail(f"{tid} already reviewed {cid}; one task supplies at most one scope per candidate")
    other = {"individual": "cross", "cross": "individual"}.get(scope)
    for r in prior:
        if other and r["scope"] == other and same_l2_context(st, tid, r["task"]):
            fail(f"the individual and cross gates of {cid} must come from different contexts "
                 f"({tid} and {r['task']} share {task_ctx(st, tid)!r})")


def clean_assumes(text):
    s = (text or "").strip()
    return None if s.lower() in ("", "none", "-", "no") else s


def review_file(run, tid, arts=None):
    """The review file task tid wrote, relative to RUN: the first existing .md other than result.md in
    result.md's artifacts: field (arts, read from result.md when None), else review.md, else report.md
    (the pre-6.2 name); None if there is none. Paths outside RUN are ignored."""
    tdir = Path(run) / "tasks" / tid
    if arts is None:
        arts = next((v for k, a, v in read_result(tdir / "result.md") or [] if k == "artifacts" and a is None), "")
    for name in re.findall(r"[^\s,;()\[\]'\"`]+\.md\b", arts or "", re.I) + ["review.md", "report.md"]:
        p = Path(name)
        if p.name.lower() == "result.md":
            continue
        for cand in ([p] if p.is_absolute() else [tdir / p, Path(run) / p]):
            r = rel(run, cand)
            if is_file(cand) and not os.path.isabs(r):
                return r
    return None


def do_review_add(st, run, cid, tid, scope, verdict, fidelity=None, blocking=None, report=None, note=None,
                  confirmed=None, assumes=None):
    """Record one review (review add and ingest). Returns (message, warnings)."""
    c = st["candidates"][cid]
    path = Path(run) / c["path"]
    if not is_file(path) or sha256_file(path) != c["sha256"]:
        fail(f"stale: {c['path']} no longer matches the sha256 frozen by 'cand add'. Reviews of edited "
             f"content are refused; freeze the edit as a new candidate (cand add --revises {cid})")
    stale = attachment_problems(run, c)
    if stale:
        fail(f"stale: {stale[0].split(' changed')[0]} of {cid} no longer matches the sha256 frozen by 'cand add'. "
             f"Reviews of edited content are refused; freeze a new candidate (cand add --revises {cid} --attach ...)")
    check_reviewer(st, cid, tid, scope)
    objections = parse_blocking(tid, blocking)
    used = {o["id"]: r["cand"] for r in st["reviews"] if r["task"] == tid for o in r["objections"]}
    clash = [o["id"] for o in objections if used.get(o["id"], cid) != cid]
    if clash:
        fail(f"objection {clash[0]} is already used by {tid} on {used[clash[0]]}: number objections "
             "uniquely across the whole report (D1)")
    if scope in ("sanity", "witness") and verdict == "FAIL" and not any(o["severity"] == "CRITICAL" for o in objections):
        k = max([int(x.split(".O")[1]) for x in list(used) + [o["id"] for o in objections]], default=0) + 1
        objections.append(new_objection(f"{tid}.O{k}", "CRITICAL", f"{scope} check contradicts the claim (see report)"))
    report = rel(run, find_input(run, report)) if report else review_file(run, tid)
    warn = []
    sev = {o["severity"] for o in objections}
    if verdict == "FAIL" and "CRITICAL" not in sev:
        warn.append("FAIL without a CRITICAL objection (verdict rule: FAIL iff a CRITICAL)")
    if verdict in PASSING and sev & {"CRITICAL", "MAJOR"}:
        warn.append("a passing verdict with CRITICAL/MAJOR objections; the objections still block")
    if c["status"] != "proposed":
        warn.append(f"{cid} is already {c['status']}; a non-pass will show in status and check")
    t = st["tasks"][tid]
    assumes = clean_assumes(assumes)
    st["reviews"].append({"cand": cid, "scope": scope, "task": tid, "verdict": verdict,
                          "fidelity": fidelity, "assumes": assumes, "sha256": c["sha256"], "report": report,
                          "note": note, "confirmed": split_list(confirmed), "isolation": t.get("isolation"),
                          "context": t.get("context"), "objections": objections, "seq": st["seq"] + 1})
    msg = (f"review recorded: {cid} {scope} {verdict}" + (f" fidelity {fidelity}" if fidelity else "")
           + (f" (assumes: {assumes})" if assumes else "") + f" by {tid}"
           + (f"; objections {', '.join(o['id'] + ' ' + o['severity'] for o in objections)}" if objections else ""))
    return msg, warn


def cmd_review_add(a):
    run, st = open_run(a)
    cid = get(st, "candidates", "C", a.cand)
    tid = get(st, "tasks", "T", a.task)
    msg, warn = do_review_add(st, run, cid, tid, a.scope, a.verdict, fidelity=a.fidelity, blocking=a.blocking,
                              report=a.report, note=text_arg(a, "note", run), confirmed=a.confirmed, assumes=a.assumes)
    for w in warn:
        print(f"note: {w}", file=sys.stderr)
    r = st["reviews"][-1]
    commit(run, st, "review add", {"cand": cid, "scope": a.scope, "task": tid, "verdict": a.verdict,
                                   "fidelity": a.fidelity, "assumes": r["assumes"],
                                   "objections": [o["id"] for o in r["objections"]]})
    refresh_lane(run, st, st["candidates"][cid].get("lane"))
    print(msg)


def revision_ancestors(st, cid):
    out, cur = set(), st["candidates"][cid].get("revises")
    while cur and cur not in out:
        out.add(cur)
        cur = st["candidates"].get(cur, {}).get("revises")
    return out


def do_resolve(st, oid, how, by_text, cand=None, note=None):
    """Resolve one objection (objection resolve and ingest). Returns (message, candidates touched)."""
    hits = [(r, o) for r in st["reviews"] for o in r["objections"] if o["id"] == oid]
    if cand:
        hits = [(r, o) for r, o in hits if r["cand"] == cand]
    if not hits:
        usage(f"unknown objection {oid}" + (f" on {cand}" if cand else ""))
    on = sorted({r["cand"] for r, _ in hits})
    if len(on) > 1:
        usage(f"{oid} is ambiguous: it was raised on {', '.join(on)}; give --cand (D1)")
    raiser = oid.split(".")[0]
    if how == "fixed":
        by = get(st, "candidates", "C", by_text)
        if on[0] not in revision_ancestors(st, by):
            fail(f"{by} does not revise the candidate {oid} was raised on (use cand add --revises)")
    else:
        by = get(st, "tasks", "T", by_text)
        bt = st["tasks"][by]
        if how == "rejected":
            if bt["role"] != "verifier" or (bt.get("mode") and bt["mode"] != "ADJUDICATE"):
                fail(f"rejected needs an ADJUDICATE verifier task; {by} is {bt['role']} {bt.get('mode') or ''}".strip())
            if by == raiser or same_l2_context(st, by, raiser):
                fail("the reviewer who raised an objection cannot adjudicate it")
            problem = independence_problem(st, by, st["candidates"][on[0]])
            if problem:
                fail(f"independence (I2): {problem}")
        elif by != raiser and not (task_ctx(st, by) and task_ctx(st, by) == task_ctx(st, raiser)):
            fail(f"withdrawn must come from the original reviewer {raiser} (same task or context)")
    for _, o in hits:
        o.update(status="resolved", how=how, resolved_by=by, note=note)
    return f"{oid} resolved ({how} by {by}) on {on[0]}", on[0], by


def cmd_objection_resolve(a):
    run, st = open_run(a)
    oid = norm_objection(a.objection)
    cand = get(st, "candidates", "C", a.cand) if a.cand else None
    note = text_arg(a, "note", run)
    msg, on, by = do_resolve(st, oid, a.how, a.by, cand, note)
    commit(run, st, "objection resolve", {"id": oid, "how": a.how, "by": by, "cand": on, "note": note})
    refresh_lane(run, st, st["candidates"][on].get("lane"))
    print(msg)
    if a.how == "fixed":
        print(f"note: a fix confirms the defect, so {on} stays blocked; {by} needs its own gates", file=sys.stderr)


def event_cands(e):
    """The candidates whose acceptance an acceptance event records (older events: the C-IDs in its note)."""
    return list(e.get("cands") or re.findall(r"\bC\d+\b", (e.get("note") or "").split("; assumes:")[0]))


def do_accept(st, run, cid):
    """Gate check and acceptance (accept and ingest --accept). Returns (message, next-step hints)."""
    c = st["candidates"][cid]
    if c["status"] != "proposed":
        fail(f"{cid} is {c['status']}, not proposed")
    problems, label = gate_check(st, run, cid)
    if problems:
        fail(f"{cid} not accepted:\n" + "\n".join(f"  - {p}" for p in problems))
    lane, claims = c.get("lane"), c.get("claims") or ""
    conflict = accept_conflict(st, run, cid)
    if conflict:
        fail(f"contradiction: {conflict}; {cid} not accepted. {CONTRA_TAIL}")
    assumes = cand_assumes(st, cid)
    c.update(status="accepted", label=label, accepted_seq=st["seq"] + 1, assumes=assumes or None)
    msg, hints = f"{cid} accepted ({label})" + assumes_note(assumes), []
    if lane and c["kind"] in RUNG_KINDS and ".R" in claims:
        etype = "top-accepted" if claims.endswith(".R1") else "rung-accepted"
        rung = int(claims.split(".R")[1])
        note = (f"{cid} accepted for {claims}" + ("" if rung == 1 else f"; lane continues on R{rung - 1}")
                + (f"; assumes: {'; '.join(assumes)}" if assumes else ""))
        prior = next((e for e in st["events"] if e["type"] == etype and e.get("lane") == lane
                      and e.get("claim") == claims and any(st["candidates"].get(x, {}).get("status") == "accepted"
                                                           for x in event_cands(e))), None)
        if prior:  # K78: one event per lane and rung, handled or not, while one of its acceptances stands
            prior["note"] = (prior.get("note") or "") + f"; also {cid} accepted"
            prior["cands"] = event_cands(prior) + [cid]
            msg += f"; {etype} {lane} already logged ({prior['id']}): note updated"
        else:  # first acceptance, or every earlier one was quarantined: a new event
            eid = add_event(st, etype, lane, note)
            st["events"][-1].update(claim=claims, cands=[cid])
            msg += f"; event {eid} {etype} {lane}"
    if c["kind"] == "counterexample":
        hints.append(f"ri.py exclude RUN --claim {claims} --cand {cid}  (logs refuted)")
    elif c["kind"] in RUNG_KINDS and claims.endswith(".D"):
        hints.append(f"ri.py exclude RUN --claim {d_refutes(run, lane)} --cand {cid}  (D refutes this rung; logs "
                     f"refuted); then optionally ledger add")
    elif c["kind"] != "manuscript":
        hints.append(f"ri.py ledger add RUN --cand {cid}  (to make it a reusable premise)")
    if assumes and lane:
        hints.append("assumption open: the next RENEW must return a HYPOTHESIS-AUDIT successor that removes it")
    return msg, hints


def cmd_accept(a):
    run, st = open_run(a)
    cid = get(st, "candidates", "C", a.cand)
    msg, hints = do_accept(st, run, cid)
    c = st["candidates"][cid]
    commit(run, st, "accept", {"cand": cid, "label": c["label"], "assumes": c.get("assumes")})
    refresh_lane(run, st, c.get("lane"))
    regenerate_ledger(run, st)
    print(msg)
    for h in hints:
        print(f"next: {h}")


# ---------------------------------------------------------------- commands: ledger, exclusions, quarantine

def new_entry(st, cid, kind, statement, excludes=None, note=None):
    c = st["candidates"][cid]
    lid = next_id(st, "L")
    st["ledger"][lid] = {"cand": cid, "kind": kind, "model": c.get("model") or model_of(st, c.get("lane")),
                         "deps": list(c.get("deps") or []), "status": "active", "label": c.get("label"),
                         "statement": statement, "excludes": excludes, "note": note, "reason": None,
                         "assumes": c.get("assumes"), "seq": st["seq"] + 1}
    return lid


def do_ledger_add(st, run, cid, statement=None):
    c = st["candidates"][cid]
    if c["status"] != "accepted":
        fail(f"{cid} is {c['status']}; only accepted candidates enter the ledger (I4)")
    dup = ledger_of(st, cid)
    if dup:
        fail(f"{cid} is already ledger entry {dup}")
    text = statement or section_paragraph(Path(run) / c["path"]) or (
        c["claims"] if c["kind"] == "transfer" else first_line(Path(run) / c["path"]))
    note = assumes_note(c.get("assumes") or [])
    if note and note.strip() not in text:
        text += note
    lid = new_entry(st, cid, c["kind"], text)
    return lid, f"{lid} <- {cid} ({c['kind']}, {c.get('label')})"


def cmd_ledger_add(a):
    run, st = open_run(a)
    cid = get(st, "candidates", "C", a.cand)
    lid, msg = do_ledger_add(st, run, cid, text_arg(a, "statement", run))
    commit(run, st, "ledger add", {"id": lid, "cand": cid})
    regenerate_ledger(run, st)
    refresh_lane(run, st, st["candidates"][cid].get("lane"))
    print(msg)


def cmd_exclude(a):
    run, st = open_run(a)
    claim = norm_claim(a.claim)
    qid, rung = claim.split(".")
    if qid not in st["questions"]:
        usage(f"unknown question {qid}")
    cid = get(st, "candidates", "C", a.cand)
    c = st["candidates"][cid]
    if c["status"] != "accepted":
        fail(f"{cid} is {c['status']}; exclusions need an accepted counterexample or an accepted proof of {qid}.D")
    prob = exclusion_problem(st, run, claim, cid)
    if prob:
        fail(prob)
    for lid, e in st["ledger"].items():
        if e["kind"] == "exclusion" and e["status"] == "active" and claim in covers(e):
            fail(f"{claim} is already excluded by {lid}")
    cov = covers({"excludes": claim})
    clash = [k for k, x in sorted(st["candidates"].items()) if x["status"] == "accepted"
             and x["kind"] in RUNG_KINDS and x.get("claims") in cov]
    if clash:
        fail(f"contradiction: {st['candidates'][clash[0]]['claims']} is accepted ({clash[0]}); excluding "
             f"{span(cov)} with {cid} contradicts it. {CONTRA_TAIL}")
    note = text_arg(a, "note", run)
    lid = new_entry(st, cid, "exclusion", f"NOT {span(cov)} (witness {cid})", excludes=claim, note=note)
    st["ledger"][lid].update(covers=cov, model=model_of(st, qid))
    msg = f"{lid} excludes {span(cov)} (witness {cid})"
    prior = [e["id"] for e in st["events"] if e["type"] == "refuted" and e.get("lane") == qid]
    if prior:
        msg += f"; refuted already logged ({prior[0]})"
    else:
        ev_note = f"{span(cov)} excluded by {lid}" + ("" if rung == "R1" else f"; R1..{rung} false by ladder nesting")
        msg += f"; event {add_event(st, 'refuted', qid, ev_note)} refuted {qid}"
    commit(run, st, "exclude", {"id": lid, "claim": claim, "covers": cov, "cand": cid, "note": note})
    regenerate_ledger(run, st)
    refresh_lane(run, st, qid)
    print(msg + ("" if rung == "R1" else f"; weaker rungs after {rung} stay open"))


def cmd_quarantine(a):
    run, st = open_run(a)
    reason = text_arg(a, "reason", run)
    if not reason:
        usage("quarantine needs --reason or --reason-file")
    target = a.target.strip().upper()
    if target.startswith("L"):
        root = get(st, "ledger", "L", target)
        ql, qc = quarantine_closure(st, {root}, set())
    elif target.startswith("C"):
        root = get(st, "candidates", "C", target)
        ql, qc = quarantine_closure(st, set(), {root})
    else:
        usage("quarantine target must be a ledger entry Lxxx (or a candidate Cxxx)")
    new = [k for k in sorted(ql) if st["ledger"][k]["status"] == "active"]
    new += [k for k in sorted(qc) if st["candidates"][k]["status"] != "quarantined"]
    if not new:
        print(f"{root} and its dependants are already quarantined; nothing changed")
        return
    for k in new:
        rec = st["ledger"][k] if k.startswith("L") else st["candidates"][k]
        rec.update(status="quarantined", reason=reason, code=a.code, quarantined_by=root)
    lanes = {st["candidates"][k].get("lane") for k in qc}
    lanes |= {c.get("lane") for c in st["candidates"].values() if set(c.get("deps") or []) & ql}
    events = [add_event(st, "model-change", lane, f"quarantine {root} ({a.code}): {reason}")
              for lane in sorted(x for x in lanes if x)]
    commit(run, st, "quarantine", {"root": root, "code": a.code, "reason": reason, "items": new})
    regenerate_ledger(run, st)
    for lane in lanes:
        refresh_lane(run, st, lane)
    print(f"quarantined: {', '.join(new)}" + (f"; events {', '.join(events)} model-change" if events else ""))


def cmd_record(a):
    run, st = open_run(a)
    qid = get(st, "questions", "Q", a.qid)
    regenerate_record(run, st, qid)
    print(f"lanes/{qid}/record.md regenerated")


def cmd_ledger(a):
    run, st = open_run(a)
    regenerate_ledger(run, st)
    print("ledger.md regenerated")


# ---------------------------------------------------------------- commands: events and control

def cmd_event(a):
    run, st = open_run(a)
    note = text_arg(a, "note", run)
    if a.handled:
        if not a.by:
            usage("--handled needs --by Txxx: the task that handled the events (any task: RENEW, SELECT, "
                  "BREADTH, comparator, writer, ...)")
        by = get(st, "tasks", "T", a.by)
        ids = [norm_id("E", x) for x in a.handled]
        known = {e["id"]: e for e in st["events"]}
        missing = [i for i in ids if i not in known]
        if missing:
            usage(f"unknown events: {', '.join(missing)}")
        released = []
        for i in ids:
            known[i]["handled_by"] = by
            q = st["questions"].get(known[i].get("lane") or "")
            if q is not None:
                if i in (q.get("held_by") or []):
                    q["held_by"].remove(i)
                    released.append(known[i]["lane"])
                if known[i]["type"] == "lane-budget":
                    q["budget_base"] = q["round"]
        commit(run, st, "event handled", {"events": ids, "by": by, "released": released})
        print(f"handled by {by}: {', '.join(ids)}" + (f"; holds released on {', '.join(sorted(set(released)))}"
                                                     if released else ""))
        return
    lane = get(st, "questions", "Q", a.lane) if a.lane else None
    dup = next((e["id"] for e in st["events"] if not e.get("handled_by") and e["type"] == a.type
                and e.get("lane") == lane and a.type in HOLD_TYPES + ("too-easy", "queue-low", "breadth-review")
                and (a.type != "too-easy" or (e.get("note") or "") == (note or ""))), None)
    if dup:
        print(f"{dup} {a.type}" + (f" {lane}" if lane else "") + " is already pending; nothing logged")
        return
    eid = log_event(st, a.type, lane, note)
    commit(run, st, "event", {"id": eid, "type": a.type, "lane": lane, "note": note})
    held = lane and a.type in HOLD_TYPES
    print(f"{eid} {a.type}" + (f" {lane}" if lane else "") + f"  (first: {event_action(st, a.type, lane)})"
          + (f"; {lane} HELD until RENEW" if held else ""))
    if st["mode"] == "focused" and a.type == "literature-hit" and lane:
        print(f"note: {FOCUSED_HOLD}", file=sys.stderr)


def cmd_control(a):
    run, st = open_run(a)
    flags = control_flags(run)
    reason = text_arg(a, "reason", run)
    if a.command == "resume":
        lift_stop = getattr(a, "stop", False)
        if lift_stop and not reason:
            usage("resume --stop needs --reason or --reason-file with the user's words")
        names = ["PAUSE"] + (["STOP"] if lift_stop else [])
        old = [flag_desc(p) for n in names for p in flags[n]]
        removed = []
        for n in names:
            for p in flags[n]:
                xp(p).unlink()
                removed.append(p.name)
        for d in old:
            print(f"removing {d}")
        msg = f"removed {', '.join(removed)}" if removed else f"no {' or '.join(names)} file present"
        if flags["STOP"] and not lift_stop:
            msg += (f"\nSTOP still in force ({flag_desc(flags['STOP'][0])}): resume removes PAUSE only. Dispatch "
                    "nothing; lift a STOP only on the user's explicit words: "
                    "ri.py resume RUN --stop --reason-file <file with their words>")
        commit(run, st, "resume", {"reason": reason, "stop": lift_stop, "removed": removed, "old": old})
    else:
        name = a.command.upper()
        atomic_write(run / name, f"{name} {now()}\n{reason or ''}\n")
        msg = f"{name} file created"
        commit(run, st, a.command, {"reason": reason})
    print(msg)


def cmd_mode(a):
    """program.md sec. 3: after a focused delivery with 'After delivery: continue', the run becomes a research
    program built on the result (SKILL.md sec. 5 focused step 5). Refused under STOP or PAUSE; idempotent; never
    re-runs intake. Records {from, seq, question, lane_rounds} as state['converted']."""
    run, st = open_run(a)
    refuse_on_control(run, "mode conversion")
    reason = text_arg(a, "reason", run)
    if st["mode"] == a.to:
        c = st.get("converted")
        print(f"already {a.to} mode" + (f" (converted from {c['from']} at seq {c['seq']} after the delivery of "
                                        f"{c.get('question') or '-'})" if c else "") + "; nothing changed")
        return
    if not reason:
        usage("mode --to program needs --reason or --reason-file (the contract's after-delivery line, or the user's words)")
    qid = delivered_question(st)
    notes = []
    if after_delivery(st) == "stop":
        notes.append("contract.md says 'After delivery: stop' (or the run predates v6.4): convert only on the user's "
                     "words; the reason was appended under contract.md's Mode - make sure it quotes them")
    live = [k for k, q in sorted(st["questions"].items()) if q["status"] == "active"]
    if live:
        notes.append(f"{', '.join(live)} still active: it runs on as a program lane (SELECT or RENEW decides its future)")
    st["mode"] = a.to
    st["converted"] = {"from": "focused", "seq": st["seq"] + 1, "question": qid,
                       "lane_rounds": st["counters"].get("lane_rounds", 0)}
    add_contract_limit(run, f"- {now()[:10]}: converted to program mode after the delivery of {qid or '-'} (program.md "
                            f"sec. 3): {' '.join(reason.split())[:300]}", "Mode")
    add_contract_limit(run, f"- Continuation (from {now()[:10]}): {CONTINUATION_SCOPE}", "Scope boundaries")
    commit(run, st, "mode", {"to": a.to, "from": "focused", "question": qid, "reason": reason})
    print(f"mode focused -> program (seq {st['seq']}; delivered: {qid or '-'}). The run continues as a research program "
          "(I9). Next: the continuation opening (program.md sec. 2.1): investigator RENEW on the delivered result "
          "(+ LANDSCAPE if none ran), then PROPOSE x2-4, then SELECT; never re-run intake. The continuation is the "
          "user's request, not optional work, and its questions are in scope (contract.md): the run is not finished. "
          "Keep the control loop going (SKILL.md sec. 6) until STOP or PAUSE, a user limit, a real host error, or "
          "exhaustion documented by BREADTH (I9); do not end the turn")
    for x in notes:
        print(f"note: {x}", file=sys.stderr)


# ---------------------------------------------------------------- ingest (B3)

HEADER_RE = re.compile(r"^([A-Za-z_][\w.-]*)(?:\s+([^\s:]+))?\s*:\s*(.*)$")
LEFT_RE = re.compile(r"\s*(?:next:|dispatch\b|too_easy reported\b|task new\b|warning:|literature-hit:|outer work:|"
                     r"context:|focused mode:|filed M\d+|M\d+ (?:DEGENERATE|corrections):)|.* -> |.*: event --type |"
                     r".*\bdispatch no provers\b|.*\bbeside their drafts\b|.*\(file under scout/\)")  # what is left


def read_result(path):
    """[(key, arg, value)] from result.md's header (between the first two '---' lines), or None."""
    if not is_file(path):
        return None
    lines = read(path).splitlines()
    start = next((i for i, x in enumerate(lines) if x.strip() == "---"), None)
    if start is not None:
        end = next((i for i in range(start + 1, len(lines)) if lines[i].strip() == "---"), len(lines))
        lines = lines[start + 1:end]
    pairs = []
    for x in lines:
        s = re.sub(r"\s{2,}#.*$", "", x).strip()
        m = HEADER_RE.match(s) if s and not s.startswith("#") else None
        if m:
            key = m.group(1) if re.fullmatch(r"Q\d+\.(?:R\d+|D)", m.group(1), re.I) else m.group(1).lower()
            pairs.append((key, m.group(2), m.group(3).strip()))
    return pairs


def kv(text, keys):
    """'verdict=FAIL; fidelity=MATCH; assumes=n even' -> dict (values may contain ';')."""
    out, ms = {}, list(re.finditer(r"\b(" + "|".join(keys) + r")\s*=", text or "", re.I))
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        out[m.group(1).lower()] = text[m.end():end].strip().rstrip(";").strip()
    return out


def word(text):
    return (text or "").split()[0] if (text or "").split() else ""


def parse_fidelity(text, assumes):
    """'MATCH', 'MATCH(assumes: A)', 'WEAKER(how)' -> (fidelity, assumes, note)."""
    s = (text or "").strip()
    if not s:
        return None, clean_assumes(assumes), None
    m = re.match(r"([A-Za-z_]+)\s*(?:\((.*)\))?\s*$", s, re.S)
    w = (m.group(1) if m else word(s)).upper()
    if w not in FIDELITIES:
        usage(f"unknown fidelity {s!r}")
    inner = m.group(2) if m else None
    if w == "MATCH" and inner and inner.lower().startswith("assumes"):
        assumes, inner = clean_assumes(assumes) or inner.split(":", 1)[-1], None
    return w, clean_assumes(assumes), (f"fidelity {w}({inner})" if inner else None)


def data_files(run, tdir, text):
    """(found paths, missing names) of a prover's `data:` field (K42): relative to the task directory,
    else to RUN."""
    found, missing = [], []
    for x in split_list(text):
        p = Path(x.strip("`'\""))
        hit = next((c for c in ([p] if p.is_absolute() else [tdir / p, Path(run) / p]) if is_file(c)), None)
        (found if hit else missing).append(hit or x)
    return found, missing


def ingest_prover(st, run, tid, t, f, pairs, out, manual, touched):
    tdir = Path(run) / "tasks" / tid
    if is_file(tdir / "notes.md"):
        t["notes"] = f"tasks/{tid}/notes.md"
        out.append(f"  notes: {t['notes']} (for RENEW)")
    if t["status"] == "blocked":
        return
    arts = [Path(x).name for x in split_list(f.get("artifacts", ""))]
    draft = next((tdir / x for x in arts if re.fullmatch(r"draft[\w-]*\.md", x) and is_file(tdir / x)), tdir / "draft.md")
    if not is_file(draft):
        t["status"] = "blocked"
        manual.append(f"{tid}: no draft.md to freeze; task set blocked")
        return
    try:
        raw_dir = f.get("direction") or t.get("direction")
        direction = norm_direction(raw_dir) if raw_dir else None
        claims, kind = word(f.get("claims")), (word(f.get("kind")) or "proof").lower()
        gap = None if word(f.get("gaps")).lower() in ("", "none", "-") else f["gaps"]
        if claims.lower() in ("", "none"):
            claims = direction_target(st, direction) if direction else None
            if not claims or not re.fullmatch(r"Q\d+\.(R\d+|D)", claims):
                manual.append(f"{tid}: claims: none and no direction target; freeze by hand if useful (a SPECIAL-CASE "
                              f"draft: cand add RUN --lane <Q> --kind lemma --direction \"<direction>\" --file "
                              f"tasks/{tid}/{draft.name} --author {tid}; gated as a lane result)")
                return
            gap = gap or "no rung claimed (claims: none)"
            kind = "proof" if kind == "counterexample" else kind
        if kind not in KINDS:
            manual.append(f"{tid}: unknown kind {kind!r}")
            return
        rebuttals = [norm_objection(x) for x in re.findall(r"\bT\d+\.O\d+\b", f.get("rebuttals", ""), re.I)]
        method = None if word(f.get("method")).lower() in ("", "none") else f["method"]
        attach, missing = data_files(run, tdir, f.get("data", ""))
        cid, msg = do_cand_add(st, run, draft, tid, kind=kind, claims=claims, method=method,
                               deps=re.findall(r"\bL\d+\b", f.get("depends_on", "")), gap=gap, direction=direction,
                               allow_pending=True, rebuttals=rebuttals, attach=attach)
    except RiError as e:
        manual.append(f"{tid}: cand add refused: {e}")
        return
    touched.add(cid)
    out.append("  " + msg)
    manual += [f"{tid}: data file {x} not found; {cid} was frozen without it (a draft that needs it: freeze "
               f"a revision with cand add --revises {cid} --attach)" for x in missing]
    if rebuttals:
        out.append(f"  dispatch ADJUDICATE for {', '.join(rebuttals)} (one task each: task new --role verifier "
                   "--mode ADJUDICATE --objection <id> --start)")


def ingest_verifier(st, run, tid, t, f, pairs, out, manual, touched):
    mode = word(f.get("scope") or t.get("mode")).upper()
    scope = MODE_SCOPE.get(mode)
    if not scope:
        manual.append(f"{tid}: unknown verifier scope {mode!r}")
        return
    report = review_file(run, tid, f.get("artifacts", ""))
    groups, rulings = {}, []
    for k, arg, v in pairs:
        if k in ("review", "blocking", "confirmed", "too_easy", "new_argument") and arg:
            if not re.fullmatch(r"C\d+", arg, re.I):
                manual.append(f"{tid}: malformed candidate ID in '{k} {arg}'")
                continue
            groups.setdefault(norm_id("C", arg), {}).setdefault(k, []).append(v)
        elif k == "ruling" and arg:
            rulings.append((arg, v))
    if mode == "ADJUDICATE":
        ingest_rulings(st, run, tid, t, rulings, groups, report, out, manual, touched)
        return
    if not groups:
        manual.append(f"{tid}: no `review Cxxx:` lines in the result header")
    for cid, g in groups.items():
        if cid not in st["candidates"]:
            manual.append(f"{tid}: unknown candidate {cid}")
            continue
        if "review" not in g:
            manual.append(f"{tid} {cid}: blocking/confirmed lines without a `review {cid}:` line")
            continue
        d = kv(g["review"][0], ("verdict", "fidelity", "assumes"))
        verdict = word(d.get("verdict")).upper()
        try:
            if verdict not in VERDICTS:
                usage(f"unknown verdict {d.get('verdict')!r}")
            fid, assumes, fnote = parse_fidelity(d.get("fidelity"), d.get("assumes"))
            note = "; ".join(x for x in ({"SECOND-INDEPENDENT": "single-draft", "SALVAGE": "salvage"}.get(mode), fnote) if x) or None
            msg, warn = do_review_add(st, run, cid, tid, scope, verdict, fidelity=fid, report=report, note=note,
                                      blocking="; ".join(x for x in g.get("blocking", []) if word(x).lower() != "none") or None,
                                      confirmed="; ".join(g.get("confirmed", [])) or None, assumes=assumes)
        except RiError as e:
            manual.append(f"{tid} {cid}: review add refused: {e}")
            continue
        touched.add(cid)
        out.append("  " + msg + "".join(f" [note: {w}]" for w in warn))
        na = word((g.get("new_argument") or [""])[0]).lower()
        if na in ("yes", "no"):  # K43: a transfer resting on a new argument needs a second ISOLATED pass
            st["reviews"][-1]["new_argument"] = na == "yes"
            if na == "yes" and st["candidates"][cid]["kind"] == "transfer":
                out.append(f"  new_argument {cid}: yes -> a second ISOLATED pass from another fresh task is needed")
        te = word((g.get("too_easy") or ["none"])[0]).lower()
        if te not in ("none", "-", "no", "") and is_implied(st["candidates"][cid]):
            out.append(f"  too_easy {cid}: ignored (a KILL(IMPLIED) certificate is easy by design; program.md sec. 7)")
        elif te not in ("none", "-", "no", ""):
            st["reviews"][-1]["too_easy"] = te
            lane = st["candidates"][cid].get("lane")
            out.append(f"  too_easy {cid}: {te} -> event --type too-easy" + (f" --lane {lane}" if lane else "")
                       + f" --note \"{cid}: {te} ({tid})\"  (then skeptic MODEL-GATE + CLAIM-GATE)")
    if f.get("ranking"):
        t["ranking"] = f["ranking"]
        out.append(f"  ranking: {cell(f['ranking'], 160)}")
    sfs = f.get("shared_failing_step", "")
    if word(sfs).lower() not in ("", "none", "-"):
        t["shared_failing_step"] = sfs
        lane = t.get("lane") or next((st["candidates"][c].get("lane") for c in groups if c in st["candidates"]), None)
        out.append(f"  shared_failing_step: {cell(sfs, 120)} -> event --type stall --lane {lane or '<Q>'} "
                   "--note-file <file> (then a TARGETED review of the stuck step)")


def ingest_rulings(st, run, tid, t, rulings, groups, report, out, manual, touched):
    by_cand = {}
    for arg, v in rulings:
        if not re.fullmatch(r"T\d+\.O\d+", arg, re.I):
            manual.append(f"{tid}: malformed objection reference {arg!r}")
            continue
        oid, ruling = norm_objection(arg), word(v).upper()
        if ruling not in ("UPHELD", "REJECTED"):
            manual.append(f"{tid}: ruling {oid}: expected UPHELD or REJECTED, got {v!r}")
            continue
        cs = sorted({r["cand"] for r in st["reviews"] for o in r["objections"] if o["id"] == oid})
        if t.get("cands"):
            cs = [c for c in cs if c in t["cands"]] or cs
        if len(cs) != 1:
            manual.append(f"{tid}: {oid} matches {', '.join(cs) or 'no candidate'}; record by hand")
            continue
        by_cand.setdefault(cs[0], []).append((oid, ruling))
    if not by_cand and not rulings:
        manual.append(f"{tid}: no `ruling Txxx.Ok:` line in the result header")
    for cid, rs in by_cand.items():
        verdict = "FAIL" if any(r == "UPHELD" for _, r in rs) else "PASS"
        bl = [x for x in (groups.get(cid) or {}).get("blocking", []) if word(x).lower() != "none"]
        try:
            msg, _ = do_review_add(st, run, cid, tid, "adjudicate", verdict, report=report, blocking="; ".join(bl) or None,
                                   note="; ".join(f"ruling {o}: {r}" for o, r in rs))
        except RiError as e:
            manual.append(f"{tid} {cid}: review add refused: {e}")
            continue
        touched.add(cid)
        out.append("  " + msg)
        for oid, r in rs:
            if r == "REJECTED":
                try:
                    out.append("  " + do_resolve(st, oid, "rejected", tid, cand=cid, note=f"ruling of {tid}")[0])
                except RiError as e:
                    manual.append(f"{tid}: objection resolve {oid} refused: {e}")
    for cid, g in sorted(groups.items()):  # a new problem found in another candidate (e.g. the rebuttal draft)
        bl = [x for x in g.get("blocking", []) if word(x).lower() != "none"]
        if cid in by_cand or not bl:
            continue
        if not by_cand or cid not in st["candidates"]:
            manual.append(f"{tid}: `blocking {cid}:` lines not recorded (no ruling recorded, or unknown candidate); "
                          "record them by hand (review add --scope adjudicate)")
            continue
        try:
            verdict = "FAIL" if any(re.match(r"\s*O\d+\s*:?\s*CRITICAL\b", x) for x in bl) else "INCONCLUSIVE"
            msg, _ = do_review_add(st, run, cid, tid, "adjudicate", verdict, report=report, blocking="; ".join(bl),
                                   note=f"new problem found while adjudicating ({tid})")
        except RiError as e:
            manual.append(f"{tid} {cid}: review add refused: {e}")
            continue
        touched.add(cid)
        out.append("  " + msg)


def ingest_scout(st, run, tid, t, f, pairs, out, manual, touched):
    mode = (t.get("mode") or word(f.get("mode"))).upper()
    checks = [(arg, v) for k, arg, v in pairs if k == "check" and arg]
    blocks_ = {}
    for k, arg, v in pairs:
        if k == "blocking" and arg and re.fullmatch(r"C\d+", arg, re.I):
            blocks_.setdefault(norm_id("C", arg), []).append(v)
    if not checks and f.get("outcome"):
        ids = re.findall(r"\bC\d+\b", f.get("checked", ""), re.I) or list(t.get("cands") or [])
        if len(ids) == 1:
            checks = [(ids[0], f"outcome={f['outcome']}; exact={f.get('exact', 'no')}")]
    if not checks:
        if mode in ("SANITY", "WITNESS"):
            manual.append(f"{tid}: no `check Cxxx: outcome=...` line in the result header")
        show_fields(pairs, out)
        return
    report = review_file(run, tid, f.get("artifacts", "")) or f"tasks/{tid}/result.md"
    for arg, v in checks:
        if not re.fullmatch(r"C\d+", arg, re.I):
            manual.append(f"{tid}: malformed candidate ID in 'check {arg}'")
            continue
        cid = norm_id("C", arg)
        d = kv(v, ("outcome", "exact"))
        outc, exact = word(d.get("outcome")).lower(), word(d.get("exact")).lower().startswith("y")
        if outc == "table-ready":
            out.append(f"  {cid}: table-ready (file under scout/)")
            continue
        verdict = {"consistent": "PASS", "witness-valid": "PASS" if exact else "INCONCLUSIVE",
                   "contradicts": "FAIL", "witness-invalid": "FAIL"}.get(outc)
        if not verdict or cid not in st["candidates"]:
            manual.append(f"{tid}: check {cid}: cannot map outcome {outc!r}")
            continue
        scope = "witness" if outc.startswith("witness") or mode == "WITNESS" else "sanity"
        try:
            msg, _ = do_review_add(st, run, cid, tid, scope, verdict, report=report,
                                   blocking="; ".join(blocks_.get(cid, [])) or None,
                                   note=None if exact else "exact: no")
        except RiError as e:
            manual.append(f"{tid} {cid}: review add refused: {e}")
            continue
        touched.add(cid)
        out.append("  " + msg)


ITEM_KEYS = ("verdict", "plausibility", "solved", "corrections")
QG_VERDICTS = ("ADVANCE", "REFORMULATE", "DEMOTE", "SOLVED", "REFUTE-SKETCH")  # and KILL(<code>)
GATED_ARGUMENTS = {"SOLVED": ("solved", "R1"), "REFUTE-SKETCH": ("refutation", "D"), "KILL(IMPLIED)": ("implied", "R1")}
CLAIM_HINTS = {
    "STANDS": "report it with its label",
    "QUALIFY": "copy the qualifier verbatim into every progress.md section stating the result, sec. 1 included, "
               "and into the writer's Assignment (program.md sec. 5.2)",
    "OVERCLAIM": "copy the corrected wording verbatim into every progress.md section stating the result, sec. 1 "
                 "included, and into the writer's Assignment (program.md sec. 5.2)",
    "KNOWN": "a rediscovery: report it with its locator; event --type literature-hit --lane {lane} --note-file "
             "<file> (a locator with no source card gets a TARGETED task that cards it)",
    "TRIVIAL": "remark; dispatch a skeptic MODEL-GATE for loopholes",
}


def item_fields(text, keys=ITEM_KEYS):
    """'{verdict: KILL(IMPLIED), plausibility: mixed, solved: R3}' -> dict (braces optional; a bare value is
    the verdict; a key counts only at the start or after ',' or ';', so values may contain ',', ':' or '=')."""
    s = (text or "").strip()
    if s.startswith("{"):  # anything after the closing brace is a comment
        s = s[1:s.rfind("}")] if "}" in s else s[1:]
    ms = list(re.finditer(r"(?:^|[,;])\s*(" + "|".join(keys) + r")\s*[:=]", s, re.I))
    if not ms:
        return {"verdict": s} if s else {}
    out = {}
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(s)
        out.setdefault(m.group(1).lower(), s[m.end():end].strip().rstrip(",;").strip())
    return out


def verdict_code(text):
    """'kill (implied)' -> 'KILL(IMPLIED)'."""
    return word(re.sub(r"\s+\(", "(", text or "")).upper().strip("{}.,;")


def skeptic_file(run, tid, prefix, qid):
    """tasks/<tid>/<prefix>-Qxx.md (any zero padding or case), or None."""
    tdir = Path(run) / "tasks" / tid
    if is_file(tdir / f"{prefix}-{qid}.md"):
        return tdir / f"{prefix}-{qid}.md"
    try:
        names = sorted(os.listdir(xp(tdir)))
    except OSError:
        names = []
    for n in names:
        m = re.fullmatch(re.escape(prefix) + r"-Q0*(\d+)\.md", n, re.I)
        if m and int(m.group(1)) == int(qid[1:]):
            return tdir / n
    return None


def sanity_line(run, qid):
    """The lane statement's Sanity line when it names a scout check (not pending, not 'not checkable')."""
    m = re.search(r"(?im)^\s*Sanity\s*[.:]\s*(.+)$", read(Path(run) / "lanes" / qid / "statement.md"))
    s = m.group(1).strip() if m else ""
    return None if not s or s.startswith("<") or re.match(r"(pending|not checkable)\b", s, re.I) else s


def mark_gate_only(st, q, rnd):
    """An opened round becomes gate-only (a fast start): uncount it from the breadth trigger's lane-rounds."""
    if not is_gate_only(q, rnd):
        q.setdefault("gate_only", []).append(rnd)
        st["counters"]["lane_rounds"] = max(0, st["counters"].get("lane_rounds", 0) - 1)


def gate_argument(st, run, tid, qid, path, claim, for_, open_round, out, manual, touched):
    """program.md sec. 5.3: freeze a skeptic's argument unchanged (author: the skeptic task) and print its
    gate-only round and reviews (INDIVIDUAL + SECOND-INDEPENDENT, a SANITY check if the Sanity line names one)."""
    q = st["questions"][qid]
    active = q["status"] == "active" and q["round"] >= 1
    rnd = q["round"] if active else q["round"] + 1
    try:
        cid, msg = do_cand_add(st, run, path, tid, kind="proof", claims=claim, lane=qid, rnd=rnd, for_=for_)
    except RiError as e:
        manual.append(f"{tid}: cand add refused for {Path(path).name}: {e}")
        return
    touched.add(cid)
    out.append(f"  {msg}")
    if open_round and active:
        if any(t["role"] == "prover" for t in lane_tasks(st, qid, rnd).values()):
            out.append(f"  {qid} round {rnd} already has provers: gate {cid} beside their drafts")
        else:
            mark_gate_only(st, q, rnd)
            out.append(f"  {qid} round {rnd} is now a gate-only round: dispatch no provers in it (program.md sec. 5.3)")
    elif open_round:
        if q["status"] != "active":
            out.append(f"  next: q set RUN {qid} --status active --slots {q.get('slots') or 2} --plausibility "
                       + ("doubtful" if claim.endswith(".D") else "supported"))
        out.append(f"  next: round RUN {qid} --open --gate-only  (a round with no provers; outside the lane cap)")
    for mode in ("INDIVIDUAL", "SECOND-INDEPENDENT"):
        out.append(f"  next: task new RUN --role verifier --mode {mode} --cand {cid} --start")
    if sanity_line(run, qid):
        out.append(f"  next: task new RUN --role scout --mode SANITY --cand {cid} --start  "
                   f"(Sanity: {cell(sanity_line(run, qid), 80)})")


def is_user_claim(st, qid):
    """Focused mode: the claim the user asked for - Q01, or the question READING re-targeted from it (program.md
    sec. 3). Its KILL(IMPLIED) argument is always gated, and a light-gate KILL never makes it a dead end."""
    q = st["questions"].get(qid) or {}
    return st["mode"] == "focused" and (qid == "Q01" or ((q.get("operator") or "").upper() == "READING"
                                                         and q.get("parent") == "Q01"))


def skeptic_question(st, run, tid, qid, d, out, manual, touched):
    """One QUESTION-GATE item: record the verdict and route it (program.md sec. 5.2-5.3)."""
    q = st["questions"].get(qid)
    code = verdict_code(d.get("verdict"))
    if q is None or not (code in QG_VERDICTS or code.startswith("KILL")):
        manual.append(f"{tid}: {qid}: " + ("unknown question" if q is None else f"unknown QUESTION-GATE verdict {code!r}"))
        return
    q.setdefault("verdicts", []).append({"task": tid, "code": code, "seq": st["seq"] + 1})
    plaus = word(d.get("plausibility")).lower()
    head = f"  {qid}: {code}" + (f" (plausibility {plaus})" if plaus else "")
    user_claim = is_user_claim(st, qid)  # the user asked for this claim: always gated, never a dead end
    active = q["status"] == "active"
    if code == "ADVANCE" and active:  # a fast-start or foothold lane stays active (program.md sec. 5.2, 6.1)
        out.append(head + f" -> q set RUN {qid} --plausibility {plaus or '<p>'} (the lane is open: round "
                          f"{q['round']}'s provers may go, program.md sec. 6.1; a later full gate takes effect at the "
                          "lane's next round boundary)")
    elif code == "ADVANCE":
        out.append(head + f" -> q set RUN {qid} --plausibility {plaus or '<p>'}; --status ready once program.md "
                          "sec. 6 holds")
    elif code == "KILL(FALSE)" and user_claim:  # SKILL.md sec. 5 focused step 2: the witness first, then READING
        out.append(head + f" -> no provers; do not kill {qid}: gate the witness (verification.md sec. 8): cand add "
                          f"RUN --lane {qid} --claims {qid}.R1 --kind counterexample --file tasks/{tid}/<witness file> "
                          f"--author {tid}, then INDIVIDUAL, SECOND-INDEPENDENT and WITNESS; exclude logs refuted, and "
                          "one limited RENEW applies READING (program.md sec. 3)")
    elif code in ("SOLVED", "REFUTE-SKETCH") or (code == "KILL(IMPLIED)" and user_claim):
        prefix, rung = GATED_ARGUMENTS[code]
        out.append(head + f" -> {prefix}-{qid}.md is gated at once (program.md sec. 5.3)")
        path = skeptic_file(run, tid, prefix, qid)
        if path is None:
            manual.append(f"{tid}: {qid} {code} without tasks/{tid}/{prefix}-{qid}.md: ask the skeptic for the file")
        else:
            gate_argument(st, run, tid, qid, path, f"{qid}.{rung}", qid if code == "KILL(IMPLIED)" else None, True,
                          out, manual, touched)
    elif code in ("REFORMULATE", "DEMOTE", "KILL(IMPLIED)") or (code.startswith("KILL") and user_claim):
        eid = log_event(st, "question-verdict", qid, f"{code} ({tid})")
        out.append(head + f" -> event {eid} question-verdict {qid} ({event_action(st, 'question-verdict')})"
                   + ("; no provers in this round" if user_claim and active else ""))
        if code == "KILL(IMPLIED)":
            out.append(f"  next: q set RUN {qid} --status killed --note-file <file>  (\"IMPLIED: follows from "
                       "<locator>\": an attributed answer, never a dead end; its argument is gated only for a named "
                       "citer: tasks_requested gate-only Qxx for Qyy)")
    elif code.startswith("KILL"):
        out.append(head + f" -> q set RUN {qid} --status killed --note-file <file>  "
                          f"(\"{code[5:-1] or 'KILL'}: <evidence>\"; a dead end)"
                   + ("; an exclusion only after the witness passes the counterexample gate (verification.md sec. 8) "
                      "and exclude" if code == "KILL(FALSE)" else ""))
    solved = word(d.get("solved")).upper()
    if solved and solved not in ("NONE", "-") and code != "SOLVED":
        path = skeptic_file(run, tid, "solved", qid)
        if not re.fullmatch(r"R\d+", solved) or path is None:
            manual.append(f"{tid}: {qid} solved: {solved}: " + ("not a rung Rj" if path else
                                                              f"no tasks/{tid}/solved-{qid}.md"))
        else:  # a lower rung needs no round: it is gated beside whatever its question does
            gate_argument(st, run, tid, qid, path, f"{qid}.R{int(solved[1:])}", None, False, out, manual, touched)


def skeptic_claim(st, tid, claim, d, out, manual):
    """One CLAIM-GATE item: print its route (program.md sec. 5.2)."""
    code = verdict_code(d.get("verdict"))
    hint = CLAIM_HINTS.get(code)
    if hint is None:
        manual.append(f"{tid}: {claim}: unknown CLAIM-GATE verdict {code!r}")
        return
    out.append(f"  {claim}: {code} -> " + hint.format(lane=claim.split(".")[0]))


def ingest_skeptic(st, run, tid, t, f, pairs, out, manual, touched):
    """Skeptic items: `Qxx: {verdict: ...}` (QUESTION-GATE), `Mx: {...}` (MODEL-GATE), `Qxx.Rj: {...}`
    (CLAIM-GATE); other fields (too_easy, contradiction, ...) are shown as for any role."""
    rest = []
    for k, arg, v in pairs:
        if arg is None and re.fullmatch(r"q\d+", k):
            skeptic_question(st, run, tid, norm_id("Q", k), item_fields(v), out, manual, touched)
        elif arg is None and re.fullmatch(r"m\d+", k):
            ingest_model_item(st, run, tid, f"M{int(k[1:])}", item_fields(v), out, manual, touched)
        elif arg is None and re.fullmatch(r"Q\d+\.(?:R\d+|D)", k, re.I):
            skeptic_claim(st, tid, norm_claim(k), item_fields(v), out, manual)
        else:
            rest.append((k, arg, v))
    foot = foothold_seed(st)
    if foot and st["questions"][foot]["verdicts"][-1]["task"] == tid:  # this seed light gate released it
        out.append(f"  next: {foothold_line(foot)}")
    show_fields(rest, out)


def words_in(path):
    return len(read(path).split())


def ingest_investigator(st, run, tid, t, f, pairs, out, manual, touched):
    """RENEW's successor duty (K10, program mode): no successor card while the portfolio is below the cap."""
    show_fields(pairs, out)
    if st["mode"] == "program" and t.get("mode") == "RENEW" and t["status"] != "blocked" and not continuation_open(st):
        cards = list(xp(Path(run) / "tasks" / tid / "new").glob("N*-card.md"))
        live = sum(q["status"] in ("ready", "vetting") or (q["status"] == "active" and not in_gate_only_round(q))
                   for q in st["questions"].values())
        if not cards and live < lane_cap(st):
            out.append("  RENEW returned no successor while the portfolio is below the lane cap "
                       f"({live} active + ready + vetting < {lane_cap(st)}): event --type queue-low")


def ingest_comparator(st, run, tid, t, f, pairs, out, manual, touched):
    """K43: the comparator's `selected:` candidates are the presented results; their dependency closures
    are load-bearing (load_bearing). K74: selection.md stays short when one candidate is selected."""
    show_fields(pairs, out)
    named = [norm_id("C", x) for x in re.findall(r"\bC\d+\b", f.get("selected", ""), re.I)]
    manual += [f"{tid}: selected {x} is not a candidate" for x in named if x not in st["candidates"]]
    sel = [x for x in named if x in st["candidates"]]
    if sel:
        st["selected"] = list(dict.fromkeys((st.get("selected") or []) + sel))
        out.append(f"  presented: {', '.join(sel)} (their dependency closures are load-bearing)")
    n = words_in(Path(run) / "tasks" / tid / "selection.md")
    if len(named or st.get("selected") or []) == 1 and n > 600:
        out.append(f"  warning: selection.md has {n} words for one selected candidate (about 400 words; "
                   "prompts/comparator.md)")


def ingest_writer(st, run, tid, t, f, pairs, out, manual, touched):
    """K74: the manuscript stays within the presented candidates plus about 1,200 words of framing."""
    show_fields(pairs, out)
    C = st["candidates"]
    # the writer's own --cand first: st["selected"] also collects every earlier writer's candidates (K43)
    shown = [c for c in (t.get("cands") or st.get("selected") or []) if c in C]
    n = words_in(Path(run) / "tasks" / tid / "manuscript.md")
    base = sum(words_in(Path(run) / C[c]["path"]) for c in shown)
    if shown and n > base + 1200:
        out.append(f"  warning: manuscript.md has {n} words, more than the presented candidates ({base}) + 1,200: "
                   "trim the framing (prompts/writer.md budget)")


LIT_REPORT = {"LANDSCAPE": "landscape.md", "TARGETED": "targeted.md"}
CARD_NAME_RE = re.compile(r"(S\d+|NEW-[^\\/]+)\.md", re.I)


def task_cards(run, tid):
    """Source cards a literature task wrote in its directory: Sxx.md and NEW-<name>.md."""
    d = xp(Path(run) / "tasks" / tid)
    return sorted(p.name for p in d.iterdir() if p.is_file() and CARD_NAME_RE.fullmatch(p.name)) if d.is_dir() else []


def ingest_literature(st, run, tid, t, f, pairs, out, manual, touched):
    """K03, K53: route a literature result by its fields. found: settles -> a literature-hit hint; bridges ->
    context, never an event; follow_ups -> outer work; cards -> file-cards."""
    show_fields(pairs, out)
    m = re.match(r"\s*([A-Za-z-]+)", f.get("found", ""))
    found = m.group(1).lower() if m else ""
    if found == "settles":
        qs = sorted({norm_id("Q", x) for x in re.findall(r"\bQ\d+\b", f.get("found", ""), re.I)})
        out.append(f"  literature-hit: event --type literature-hit [--lane {'|'.join(qs) or 'Qxx'} if it names that "
                   "question's claim] --note-file <file> (program.md sec. 7)")
        if st["mode"] == "focused":
            out.append(f"  {FOCUSED_HOLD}")
    elif found == "bridges":
        name = LIT_REPORT.get(t.get("mode") or "", "result.md")
        path = f"tasks/{tid}/{name if is_file(Path(run) / 'tasks' / tid / name) else 'result.md'}"
        out.append(f"  context: pass {path} by path to MODEL, SELECT and the lane's next summarizers; no event")
    ups = [x for x in split_list(f.get("follow_ups", "")) if x not in ("-", "n/a")]
    if ups:
        out.append(f"  outer work: {cell('; '.join(ups), 200)} (program.md sec. 2 step 3: while MODEL runs, never in "
                   "its blocking wave; later the next SELECT or RENEW re-lists them)")
    cards = task_cards(run, tid)
    if cards and not t.get("filed_seq"):
        out.append(f"  next: file-cards RUN {tid} ({len(cards)} card{'s' if len(cards) > 1 else ''})")


def task_file(run, tid, prefix, mid):
    """tasks/<tid>/<prefix>-<mid>.md for an ID such as M2 (any case or zero padding), or None."""
    tdir = Path(run) / "tasks" / tid
    if not xp(tdir).is_dir():
        return None
    for p in sorted(xp(tdir).iterdir(), key=lambda p: p.name):
        m = re.fullmatch(re.escape(prefix) + r"-([A-Za-z])0*(\d+)\.md", p.name, re.I)
        if m and m.group(1).upper() == mid[0] and int(m.group(2)) == int(mid[1:]):
            return tdir / p.name
    return None


def next_model(st, run):
    """M<n>: n = 1 + the largest model number in frontier/model.md, frontier/patches/, the filed models and
    the questions' models."""
    nums = [int(x) for x in re.findall(r"\bM(\d+)\b", read(Path(run) / "frontier" / "model.md"))]
    pdir = xp(Path(run) / "frontier" / "patches")
    if pdir.is_dir():
        nums += [int(m.group(1)) for p in pdir.iterdir() for m in [re.fullmatch(r"M(\d+)\.md", p.name, re.I)] if m]
    nums += [int(k[1:]) for k in st.get("models") or {}]
    nums += [int(q["model"][1:]) for q in st["questions"].values() if q.get("model")]
    return f"M{max(nums, default=0) + 1}"


def ingest_model_item(st, run, tid, mx, d, out, manual, touched):
    """K17, K22, K25: one MODEL-GATE item. PATCH: file patch-<Mx>.md verbatim as the next model ID; DEGENERATE:
    the apply-verdicts hint, and for M1 freeze degenerate-M1.md as a transfer candidate; corrections: hint."""
    verdict = word(d.get("verdict")).upper().rstrip(",;")
    out.append(f"  {mx}: {verdict or '-'}")
    if verdict == "PATCH":
        src = task_file(run, tid, "patch", mx)
        if not src:
            manual.append(f"{tid}: {mx} PATCH without tasks/{tid}/patch-{mx}.md; file the patch by hand "
                          "(frontier/patches/M<n>.md, verbatim) or ask the skeptic for the file")
        else:
            mn = next_model(st, run)
            rel_path = f"frontier/patches/{mn}.md"
            head = f"{mn} = {mx} + patch from {tid} (verbatim; counts as gated)\n\n"
            atomic_write(Path(run) / rel_path, head.encode("utf-8") + xp(src).read_bytes())
            st.setdefault("models", {})[mn] = {"base": mx, "task": tid, "path": rel_path}
            out.append(f"  filed {mn} = {mx} + patch ({tid}): {rel_path}; use --model {mn} for questions and lanes on {mx}")
    elif verdict == "DEGENERATE":
        out.append(f"  {mx} DEGENERATE: apply-verdicts MODEL (at most once at opening; program.md §5.2)")
        if mx == "M1":
            src = task_file(run, tid, "degenerate", mx)
            if not src:
                manual.append(f"{tid}: M1 DEGENERATE without tasks/{tid}/degenerate-M1.md; ask the skeptic for the "
                              "argument (it is reported first and gated, K25)")
            else:
                try:
                    cid, msg = do_cand_add(st, run, src, tid, kind="transfer", claims=f"transfer:degenerate M1 ({tid})@M1")
                except RiError as e:
                    manual.append(f"{tid}: cand add of {rel(run, src)} refused: {e}")
                else:
                    touched.add(cid)
                    out.append("  " + msg)
                    out.append(f"  task new --role verifier --mode ISOLATED --cand {cid} --start; report now in "
                               "progress.md §1 and How I read your request (K25), labelled \"candidate (skeptic "
                               "argument; check pending)\"")
    elif verdict != "SOUND":
        manual.append(f"{tid}: {mx}: unknown MODEL-GATE verdict {d.get('verdict')!r} (SOUND, PATCH or DEGENERATE)")
    if word(d.get("corrections")).lower() not in ("", "none", "-", "no"):
        out.append(f"  {mx} corrections: copy verbatim under {mx} in How I read your request (program.md §5.2); the "
                   "next SELECT or RENEW applies them")


def ingest_task(st, run, tid, out, manual, touched):
    """Integrate one task's result.md. Returns True when state changed."""
    t = st["tasks"][tid]
    res = Path(run) / "tasks" / tid / "result.md"
    if t.get("superseded_by"):
        if is_file(res):
            t["late_result_seen"] = True
            out.append(f"{tid}: superseded by {t['superseded_by']}; its late result.md is extra evidence: "
                       "file it, do not re-ingest")
            return True
        manual.append(f"{tid}: superseded by {t['superseded_by']}; nothing to ingest")
        return False
    if t.get("ingested_seq"):
        manual.append(f"{tid}: already ingested (seq {t['ingested_seq']}); nothing done")
        return False
    pairs = read_result(res)
    if pairs is None:
        manual.append(f"{tid}: no tasks/{tid}/result.md (worker alive -> wait; else task new --redo {tid})")
        return False
    f = {}
    for k, arg, v in pairs:
        if arg is None:
            f.setdefault(k, v)
    status = {"completed": "done", "done": "done", "partial": "partial", "blocked": "blocked"}.get(word(f.get("status")).lower())
    if not status:
        manual.append(f"{tid}: result.md header has no status: completed | partial | blocked")
        return False
    t.update(status=status, ingested_seq=st["seq"] + 1)
    out.append(f"{tid} {t['role']}" + (f" {t['mode']}" if t.get("mode") else "") + f": {status}"
               + (f" - {cell(f['summary'], 100)}" if f.get("summary") else ""))
    if t["role"] == "process-advisor" and status != "blocked":
        file_instructions(run, tid, out, manual)
    handler = {"prover": ingest_prover, "verifier": ingest_verifier, "scout": ingest_scout, "skeptic": ingest_skeptic,
               "investigator": ingest_investigator, "comparator": ingest_comparator,
               "writer": ingest_writer, "literature-reviewer": ingest_literature}.get(t["role"])
    if handler and (status != "blocked" or t["role"] == "prover"):
        handler(st, run, tid, t, f, pairs, out, manual, touched)
    else:
        show_fields(pairs, out)
    return True


def file_instructions(run, tid, out, manual):
    """File a process advisor's new instructions.md (written in its task dir) into RUN/instructions.md.

    The advisor never edits the canonical file in place, so `task new` never reads a half-written
    file; this copy happens under the run lock (I6)."""
    src = Path(run) / "tasks" / tid / "instructions.md"
    if not is_file(src):
        out.append(f"  {tid}: no new instructions.md (rules unchanged)")
        return
    text = xp(src).read_text(encoding="utf-8-sig")
    if not parse_instructions(text)[1] and "revision:" not in text.lower():
        manual.append(f"{tid}: tasks/{tid}/instructions.md has no 'revision:' line or rule blocks; not filed")
        return
    atomic_write(Path(run) / "instructions.md", text)
    out.append(f"  {tid}: filed tasks/{tid}/instructions.md -> instructions.md (revision {parse_instructions(text)[0]})")


def show_fields(pairs, out):
    """Other roles: print the role fields (status only is recorded; filing is the orchestrator's)."""
    out.extend([f"  {k}{' ' + a if a else ''}: {cell(v, 120)}" for k, a, v in pairs
                if k not in ("task", "role", "status", "summary")][:12])
    if any(k == "too_easy" and word(v).lower() not in ("none", "-", "no", "") for k, _, v in pairs):
        out.append("  too_easy reported: event --type too-easy --lane <Q> --note-file <file> (E8)")


def ingest_accept(st, run, touched, out, manual):
    C = st["candidates"]
    lanes = {C[k].get("lane") for k in touched if C[k].get("lane")}
    pool = sorted(set(touched) | {k for k, c in C.items() if c.get("lane") in lanes and c["status"] == "proposed"})
    changed = False
    for k in pool:
        c = C[k]
        if c["status"] != "proposed" or gate_check(st, run, k)[0]:
            continue
        try:
            msg, hints = do_accept(st, run, k)
        except RiError as e:
            manual.append(f"{k}: {e}")
            continue
        changed = True
        out.append("accepted: " + msg)
        if c["kind"] in RUNG_KINDS + ("lemma", "imported", "transfer"):
            out.append("  ledger: " + do_ledger_add(st, run, k)[1])
            hints = [h.replace("; then optionally ledger add", "; its ledger entry is already added") for h in hints
                     if "ledger add" not in h or "exclude" in h]
        out.extend(f"  next: {h}" for h in hints)
    return changed


def cmd_ingest(a):
    run, st = open_run(a)
    tids = list(dict.fromkeys(get(st, "tasks", "T", x) for x in a.tids))
    out, manual, touched = [], [], set()
    changed = False
    for tid in tids:
        changed = ingest_task(st, run, tid, out, manual, touched) or changed
    if a.accept:
        changed = ingest_accept(st, run, touched, out, manual) or changed
    if changed:
        commit(run, st, "ingest", {"tasks": tids, "accept": a.accept, "cands": sorted(touched)})
        for lane in sorted(({st["candidates"][k].get("lane") for k in touched}
                            | {st["tasks"][t].get("lane") for t in tids}) - {None}):
            refresh_lane(run, st, lane)
        regenerate_ledger(run, st)
    if a.brief:  # K55: each task's status line and what is left for you (next steps, routing hints)
        out = [x for x in out if re.match(r"T\d+\b", x) or LEFT_RE.match(x)]
    print("\n".join(out) if out else "nothing ingested")
    if manual:
        print("manual (handle by hand):\n" + "\n".join(f"  - {m}" for m in manual))


# ---------------------------------------------------------------- file-cards (K52)

ARXIV_RE = re.compile(r"(?<![\d.])(\d{4}\.\d{4,5})(?!\d)")
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s)\]>,;\"'`]+)")


def card_keys(text):
    """Dedupe keys of a source card, read from its identity part (before its results): arXiv ID, DOI, and the
    normalized title and authors (lower-case alphanumerics)."""
    ident = re.split(r"(?im)^\W*results\b", text, maxsplit=1)[0]

    def field(name):
        m = re.search(r"(?im)^[\s>*_-]*" + name + r"[\s*_]*:[\s*_]*(.+)$", ident)
        return m.group(1) if m else ""

    head = next((re.sub(r"^#+\s*(?:S\d+|NEW-\S+)?\s*[-:|–—]*\s*", "", x) for x in ident.splitlines()
                 if x.startswith("#")), "")
    title = alnum(field("title"))
    ax, doi = ARXIV_RE.search(ident), DOI_RE.search(ident)
    return {"arxiv": ax.group(1) if ax else "", "doi": doi.group(1).rstrip(".").lower() if doi else "",
            "title": title + "|" + alnum(field("authors?")) if title else alnum(field("identity")) or alnum(head)}


def alnum(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def same_source(k1, k2):
    """arXiv ID when both cards have one, else DOI when both have one, else the title and authors."""
    for key in ("arxiv", "doi"):
        if k1[key] and k2[key]:
            return k1[key] == k2[key]
    return bool(k1["title"]) and k1["title"] == k2["title"]


def index_row(*cells):
    return "| " + " | ".join(cell(x, 200) for x in cells) + " |"


def bound_rows(text):
    """Data rows of a task's bounds.md: table rows (header and separator rows skipped) or plain lines."""
    lines = [x.strip() for x in text.splitlines()]
    sep = [bool(re.fullmatch(r"\|?[\s:|-]*-[\s:|-]*\|?", x)) for x in lines]
    return [x for i, x in enumerate(lines) if x and not x.startswith(("#", "<!--")) and not sep[i]
            and not (x.startswith("|") and i + 1 < len(lines) and sep[i + 1])]


def cmd_file_cards(a):
    """K52: file literature-reviewer outputs: cards to sources/Sxx.md (dedupe: arXiv ID, DOI, title and authors),
    bound rows to sources/bounds.md (NEW- names replaced by Sxx), raw/ downloads to sources/raw/Txxx/; after a
    finished investigator MODEL, a new-source event per new card (K60: none for a bundle file MODEL read as
    uncarded)."""
    run, st = open_run(a)
    T, Q = st["tasks"], st["questions"]
    tids = list(dict.fromkeys(get(st, "tasks", "T", x) for x in a.tids))
    src = Path(run) / "sources"
    idx_p, bnd_p = src / "index.md", src / "bounds.md"
    idx = read(idx_p) or init_files()["sources/index.md"]
    st["counters"]["S"] = max([st["counters"].get("S", 0)] + [int(x) for x in re.findall(r"(?m)^\|\s*S(\d+)\s*\|", idx)])
    stored = {norm_id("S", m.group(1)): m.group(2).strip()
              for m in re.finditer(r"(?m)^\|\s*(S\d+)\s*\|[^|\n]*\|([^|\n]*)\|", idx)}
    have = {norm_id("S", p.stem): card_keys(read(src / p.name)) for p in sorted(xp(src).glob("S*.md"))
            if re.fullmatch(r"S\d+", p.stem, re.I)}
    origin = st.setdefault("source_cards", {})  # Sxx -> the task card it was copied from (never lose a text)
    models = [k for k, t in T.items() if t["role"] == "investigator" and t.get("mode") == "MODEL" and t["status"] in FINISHED]
    uncarded = "\n".join(read(Path(run) / T[k]["packet"]) for k in models)
    stmts = {q: read(Path(run) / "lanes" / q / "statement.md") for q, x in sorted(Q.items()) if x["status"] == "active"}
    rows, bounds, out, manual, filed = [], [], [], [], []
    for tid in tids:
        t = T[tid]
        if t["role"] != "literature-reviewer" or t["status"] not in FINISHED:
            manual.append(f"{tid}: not a finished literature-reviewer task ({t['role']}, {t['status']}): ingest it first")
            continue
        if t.get("filed_seq"):
            manual.append(f"{tid}: already filed (seq {t['filed_seq']}); nothing done")
            continue
        tdir = Path(run) / "tasks" / tid
        names = sorted(task_cards(run, tid), key=lambda n: (n.upper().startswith("NEW-"), n))
        sid_of, new = {}, []
        out.append(f"{tid} literature-reviewer" + (f" {t['mode']}" if t.get("mode") else "") + f": {len(names)} cards")
        for name in names:
            text, size = read(tdir / name), xp(tdir / name).stat().st_size
            keys, stem, here = card_keys(text), name[:-3], f"tasks/{tid}/{name}"
            if stem.upper().startswith("S"):
                sid = norm_id("S", stem)
                if sid not in stored:
                    manual.append(f"{tid}: {name} names {sid}, which has no sources/index.md row; file it by hand")
                    continue
                sid_of[stem], dest = sid, src / f"{sid}.md"
                if not is_file(dest):
                    atomic_write(dest, xp(tdir / name).read_bytes())
                    origin[sid], have[sid] = here, keys
                    new.append((sid, name, stored[sid]))
                    out.append(f"  {sid} <- {here}")
                elif xp(dest).read_bytes() == xp(tdir / name).read_bytes():
                    out.append(f"  {sid}: {here} is identical to the filed card")
                elif size > xp(dest).stat().st_size and origin.get(sid):  # keep the larger; the smaller stays a file
                    old, old_size = origin[sid], xp(dest).stat().st_size
                    atomic_write(dest, xp(tdir / name).read_bytes())
                    origin[sid], have[sid] = here, keys
                    rows.append(index_row("-", f"{Path(old).name} ({old.split('/')[1]})", old, "card", human(old_size),
                                          f"duplicate of {sid}", "-"))
                    out.append(f"  {sid} <- {here} (larger); {old} kept as a duplicate row")
                else:
                    rows.append(index_row("-", f"{name} ({tid})", here, "card", human(size), f"duplicate of {sid}", "-"))
                    out.append(f"  {name}: duplicate of {sid} (the filed card is kept)")
                continue
            match = next((s for s, k in sorted(have.items()) if same_source(keys, k)), None)
            if match:
                sid_of[stem] = match
                rows.append(index_row("-", f"{name} ({tid})", here, "card", human(size), f"duplicate of {match}", "-"))
                out.append(f"  {name}: duplicate of {match}")
                continue
            sid = next_id(st, "S")
            atomic_write(src / f"{sid}.md", xp(tdir / name).read_bytes())
            sid_of[stem], origin[sid], have[sid] = sid, here, keys
            rows.append(index_row(sid, f"{name} ({tid})", f"sources/{sid}.md", "card", human(size), f"card from {tid}", "-"))
            new.append((sid, name, None))
            out.append(f"  {sid} <- {here} (new card)")
        n_b = 0
        for row in bound_rows(read(tdir / "bounds.md")):
            lead = re.sub(r"^[|\s*_>-]*", "", row)  # the row's first token is its card name
            card = next((s for s in sorted(sid_of, key=len, reverse=True)
                         if re.match(re.escape(s) + r"(?![\w-])", lead)), None)
            m = card or re.match(r"S\d+(?![\w-])|NEW-[\w.+-]*[\w+-]", lead)
            for stem, sid in sid_of.items():
                if stem.upper().startswith("NEW-"):
                    row = re.sub(r"(?<![\w-])" + re.escape(stem) + r"(?![\w-])", sid, row)
            if m and not card and m.group(0).upper().startswith("NEW-"):
                manual.append(f"{tid}: bounds.md row names {m.group(0)}, which has no card: {cell(row, 80)}")
                continue
            if not m:
                if len(sid_of) != 1:
                    manual.append(f"{tid}: bounds.md row with no card name: {cell(row, 80)}")
                    continue
                only_sid = next(iter(sid_of.values()))
                row = f"| {only_sid} {row}" if row.startswith("|") else f"{only_sid}: {row}"
            bounds.append(row)
            n_b += 1
        if n_b:
            out.append(f"  bounds: {n_b} rows -> sources/bounds.md")
        rawd = xp(tdir / "raw")
        for p in sorted(rawd.rglob("*")) if rawd.is_dir() else []:
            if not p.is_file():
                continue
            parts = list(p.relative_to(rawd).parts)
            dest = unique_path(src / "raw" / tid / Path(*[safe_name(x) for x in parts]))
            xp(dest.parent).mkdir(parents=True, exist_ok=True)
            atomic_write(dest, p.read_bytes())
            sid = next_id(st, "S")
            rows.append(index_row(sid, f"raw/{'/'.join(parts)} ({tid})", rel(run, dest), file_type(parts[-1:], 1),
                                  human(p.stat().st_size), f"downloaded by {tid}", "-"))
            out.append(f"  {sid} <- tasks/{tid}/raw/{'/'.join(parts)} -> {rel(run, dest)}")
        for sid, name, raw_path in (new if models else []):
            if raw_path and raw_path in uncarded:  # K60: a bundle file MODEL's Assignment named as uncarded
                out.append(f"  {sid}: no new-source event ({raw_path} was an uncarded input of MODEL)")
                continue
            needles = [x for x in (raw_path, have[sid]["arxiv"], have[sid]["doi"]) if x]
            lanes = [q for q, s in stmts.items() if any(x.lower() in s.lower() for x in needles)]
            for lane in lanes or [None]:
                eid = log_event(st, "new-source", lane, f"{sid} filed from {tid} ({name})")
                out.append(f"  {eid} new-source" + (f" {lane} (HELD until RENEW)" if lane else "") + f": {sid}")
        t["filed_seq"] = st["seq"] + 1
        filed.append(tid)
    if filed:
        if rows:
            atomic_write(idx_p, idx.rstrip("\n") + "\n" + "".join(x + "\n" for x in rows))
        if bounds:
            base = read(bnd_p)
            atomic_write(bnd_p, (base.rstrip("\n") + "\n" if base else "# Bounds (rows filed by ri.py file-cards; card "
                                 "names as Sxx)\n\n") + "".join(x + "\n" for x in bounds))
        commit(run, st, "file-cards", {"tasks": filed, "rows": len(rows), "bounds": len(bounds)})
    print("\n".join(out) if out else "nothing filed")
    if manual:
        print("manual (handle by hand):\n" + "\n".join(f"  - {m}" for m in manual))


# ---------------------------------------------------------------- intake (B6)

ARCHIVE_RE = re.compile(r"\.(zip|tar|tgz|tbz2|txz|tar\.gz|tar\.bz2|tar\.xz)$", re.I)
WIN_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)}
TYPE_EXT = {
    "paper-pdf": (".pdf",),
    "tex": (".tex", ".bib", ".bbl", ".sty", ".cls"),
    "notes": (".md", ".txt", ".rst", ".org", ".html", ".htm"),
    "code": (".py", ".ipynb", ".c", ".cc", ".cpp", ".h", ".hpp", ".java", ".js", ".ts", ".m", ".jl", ".r",
             ".rs", ".go", ".sh", ".sage", ".mpl", ".nb", ".hs", ".ml", ".lean", ".v", ".gp", ".mod"),
    "data": (".csv", ".tsv", ".json", ".jsonl", ".xlsx", ".xls", ".dat", ".npy", ".npz", ".mat", ".parquet",
             ".pkl", ".h5", ".hdf5", ".yaml", ".yml", ".xml", ".lp", ".mps", ".cnf"),
}
PER_FILE_MB, MAX_RATIO, PATH_BUDGET = 200, 200, 1000  # PATH_BUDGET: absurd lengths only (xp passes MAX_PATH)
# The leading word must end at a non-letter: plan.md and ideas.md match; planar-graphs.pdf and ideal.pdf do not.
USER_NOTES_RE = re.compile(r"(readme|notes|brief(ing)?s?|ideas?|todos?|plans?|questions?|directions?)(?![a-z])"
                           r"|.*(-notes|_notes|notes-|notes_)", re.I)
# K28: intent files below the top level (a text file at most two folders deep), by name or by folder.
NOTES_WORDS_RE = re.compile(r"(guides?|start[-_ ]?here|overview|status|roadmap|next[-_ ]?steps?|handoff|scope|conjectures?"
                            r"|agent[-_ ]?brief|chat|conversation|transcripts?|prompts?)(?![a-z])", re.I)
NOTES_DIRS_RE = re.compile(r"guides?|notes|directions?|conjectures?|handoff|briefs?|overview", re.I)
PAPER_LIKE_RE = re.compile(r"\d{4}\.\d{4,5}|paper|arxiv", re.I)


def archive_members(path):
    """([(name, size, compressed size, kind, opener)], handle); kind: file, dir, link or special."""
    p = str(xp(path))
    if zipfile.is_zipfile(p):
        zf = zipfile.ZipFile(p)
        out = []
        for zi in zf.infolist():
            ft = (zi.external_attr >> 16) & 0o170000
            kind = ("dir" if zi.is_dir() else "link" if ft == 0o120000
                    else "file" if ft in (0, 0o100000) else "special")
            out.append((zi.filename, zi.file_size, zi.compress_size, kind, lambda zi=zi: zf.open(zi)))
        return out, zf
    try:
        tf = tarfile.open(p)
    except (tarfile.TarError, OSError):
        usage(f"{path} is not a zip or tar archive")
    out = []
    for ti in tf.getmembers():
        kind = ("dir" if ti.isdir() else "file" if ti.isreg()
                else "link" if (ti.issym() or ti.islnk()) else "special")
        out.append((ti.name, ti.size, None, kind, lambda ti=ti: tf.extractfile(ti)))
    return out, tf


def unsafe_entry(name, kind):
    n = name.replace("\\", "/")
    if kind == "link":
        return "symbolic or hard link"
    if kind == "special":
        return "device or special file"
    if n.startswith("/") or re.match(r"[A-Za-z]:", n):
        return "absolute path"
    if ".." in n.split("/"):
        return "'..' path component"
    return None


def safe_name(part):
    s = re.sub(r'[<>:"|?*\x00-\x1f]', "_", part).rstrip(" .") or "_"
    return "_" + s if s.split(".")[0].upper() in WIN_RESERVED else s


def unique_path(p):
    if not exists(p):
        return p
    stem, suf = (p.name[:-len(ARCHIVE_RE.search(p.name).group(0))], ARCHIVE_RE.search(p.name).group(0)) \
        if ARCHIVE_RE.search(p.name) else (p.stem, p.suffix)
    i = 2
    while exists(p.parent / f"{stem}-{i}{suf}"):
        i += 1
    return p.parent / f"{stem}-{i}{suf}"


def file_type(rel_parts, depth):
    """Type by extension (rel_parts: the bundle-relative path). user-notes, never for code, data, archives or
    paper-like names (K28): rule 1, a top-level file named like the user's notes (USER_NOTES_RE); rule 2, a text
    file at most two folders deep named like a guide, status or brief (NOTES_WORDS_RE) or inside a folder named
    like one (NOTES_DIRS_RE). Any other top-level .md or .txt file is text. Rule 3 (README targets): cmd_intake."""
    name = rel_parts[-1]
    ext = Path(name).suffix.lower()
    typ = "archive" if ARCHIVE_RE.search(name) else next((t for t, exts in TYPE_EXT.items() if ext in exts), "other")
    if depth == 0:
        intent = typ not in ("code", "data", "archive") and not PAPER_LIKE_RE.search(name)
        if intent and len(rel_parts) == 1 and USER_NOTES_RE.match(name):
            return "user-notes"
        if intent and typ == "notes" and len(rel_parts) <= 3 and (
                NOTES_WORDS_RE.match(name) or (len(rel_parts) > 1 and NOTES_DIRS_RE.fullmatch(rel_parts[-2]))):
            return "user-notes"
        if len(rel_parts) == 1 and ext in (".md", ".txt"):
            return "text"
    return typ


def human(n):
    return f"{n} B" if n < 1024 else f"{n / 1024:.1f} KB" if n < 1 << 20 else f"{n / (1 << 20):.1f} MB"


def member_parts(name):
    return [x for x in str(name).replace("\\", "/").split("/") if x not in ("", ".")]


def under_prefix(parts, prefix):
    return parts[:len(prefix)] == prefix


def readme_targets(run, readme):
    """K28 rule 3: stored paths (relative to RUN) that a top-level README points to: markdown links, backticked
    relative paths, and the rest of a 'START HERE' line."""
    text = read(readme)
    toks = (re.findall(r"\]\(\s*<?([^)\s>]+)", text) + re.findall(r"`([^`\s]+)`", text)
            + re.findall(r"(?i)start here\W+(\S+)", text))
    out = set()
    for tok in toks:
        tok = urllib.parse.unquote(tok.strip("<>()[]`'\"").split("#")[0].split("?")[0]).rstrip(".,;:")
        if not tok or "://" in tok or tok.startswith(("/", "\\", "mailto:")) or re.match(r"[A-Za-z]:", tok):
            continue
        out.add(rel(run, os.path.normpath(os.path.join(os.fspath(Path(readme).parent), tok))))
    return out


def add_contract_limit(run, line, section="Limits"):
    """Append one line to a contract.md section: '## Limits' (the intake-cap and bundled-code lines) or '## Mode'
    (a conversion after a focused delivery)."""
    cp = Path(run) / "contract.md"
    if not is_file(cp):
        return False
    text = read(cp)
    head = rf"(?m)^## {re.escape(section)}[^\n]*\n"
    m = re.search(head, text)
    if not m:
        text = text.rstrip("\n") + f"\n\n## {section}\n"
        m = re.search(head, text)
    nxt = re.search(r"(?m)^## ", text[m.end():])
    end = m.end() + nxt.start() if nxt else len(text)
    body = text[m.end():end].rstrip("\n")
    atomic_write(cp, text[:m.end()] + (body + "\n" if body else "") + line + "\n" + ("\n" if nxt else "") + text[end:])
    return True


def extract_archive(run, st, arc, prefix, label, depth, ctx):
    """Extract one archive level under sources/raw/<prefix> with the B6 checks; nested archives once."""
    raw = Path(run) / "sources" / "raw"
    members, handle = archive_members(arc)
    only = ctx.get("only") if depth == 0 else None
    with handle:
        ok, named = [], []
        for name, size, csize, kind, opener in members:
            if kind == "dir":
                continue
            why = unsafe_entry(name, kind)
            if not why:
                named.append(member_parts(name))
            if only and not any(under_prefix(member_parts(name), p) for p in only):
                ctx["skipped"] += 1  # K38: outside --only, not extracted
                continue
            if not why and csize is not None and size > (1 << 20) and size > MAX_RATIO * max(csize, 1):
                why = f"compression ratio above {MAX_RATIO}:1"
            if not why and size > ctx["per_file"]:
                why = f"larger than {ctx['per_file'] >> 20} MB"
            if why:
                ctx["rejected"].append(f"{label}{name}: {why}")
            else:
                ok.append((name, size, opener))
        split = [member_parts(n) for n, _, _ in ok]
        basis = named if only else split  # with --only, the bundle root is that of the whole archive
        firsts = {p[0] for p in basis if p}
        root_len = 1 if len(firsts) == 1 and all(len(p) > 1 for p in basis) else 0
        if only and not ok:
            fail(f"no extractable member of {arc.name} is under --only {' '.join('/'.join(p) for p in only)}; "
                 f"top-level entries: {', '.join(sorted({'/'.join(p[:root_len + 1]) for p in named if p})[:12])}")
        if ctx["total"] + sum(s for _, s, _ in ok) > ctx["max"]:
            parts_mb = ""
            if depth == 0:
                big = {}
                for (_, s, _), p in zip(ok, split):
                    key = "/".join(p[:root_len + 1]) + ("/" if len(p) > root_len + 1 else "")
                    big[key] = big.get(key, 0) + s
                top = sorted(big.items(), key=lambda kv_: -kv_[1])[:5]
                parts_mb = "; largest parts: " + ", ".join(f"{k} ({human(s)})" for k, s in top)
            fail(f"archive {label or arc.name} declares {sum(s for _, s, _ in ok) >> 20} MB: over the "
                 f"{ctx['max'] >> 20} MB cap. Extract part with --only <path prefix>, or raise --max-mb only for a "
                 f"genuine bundle (it is recorded in contract.md){parts_mb}")
        for (name, size, opener), parts in zip(ok, split):
            if not parts:
                continue
            safe = [safe_name(x) for x in parts]
            dest = unique_path(raw / prefix / Path(*safe))
            sid = fmt_id("S", st["counters"].get("S", 0) + 1)
            if len(str(apath(dest))) > PATH_BUDGET or max(map(len, safe)) > 255:  # 255: file system name limit
                short = safe[-1][-60:]
                dest = unique_path(raw / prefix / f"{sid}-{short}")
                if len(str(apath(dest))) > PATH_BUDGET:
                    ctx["rejected"].append(f"{label}{name}: path too long even when shortened (use a shorter RUN)")
                    continue
            xp(dest.parent).mkdir(parents=True, exist_ok=True)
            n = 0
            try:
                with opener() as src, open(xp(dest), "wb") as fo:
                    ctx["written"].append(dest)
                    for chunk in iter(lambda: src.read(1 << 20), b""):
                        n += len(chunk)
                        if n > ctx["per_file"] or ctx["total"] + n > ctx["max"]:
                            fail(f"{label}{name}: actual size passes the cap (declared {size} bytes): "
                                 "archive refused")
                        fo.write(chunk)
            except (zipfile.BadZipFile, tarfile.TarError, OSError, RuntimeError) as e:
                ctx["rejected"].append(f"{label}{name}: unreadable ({e})")
                if exists(dest):
                    xp(dest).unlink()
                continue
            ctx["total"] += n
            st["counters"]["S"] = st["counters"].get("S", 0) + 1
            stored = rel(run, dest)
            if "/".join(safe) != "/".join(parts) or Path(stored).name != parts[-1]:
                ctx["renamed"].append(f"{label}{name} -> {stored}")
            row = [sid, label + name, stored, file_type(parts[root_len:], depth), human(n), "readable", "-"]
            ctx["rows"].append(row)
            if depth == 0 and len(parts) - root_len == 1 and re.match(r"readme(?![a-z])", parts[-1], re.I):
                ctx["readmes"].append(dest)
            if ARCHIVE_RE.search(dest.name):
                if depth == 0:
                    sub = dest.parent / dest.name[:-len(ARCHIVE_RE.search(dest.name).group(0))]
                    sub = unique_path(sub) if exists(sub) else sub
                    try:
                        extract_archive(run, st, dest, sub.relative_to(raw), f"{label}{name}:", 1, ctx)
                        row[5] = f"extracted to {rel(run, sub)}/"
                    except RiError as e:
                        if e.code == 1 and "cap" in str(e):
                            raise
                        row[5] = "not extracted (unreadable archive)"
                else:
                    row[5] = "not extracted (nested deeper than one level)"


def cmd_intake(a):
    run, st = open_run(a)
    arc = find_input(run, a.archive)
    if a.max_mb < 1:
        usage("--max-mb must be >= 1")
    idx = run / "sources" / "index.md"
    text = read(idx) or init_files()["sources/index.md"]
    seen = [int(x) for x in re.findall(r"(?m)^\|\s*S(\d+)\s*\|", text)]
    st["counters"]["S"] = max([st["counters"].get("S", 0)] + seen)
    mx = a.max_mb << 20
    only = [member_parts(p) for p in a.only or []]
    if any(not p or ".." in p for p in only):
        usage("--only needs a path prefix inside the archive, such as bundle/docs")
    ctx = {"total": 0, "max": mx, "per_file": min(mx, PER_FILE_MB << 20), "rows": [], "rejected": [],
           "renamed": [], "written": [], "only": only, "skipped": 0, "readmes": []}
    try:
        extract_archive(run, st, arc, Path(), "", 0, ctx)
    except BaseException:
        for p in ctx["written"]:
            try:
                xp(p).unlink()
            except OSError:
                pass
        raise
    targets = set().union(*(readme_targets(run, r) for r in ctx["readmes"]))
    for r in ctx["rows"]:  # K28 rule 3: a text file the top-level README points to
        if r[2] in targets and r[3] in ("notes", "text") and not PAPER_LIKE_RE.search(Path(r[2]).name):
            r[3] = "user-notes"
    rows = ["| " + " | ".join(cell(x, 200) for x in r) + " |" for r in ctx["rows"]]
    atomic_write(idx, text.rstrip("\n") + "\n" + "".join(x + "\n" for x in rows))
    limits = []
    if a.max_mb > 500 and rows:
        limits.append(f"- Intake cap raised to {a.max_mb} MB (default 500) on {now()[:10]}; tell the user.")
    code = sum(r[3] == "code" for r in ctx["rows"])
    ask = code and not re.search(r"(?im)^\W*Bundled code:", read(run / "contract.md"))
    if ask:
        limits.append(f"- Bundled code: not asked ({code} code files; runtime.md §1)")
    limits = [x for x in limits if add_contract_limit(run, x)]
    commit(run, st, "intake", {"archive": arc.name, "files": len(rows), "rejected": ctx["rejected"],
                               "renamed": ctx["renamed"], "only": a.only, "max_mb": a.max_mb if a.max_mb != 500 else None,
                               "skipped": ctx["skipped"], "contract": limits})
    ids = [r[0] for r in ctx["rows"]]
    notes = [r[2] for r in ctx["rows"] if r[3] == "user-notes"]
    print(f"intake {arc.name}: {len(rows)} files into sources/raw/" + (f" ({ids[0]}-{ids[-1]})" if ids else "")
          + f"; {human(ctx['total'])}; rejected {len(ctx['rejected'])}; renamed {len(ctx['renamed'])}"
          + (f"; skipped {ctx['skipped']} outside --only" if only else ""))
    for x in ctx["rejected"]:
        print(f"rejected: {x}")
    for x in ctx["renamed"]:
        print(f"renamed: {x}")
    if notes:
        print("user-notes (read in full; they state the user's intent): " + ", ".join(notes))
    for x in limits:
        print(f"contract.md Limits: {x[2:]}")
    if ask and any("Bundled code" in x for x in limits):
        print(f"bundle holds {code} code files: ask once in your opening message whether scouts may run copies in "
              "their task directory; proceed meanwhile")


# ---------------------------------------------------------------- progress.md lint (K07, K08)

HTML_TAGS = {"a", "b", "i", "u", "em", "strong", "br", "hr", "p", "div", "span", "sub", "sup", "img", "code", "pre",
             "kbd", "details", "summary", "table", "tr", "td", "th", "ul", "ol", "li", "svg", "g", "path", "rect",
             "line", "circle", "ellipse", "polyline", "polygon", "text", "tspan", "defs", "marker", "title", "desc"}
RUNON_ALLOW = ("sha256", "utf8", "log2", "log10", "l1", "l2")
I5_RE = re.compile(r"\b(?:conjecture|numerical evidence|candidate|self-checked|agent-checked|machine-checked|"
                   r"expert-verified)\b|cited \(", re.I)
CLAIM_RE = re.compile(r"\b(?:proved|verified|novel|improve[sd]|is new|new (?:result|bound|theorem|construction|"
                      r"proof)s?)\b", re.I)
INLINE_RE = re.compile(r"`[^`\n]*`|\$[^$\n]+\$")  # inline code and inline maths


def log_time(run, seq):
    """The log.jsonl time of command seq as a POSIX timestamp, or None."""
    for line in read(Path(run) / "log.jsonl").splitlines():
        m = re.match(r'\{"seq": (\d+), "time": "([^"]+)"', line)
        if m and int(m.group(1)) == seq:
            return datetime.datetime.strptime(m.group(2), "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=datetime.timezone.utc).timestamp()
    return None


def prose_lines(text):
    """Lines of text outside fenced code blocks and HTML comments."""
    out, fence = [], None
    for line in re.sub(r"<!--.*?-->", "", text, flags=re.S).splitlines():
        m = re.match(r"\s*(```|~~~)", line)
        if m:
            fence = None if fence == m.group(1) else fence or m.group(1)
        elif not fence:
            out.append(line)
    return out


def reader_sections(lines):
    """[(name, lines)] of the sections the user reads first: '## 1.' to '## 4.' and 'How I read your
    request', each with its subsections."""
    out, cur, level = [], None, 0
    for line in lines:
        hm = re.match(r"\s*(#{1,6})\s+(.*)", line)
        if not hm:
            if cur:
                cur[1].append(line)
            continue
        if cur and len(hm.group(1)) > level:
            continue
        cur, level = None, len(hm.group(1))
        num = re.match(r"([1-4])\.", hm.group(2))
        if num or "how i read your request" in hm.group(2).lower():
            cur = (f"sec. {num.group(1)}" if num else "'How I read your request'", [])
            out.append(cur)
    return out


def sentence_units(lines):
    """(text, table row?) units of prose: paragraphs and list items split into sentences; table rows whole;
    display maths ($$ or \\[ blocks) skipped; inline code and maths replaced by one token."""
    units, para, maths = [], [], False

    def flush():
        if para:
            units.extend((s, False) for s in re.split(r"(?<=[.!?])\s+", INLINE_RE.sub("X", " ".join(para))) if s)
            para.clear()

    for line in lines:
        s = line.strip()
        if maths:
            maths = not (s.endswith("$$") or s.endswith("\\]"))
            continue
        if s.startswith(("$$", "\\[")):
            flush()
            maths = len(s) <= 2 or not (s.endswith("$$") or s.endswith("\\]"))
        elif not s:
            flush()
        elif s.startswith("|"):
            flush()
            units.append((INLINE_RE.sub("X", s), True))
        else:
            item = re.match(r"(?:[-*+]|\d+[.)])\s+", s)
            if item:
                flush()
            para.append(s[item.end():] if item else s)
    flush()
    return units


def progress_findings(run, st):
    """K08 lint of progress.md (warnings only): template text, staleness against the last acceptance, and in
    the sections the user reads first: bare task/candidate/event IDs, sentences over 30 words, letter-digit
    run-ons, and result words without an I5 label."""
    p = Path(run) / "progress.md"
    if not is_file(p):
        return ["progress.md is missing"]
    text, C, T = read(p), st["candidates"], st["tasks"]
    lines, out = prose_lines(text), []
    holes = [m.group(0) for m in re.finditer(r"<([A-Za-z][\w-]*)(?:[^<>\n]|\n(?!\s*\n))*>",
                                             "\n".join(INLINE_RE.sub("", x) for x in lines))
             if m.group(1).lower() not in HTML_TAGS and "://" not in m.group(0) and "@" not in m.group(0)]
    if holes:
        out.append(f"template text left: {cell(holes[0], 60)!r}"
                   + (f" and {len(holes) - 1} more" if len(holes) > 1 else ""))
    acc = sorted((c.get("accepted_seq") or 0, k) for k, c in C.items() if c["status"] == "accepted")
    if acc and "(nothing established yet)" in text:
        out.append(f"'(nothing established yet)' while {acc[-1][1]} is accepted")
    model = [k for k, t in sorted(T.items()) if t["role"] == "investigator" and t.get("mode") == "MODEL"
             and t["status"] in FINISHED and is_file(Path(run) / "tasks" / k / "reading.md")]
    if model and "(not yet drawn)" in text:
        out.append(f"'(not yet drawn)' while {model[-1]} returned reading.md")
    when = log_time(run, acc[-1][0]) if acc else None
    if when and xp(p).stat().st_mtime < when:
        out.append(f"older than the last acceptance ({acc[-1][1]}): rewrite it whole")
    for name, body in reader_sections(lines):
        for s, row in sentence_units(body):
            ids = [m.group(0) for m in re.finditer(r"\b(?:T\d{3,}|C\d{3,}|E\d+)\b", s)
                   if not re.search(r"\baudit\s+$", s[:m.start()])]  # 'conjecture (audit Txxx; ...)' is a label
            if ids:
                out.append(f"bare IDs {', '.join(dict.fromkeys(ids))} in {name}: say what each is in plain words")
            n = len(s.split())
            if n > 30 and not row:
                out.append(f"a {n}-word sentence in {name} (at most 30): {cell(s, 60)!r}")
            runons = [w for w in re.findall(r"\b[a-z]{2,}\d[\d,.]*\b", s) if w.lower() not in RUNON_ALLOW]
            if runons:
                out.append(f"run-on {', '.join(dict.fromkeys(runons))} in {name}: a space between word and number")
            claim = CLAIM_RE.search(s)
            if claim and not I5_RE.search(s):
                out.append(f"{claim.group(0)!r} without an I5 label or 'cited (' in {name}: {cell(s, 60)!r}")
    return out


# ---------------------------------------------------------------- status and suggested actions

def lane_tasks(st, qid, rnd):
    return {k: t for k, t in st["tasks"].items() if t.get("lane") == qid and t.get("round") == rnd}


def in_flight(st, cid, scope):
    """A live review task aimed at cid (via --cand or a C-ID in its title) for this scope."""
    for k, t in st["tasks"].items():
        if t["status"] in LIVE and MODE_SCOPE.get(t.get("mode") or "") == scope:
            named = {fmt_id("C", int(x)) for x in re.findall(r"\bC(\d+)\b", t.get("title") or "")}
            if cid in set(t.get("cands") or []) | named:
                return k
    return None


def lane_stage(st, qid):
    q = st["questions"][qid]
    rnd = q["round"]
    if rnd == 0:
        return "PLAN"
    ts = lane_tasks(st, qid, rnd).values()
    if is_gate_only(q, rnd):  # no PLAN, BRIEF or PROVE: verify the skeptic's argument, then close
        ks = [k for k, c in st["candidates"].items() if c.get("lane") == qid and c.get("round") == rnd
              and c["status"] == "proposed" and not superseded_by(st, k)]
        live = any(t["role"] in ("verifier", "scout") and t["status"] in LIVE for t in ts)
        return "VERIFY" if live or any(missing_scopes(st, k) for k in ks) else "CLOSE"
    live, roles = {t["role"] for t in ts if t["status"] in LIVE}, {t["role"] for t in ts}
    for stage, rs in (("VERIFY", {"verifier", "scout"}), ("PROVE", {"prover"}), ("BRIEF", {"summarizer"}),
                      ("CLOSE", {"ledger-auditor", "process-advisor"})):
        if live & rs:
            return stage
    if "prover" not in roles:
        return "BRIEF" if "summarizer" in roles else "PLAN"
    waiting = [k for k in cohort(st, qid, rnd) if st["candidates"][k]["status"] == "proposed"
               and not superseded_by(st, k) and missing_scopes(st, k)]
    return "VERIFY" if waiting else "CLOSE"


def round1_gate(st, qid):
    """Fast start (program.md sec. 6.1): (task, verdict code or None) of the gate that releases round 1's provers -
    the latest skeptic gate on qid created before round 1 opened, else the first one created after it (a later gate,
    e.g. on MODEL's statement, acts at the next round boundary). None outside round 1 or with no such gate."""
    q = st["questions"][qid]
    opened = (q.get("round_seqs") or {}).get("1")
    if q["round"] != 1 or opened is None:
        return None
    gates = sorted((t.get("created_seq", 0), k) for k, t in st["tasks"].items() if t["role"] == "skeptic"
                   and t.get("mode") in ("QUESTION-GATE", "MODEL-GATE") and qid in (t.get("questions") or [])
                   and t["status"] not in GONE)
    before, after = [k for n, k in gates if n < opened], [k for n, k in gates if n >= opened]
    k = before[-1] if before else after[0] if after else None
    if k is None:
        return None
    return k, next((v["code"] for v in reversed(q.get("verdicts") or []) if v["task"] == k), None)


def gate_summary(st, cid):
    scopes = []
    for need in needed_scopes(st, cid):
        scopes += list(need) if isinstance(need, tuple) else [need]
    scopes += [r["scope"] for r in reviews_of(st, cid)]
    parts = []
    for s in dict.fromkeys(scopes):
        got = [f"{effective_verdict(r)}({r['task']}{', salvage' if is_salvage(st, r) else ''})"
               for r in reviews_of(st, cid) if r["scope"] == s]
        parts.append(f"{s} {','.join(got) or '-'}")
    return " ".join(parts)


def round_closed(st, qid, rnd):
    q = st["questions"].get(qid)
    if q is None or rnd is None:
        return False
    if q["status"] != "active" or rnd < q["round"]:
        return True
    return rnd == q["round"] and lane_stage(st, qid) == "CLOSE" and not any(
        t["status"] in LIVE for t in lane_tasks(st, qid, rnd).values())


def lane_over(st, qid):
    """The lane ended (resolved, refuted, killed, parked) or its last round ended it (R1 accepted or excluded)."""
    q = st["questions"].get(qid)
    if q is None or q["status"] in LANE_ENDED:
        return True
    return best_rung(st, qid)[0] == "R1" or any(
        e["kind"] == "exclusion" and e["status"] == "active" and covers(e)[0].startswith(qid + ".")
        for e in st["ledger"].values())


def advisor_due(st):
    """E10: closed rounds of lanes still running, with reviews newer than the last process-advisor task
    (run-wide; cancelled, superseded or withdrawn advisor tasks do not count)."""
    advs = [t for t in st["tasks"].values()
            if t["role"] == "process-advisor" and t["status"] not in GONE]
    if any(t["status"] in LIVE for t in advs):
        return []
    last = max([t.get("created_seq", 0) for t in advs], default=0)
    rounds = set()
    for r in st["reviews"]:
        c = st["candidates"].get(r["cand"], {})
        if r["seq"] > last and c.get("lane") and not lane_over(st, c["lane"]):
            rounds.add((c["lane"], c.get("round")))
    return sorted(x for x in rounds if round_closed(st, *x))


def finished_seq(t):
    """When a finished task counts as finished: its ingest, else (status set by hand) its creation."""
    return t.get("ingested_seq") or t.get("created_seq", 0)


def finished_since(st, seq, exclude_role=None):
    """Finished tasks (done, partial, blocked) that finished after seq, in ID order."""
    return sorted(k for k, t in st["tasks"].items() if t["status"] in FINISHED and finished_seq(t) > seq
                  and t["role"] != exclude_role)


def first_select_seq(st):
    """The seq at which the first investigator SELECT finished, or None while none has."""
    seqs = [finished_seq(t) for t in st["tasks"].values()
            if t["role"] == "investigator" and t.get("mode") == "SELECT" and t["status"] in FINISHED]
    return min(seqs) if seqs else None


def last_advisor(st, exclude=None):
    """(created_seq, task) of the latest process-advisor task that counts (not cancelled, superseded or
    withdrawn), or (0, None)."""
    advs = [(t.get("created_seq", 0), k) for k, t in st["tasks"].items()
            if t["role"] == "process-advisor" and t["status"] not in GONE and k != exclude]
    return max(advs) if advs else (0, None)


def advisor_runwide_due(st):
    """K41: why a run-wide process advisor is due, or None. Only while no advisor is live and no lane round
    is waiting for one: after the first SELECT when no advisor has run, else 20 tasks after the last one."""
    seq, prev = last_advisor(st)
    if any(t["role"] == "process-advisor" and t["status"] in LIVE for t in st["tasks"].values()) or advisor_due(st):
        return None
    if prev is None:
        return "the first SELECT finished and no advisor has run" if first_select_seq(st) is not None else None
    n = len(finished_since(st, seq, exclude_role="process-advisor"))
    return f"{n} tasks finished since advisor {prev}" if n >= 20 else None


def breadth_tasks_due(st):
    """K54: (count, since) when 30 tasks have finished since the later of the first SELECT and the last
    breadth-review event, else None."""
    sel = first_select_seq(st)
    if sel is None:
        return None
    seqs = [e["seq"] for e in st["events"] if e["type"] == "breadth-review" and e["seq"] > sel]
    n = len(finished_since(st, max(seqs, default=sel)))
    return (n, "the last breadth review" if seqs else "the first SELECT") if n >= 30 else None


def opening_budget(st):
    """K06: warnings when the opening (program mode, before the first SELECT) exceeds investigator.md MODEL's
    budget: at most 4 TRANSFER-AUDITs and 2 scout EXPLOREs (ANCHOR not counted)."""
    ts = [t for t in st["tasks"].values() if t["status"] not in ("superseded", "withdrawn")]
    audits = sum(t["role"] == "literature-reviewer" and t.get("mode") == "TRANSFER-AUDIT" for t in ts)
    scouts = sum(t["role"] == "scout" and t.get("mode") == "EXPLORE"
                 and not (t.get("title") or "").strip().upper().startswith("ANCHOR") for t in ts)
    return [f"opening budget: {n} {what} before the first SELECT (cap {cap}; investigator.md MODEL)"
            for n, what, cap in ((audits, "TRANSFER-AUDITs", 4), (scouts, "scout EXPLOREs (not ANCHOR)", 2)) if n > cap]


def round_progress(st, qid, rnd, prior_tags):
    """E7: (progress?, tags) of a lane round: a new accepted rung, a new ledger entry or a new objection TAG."""
    C = st["candidates"]
    ks = {k for k, c in C.items() if c.get("lane") == qid and c.get("round") == rnd}
    tags = {split_objection(o["text"])[1] for r in st["reviews"] if r["cand"] in ks for o in r["objections"]} - {""}
    acc = any(C[k]["status"] == "accepted" and C[k]["kind"] in RUNG_KINDS + ("counterexample",) for k in ks)
    led = any(e["cand"] in ks for e in st["ledger"].values())
    return bool(acc or led or (tags - prior_tags)), tags


def stall_hint(st, qid):
    q = st["questions"][qid]
    last = q["round"] if lane_stage(st, qid) == "CLOSE" else q["round"] - 1
    if last < 2 or q.get("held_by"):
        return None
    tags, prog = set(), {}
    for i in range(1, last + 1):
        prog[i], t = round_progress(st, qid, i, tags)
        tags |= t
    if prog[last] or prog[last - 1]:
        return None
    start = (q.get("round_seqs") or {}).get(str(last - 1), 0)
    if any(e["type"] == "stall" and e.get("lane") == qid and e["seq"] >= start for e in st["events"]):
        return None
    return (f"{qid}: no progress in rounds {last - 1} and {last} (no new accepted rung, ledger entry or objection "
            f"tag) - event --type stall --lane {qid}")


def needs_auditor(st, qid, rnd):
    """Round close: confirmed steps in a draft not accepted, and no ledger auditor yet for the round."""
    ks = {k for k in cohort(st, qid, rnd) if st["candidates"][k]["status"] != "accepted"}
    return (any(r.get("confirmed") for r in st["reviews"] if r["cand"] in ks)
            and not any(t["role"] == "ledger-auditor" for t in lane_tasks(st, qid, rnd).values()))


def round_close_pending(st, qid, r):
    """E5: round r's close work still outstanding (BRIEF of round r+1 waits for it)."""
    lt = lane_tasks(st, qid, r)
    out = [f"{k} {t['role']}" for k, t in sorted(lt.items()) if t["status"] in LIVE and (
        t["role"] == "ledger-auditor" or (t["role"] == "verifier" and t.get("mode") == "ISOLATED"))]
    if needs_auditor(st, qid, r):
        out.append("ledger auditor")
    out += [f"ISOLATED review of {k}" for k, c in sorted(st["candidates"].items())
            if c.get("lane") == qid and c.get("round") == r and is_fragment(c) and c["status"] == "proposed"
            and missing_scopes(st, k) and not in_flight(st, k, "isolated")]
    if (qid, r) in advisor_due(st) or any(t["role"] == "process-advisor" and t["status"] in LIVE for t in st["tasks"].values()):
        out.append("process advisor")
    return out


def close_steps(st, qid, rnd):
    q = st["questions"][qid]
    steps = []
    if needs_auditor(st, qid, rnd):
        steps.append(f"ledger auditor on confirmed steps (task new --role ledger-auditor --lane {qid} --round {rnd})")
    if q.get("held_by"):
        return steps
    if budget_used(q, rnd) >= lane_budget(st, q) and not any(
            e["type"] == "lane-budget" and e.get("lane") == qid and not e.get("handled_by") for e in st["events"]):
        steps.append(f"lane budget reached: event --type lane-budget --lane {qid}")
    elif is_gate_only(q, rnd):
        steps.append(f"gate-only round, R1 not accepted: the lane runs normally from round {rnd + 1} when the lane "
                     f"cap allows (program.md sec. 5.3): round {qid} --open; until then q set {qid} --status ready")
    else:
        steps.append(f"plan round {rnd + 1} (round {qid} --open)")
    return steps


def suggest_tasks(run, st, add, quiet):
    for k, t in sorted(st["tasks"].items()):
        has_res = is_file(Path(run) / "tasks" / k / "result.md")
        s = t["status"]
        if s == "withdrawn":  # never spawned: nothing to reconcile
            continue
        if s == "superseded":
            if has_res and not t.get("late_result_seen"):
                add(f"{k} (superseded by {t.get('superseded_by')}): late result.md - extra evidence: file, do not "
                    f"re-ingest (ingest {k} records that)")
            continue
        if has_res and not t.get("ingested_seq") and s not in FINISHED:
            add(f"{k}: result.md present - ingest RUN {k}")
        elif s == "unknown":  # under STOP or PAUSE nothing is dispatched (runtime.md sec. 5)
            add(f"{k}: status unknown - leave it; reconcile after the STOP or PAUSE is lifted" if quiet else
                f"{k}: status unknown - worker alive -> wait; else task new --redo {k} --start")
        elif s == "cancelled" and not quiet:  # e.g. by a STOP: reconcile on resume (runtime.md sec. 6, step 4)
            add(f"{k}: cancelled {t['role']} - reconcile: worker alive -> wait; else task new --redo {k} --start")
        elif s == "queued":
            tdir = Path(run) / "tasks" / k
            outputs = xp(tdir).is_dir() and any(not PACKET_FILE_RE.fullmatch(p.name) for p in xp(tdir).iterdir())
            if outputs:
                add(f"{k}: queued but has outputs - possibly dispatched: reconcile (worker alive -> wait; "
                    f"else task new --redo {k}); never re-dispatch into it")
            elif not quiet:
                todo = "fill the Assignment, then " if PLACEHOLDER in read(Path(run) / t["packet"]) else ""
                add(f"{k}: queued {t['role']} - {todo}task set {k} running, then dispatch")


def focused_end(run, st, qid):
    """Focused mode (SKILL.md sec. 5): why lane qid is at its end - resolved, refuted, or its target rung
    accepted or excluded (target: the statement's 'D refutes: Rt' line, else the lane's rung, else R1)."""
    q = st["questions"].get(qid or "")
    if st["mode"] != "focused" or not q:
        return None
    if q["status"] in ("resolved", "refuted"):
        return q["status"]
    best, cid = best_rung(st, qid)
    target = target_rung(run, st, qid)
    if best and int(best[1:]) <= int(target[1:]):
        return f"{best} accepted ({cid}; target {target})"
    lid = excluded_by(st, f"{qid}.{target}")
    return f"target {target} excluded ({lid})" if lid else None


def target_rung(run, st, qid):
    """A focused lane's target rung: the statement's 'D refutes: Rt' line, else the lane's rung, else R1."""
    q = st["questions"].get(qid or "") or {}
    m = re.search(r"(?i)\bD refutes\s*:\s*(R\d+)\b", read(Path(run) / "lanes" / qid / "statement.md")) if qid else None
    return m.group(1).upper() if m else q.get("rung") if re.fullmatch(r"R\d+", q.get("rung") or "") else "R1"


def focused_context(st, e):
    """Focused mode: a literature-hit or new-source logged without --lane is context, not a hold (program.md
    sec. 3): no RENEW; it goes to the lane's next summarizers and the closing CLAIM-GATE."""
    return st["mode"] == "focused" and not e.get("lane") and e["type"] in ("literature-hit", "new-source")


def event_action(st, etype, lane=None):
    """The mechanical first action of an event type (EVENT_ACTIONS), with focused mode's own routes."""
    if st["mode"] == "focused":
        if etype == "question-verdict":
            return FOCUSED_VERDICT
        if etype == "refuted":
            return FOCUSED_REFUTED
        if etype in ("literature-hit", "new-source") and not lane:
            return FOCUSED_CONTEXT
    return EVENT_ACTIONS[etype]


def focused_question(st):
    """Focused mode: the question the run is on - the highest-numbered one still open (a READING successor once
    it exists), else the last READING re-target, else Q01; None without questions."""
    Q = st["questions"]
    live = [k for k, q in Q.items() if q["status"] not in LANE_ENDED]
    reading = [k for k, q in Q.items() if (q.get("operator") or "").upper() == "READING"]
    return max(live or reading or [min(Q)]) if Q else None


def focused_lane(st, e):
    """The lane a focused-mode event belongs to; a context event (focused_context) belongs to the focused question."""
    return e.get("lane") or (focused_question(st) if focused_context(st, e) else None)


def focused_ending(run, st, e):
    """Why event e ends its focused lane in consolidation instead of RENEW (None: route as usual).
    An acceptance or literature event does so at the lane's end; a lane-budget event always does. A refutation
    first gets one limited RENEW that applies READING (K-READING), unless the refuted question was itself created
    by READING; until that RENEW has handled it, the lane's other events wait for the same RENEW."""
    lane = focused_lane(st, e)
    if st["mode"] != "focused" or not lane or e["type"] not in FOCUSED_END_TYPES:
        return None
    if (st["questions"].get(lane, {}).get("operator") or "").upper() != "READING" and any(
            x["type"] == "refuted" and x.get("lane") == lane and not x.get("handled_by") for x in st["events"]):
        return None
    why = focused_end(run, st, lane)
    return why or ("lane budget reached" if e["type"] == "lane-budget" else None)


def reading_kept(st, qid):
    """Focused mode (program.md sec. 3): the RENEW task that handled lane qid's `refuted` events and kept the
    refutation (READING found no natural reading: no successor of qid), while no comparator or writer task was
    created after it; None otherwise. A READING question's refutation is a focused ending instead."""
    Q, T = st["questions"], st["tasks"]
    q = Q.get(qid)
    if st["mode"] != "focused" or not q or (q.get("operator") or "").upper() == "READING":
        return None
    refs = [e for e in st["events"] if e["type"] == "refuted" and e.get("lane") == qid]
    by = refs[-1].get("handled_by") if refs and all(e.get("handled_by") for e in refs) else None
    if T.get(by, {}).get("role") != "investigator" or any(x.get("parent") == qid for x in Q.values()):
        return None
    seq = T[by].get("created_seq", 0)
    late = any(t["role"] in ("comparator", "writer") and t["status"] not in GONE and t.get("created_seq", 0) > seq
               for t in T.values())
    return None if late else by


def stronger_paths(run, st, qid):
    """Run-relative paths holding a fast start's non-empty 'Stronger (after R1)' items: lane qid's statement or a
    finished investigator task's new/Qxx-statement.md (SKILL.md sec. 5 focused step 4)."""
    paths = [f"lanes/{qid}/statement.md"] + [
        f"tasks/{k}/new/{qid}-statement.md" for k, t in sorted(st["tasks"].items())
        if t["role"] == "investigator" and t["status"] in FINISHED]
    out = []
    for p in paths:
        text = read(Path(run) / p)
        i = text.lower().find("stronger (after r1)")
        rest = text[i + len("stronger (after r1)"):].lstrip(" \t*_:.-") if i >= 0 else ""
        first = next((x.strip() for x in rest.splitlines() if x.strip()), "")
        item = first.lstrip("-*+ \t").strip("()").strip()  # '- none', '(none)': no item
        if item and not first.startswith("#") and not re.match(r"(?i)(none|n/a)\b", item):
            out.append(p)
    return out


def stronger_items(run, st, qid):
    return bool(stronger_paths(run, st, qid))


def after_delivery(st):
    """Focused mode's choice after the delivery (init --after): 'continue' (the v6.4 default) or 'stop'. A run
    initialised before v6.4 has no key and behaves as 'stop', its old behaviour."""
    return st.get("after") or "stop"


def converted(st):
    """The conversion record {from, seq, question, lane_rounds} of a run that `mode --to program` converted after a
    focused delivery (program.md sec. 3), else None."""
    return st.get("converted") if st["mode"] == "program" else None


def delivered_question(st):
    """The focused question whose result was delivered: the lane of the manuscript that passed PAPER, else the
    focused question (focused_question: a READING successor before its refuted parent)."""
    m = delivered_manuscript(st)
    lane = st["candidates"][m].get("lane") if m else None
    return lane if lane in st["questions"] else focused_question(st)


def delivered_manuscript(st):
    """The newest accepted manuscript candidate (it passed PAPER), or None."""
    ms = [k for k, c in sorted(st["candidates"].items()) if c["kind"] == "manuscript" and c["status"] == "accepted"]
    return ms[-1] if ms else None


def focused_end_hint(run, st, qid, evs, kept_by=None):
    why, (best, cid) = focused_end(run, st, qid) or "lane budget reached", best_rung(st, qid)
    budget = any(e["type"] == "lane-budget" for e in evs)
    q = st["questions"][qid]
    optional = bool(best and best != "R1" and why.startswith(best + " accepted") and q["status"] == "active"
                    and not budget)
    later = [k for k in sorted(st["questions"]) if k > qid]
    cont = after_delivery(st) == "continue"
    if cont:  # SKILL.md sec. 5 focused step 4: no extra rounds before the delivery; the program takes them up
        more = (f", now (no more rounds: once in-flight work finishes, q set {qid} --status resolved --rung {best}; "
                "its stronger rungs go to the program)" if optional else "")
        if best and stronger_items(run, st, qid):
            more += "; the 'Stronger (after R1)' items go to the continuation RENEW by path (no new question now)"
    else:
        more = ", after at most 2 more rounds on the optional stronger rungs" if optional else ""
        if best == "R1" and not budget and later and st["questions"][later[-1]]["status"] not in LANE_ENDED:
            more = f", after {later[-1]} (the stronger items) ends"
        elif best == "R1" and not budget and not later and stronger_items(run, st, qid):
            more = (", after the 'Stronger (after R1)' items run as a new question (q add, R1 = the first item; "
                    "light-gate it; q set --budget <rounds used + 2>; SKILL.md sec. 5 focused step 4)")
    tops = [k for k, c in st["candidates"].items() if c.get("lane") == qid and c["status"] == "accepted"
            and c["kind"] in RUNG_KINDS and c.get("claims") == f"{qid}.{best}"]
    pipe = (f"copy {cid} to reports/{qid}-{best}-proof-{cid}.md now (proof-lane.md sec. 6); writer --cand {cid} "
            "(no comparator) with a skeptic CLAIM-GATE in parallel -> verifier PAPER" if len(tops) == 1 else
            "comparator -> writer -> verifier PAPER, with a CLAIM-GATE beside the comparator")
    reread = (f" and {q['parent']}'s literal refutation" if (q.get("operator") or "").upper() == "READING"
              and q.get("parent") else "")
    plan = (f"consolidate {qid}.{best} ({cid}): {pipe}{more}" if best
            else f"the target is refuted: a refutation report from the record (its witness{reread})"
            if " excluded (" in why or why == "refuted" else "no accepted rung: a failure report from the record")
    tail = f"; {CONVERT_HINT}" if cont else ""
    if not evs:  # reading_kept: every event is handled; the delivery is what is left
        return f"{qid} focused, {why}: READING ({kept_by}) kept the refutation; {plan}{tail}"
    return (f"{qid} focused, {why}: no RENEW for "
            + ", ".join(f"{e['id']} {e['type']}" for e in evs) + f"; {plan}; then event --handled "
            + " ".join(e["id"] for e in evs) + " --by "
            + ("<comparator or writer task>" if best else "<the task that writes it>") + tail)


def suggest_events(run, st, pending, add):
    T, Q = st["tasks"], st["questions"]
    for qid, q in sorted(Q.items()):
        if q["status"] == "active" and q.get("held_by"):
            ev = {e["id"]: e for e in st["events"]}
            fin = all(h in ev and focused_ending(run, st, ev[h]) for h in q["held_by"])
            add(f"{qid} HELD by {holds_desc(st, q)} until " + ("consolidation" if fin else "RENEW") + " (no new round)")
    for cl, k, by in contradictions(st, run):
        add(f"{contradiction_text(cl, k, by)}: contradiction - quarantine both (quarantine --code contradiction logs "
            "model-change), TARGETED review, fresh SECOND-INDEPENDENT review of the accepted proof (verification.md sec. 8)")
    inv = [k for k, t in sorted(T.items()) if t["role"] == "investigator" and t.get("mode") in ("MODEL", "SELECT", "RENEW")
           and t["status"] in LIVE]
    renew, ends = [], {}
    for e in pending:  # program.md §7: a stall waits for its TARGETED review, too-easy for both skeptic gates
        lane = f" {e['lane']}" if e.get("lane") else ""
        if focused_ending(run, st, e):
            ends.setdefault(focused_lane(st, e), []).append(e)  # focused mode ends in consolidation, not RENEW
            continue
        if focused_context(st, e):
            add(f"{e['id']} {e['type']} (no hold): {FOCUSED_CONTEXT}")
            continue
        if e["type"] in ("stall", "too-easy"):
            role, modes = ("literature-reviewer", {"TARGETED"}) if e["type"] == "stall" else ("skeptic", {"MODEL-GATE", "CLAIM-GATE"})
            ts = [k for k, t in sorted(T.items()) if t["role"] == role and t.get("mode") in modes
                  and t.get("created_seq", 0) > e["seq"] and t.get("lane") in (None, e.get("lane"))]
            done = {T[k]["mode"] for k in ts if T[k]["status"] in FINISHED}
            if done != modes:
                live = [k for k in ts if T[k]["status"] in LIVE]
                add(f"{e['id']} {e['type']}{lane}: " + (f"RENEW waits for {', '.join(live)}" if live else
                    "dispatch literature-reviewer TARGETED on the stuck step (+ scout if the Sanity line allows), then RENEW"
                    if e["type"] == "stall" else "dispatch skeptic MODEL-GATE + CLAIM-GATE (two tasks) first, then RENEW"))
                continue
        if e["type"] in RENEW_TYPES + ("too-easy",) or (e["type"] == "rung-accepted" and "assumes:" in (e.get("note") or "")):
            renew.append(e)
    if renew:
        desc = ", ".join(f"{e['type']} {e.get('lane') or ''}".strip() + f" ({e['id']})" for e in renew[:5])
        reading = ("; focused: limited" + (", READING first for a refutation, program.md sec. 3"
                                            if any(e["type"] == "refuted" for e in renew) else "")
                   if st["mode"] == "focused" else "")
        if st["mode"] == "program" and not first_select_done(st) and converted(st):  # program.md sec. 2.1
            add(f"events pending: {desc} - handled by the continuation SELECT (program.md sec. 2.1; the RENEW on the "
                "delivered result handles none); then event --handled <E#...> --by <task>")
        elif st["mode"] == "program" and not first_select_done(st):  # program.md sec. 7: no RENEW before SELECT
            add(f"events pending: {desc} - handled by SELECT (opening), or by the MODEL whose Assignment names them "
                "(a KILL(IMPLIED)'s successors: SELECT); then event --handled <E#...> --by <task>")
        elif inv:
            add(f"events pending: {desc} - investigator {inv[0]} is live; batch them into the next RENEW"
                + (f" ({reading[2:]})" if reading else ""))
        else:
            add(f"events pending: {desc} -> dispatch investigator RENEW (batch{reading}), then event --handled <E#...> "
                "--by <task>")
    for qid, evs in sorted(ends.items()):
        add(focused_end_hint(run, st, qid, evs))
    for qid in sorted(Q):
        kept = reading_kept(st, qid) if qid not in ends else None
        if kept:
            add(focused_end_hint(run, st, qid, [], kept))
    for e in pending:
        if e["type"] == "queue-low":
            add(f"{e['id']} queue-low: {EVENT_ACTIONS['queue-low']}; then event --handled")
        elif e["type"] == "breadth-review":
            add(f"{e['id']} breadth-review: investigator BREADTH in a fresh context, then event --handled")
        elif e["type"] == "user-input":
            add(f"{e['id']} user-input: route per program.md, then event --handled")
    for k, t in sorted(T.items()):
        sfs, lane = t.get("shared_failing_step"), t.get("lane")
        if sfs and lane in Q and Q[lane]["status"] == "active" and not any(
                e["type"] == "stall" and e.get("lane") == lane and (e["seq"] >= t.get("ingested_seq", 0)
                                                                 or not e.get("handled_by")) for e in st["events"]):
            add(f"{lane}: {k} reports a shared failing step ({cell(sfs, 60)}) - event --type stall --lane {lane}")
    for r in st["reviews"]:
        te, c = r.get("too_easy"), st["candidates"].get(r["cand"], {})
        if te and not is_implied(c) and not any(e["type"] == "too-easy" and (r["cand"] in (e.get("note") or "") or (
                e.get("lane") and e.get("lane") == c.get("lane") and e["seq"] >= r["seq"])) for e in st["events"]):
            add(f"{r['cand']}: too_easy {te} reported by {r['task']} - event --type too-easy"
                + (f" --lane {c['lane']}" if c.get("lane") else "") + f" --note \"{r['cand']}: {te} ({r['task']})\"")
    for qid, q in sorted(Q.items()):
        if q["status"] == "active":
            hint = stall_hint(st, qid)
            if hint:
                add(hint)


def suggest_candidates(run, st, B):
    C = st["candidates"]
    cohorts, i8, transfers = {}, {}, {}  # transfers: candidate -> "" or " (second pass ...)"
    # both sides of a contradiction: the events line replaces their exclude / ledger add hints
    clashing = {x for _, k, by in contradictions(st, run) for x in (k, by)}
    for k, c in sorted(C.items()):
        claims = c.get("claims") or ""
        if c["status"] == "accepted":
            probs = gate_check(st, run, k)[0]
            if probs:
                B["close"].append(f"{k}: accepted but its gate now fails ({probs[0]}) - quarantine or re-review")
            if k in clashing:
                pass
            elif c["kind"] == "counterexample" and not exclusion_of(st, k):
                B["close"].append(f"{k}: accepted counterexample - exclude --claim {claims} --cand {k}")
            elif c["kind"] in RUNG_KINDS and claims.endswith(".D") and not exclusion_of(st, k):
                B["close"].append(f"{k}: accepted proof of {claims} without an exclusion - exclude --claim "
                                  f"{d_refutes(run, c['lane'])} --cand {k} (logs refuted)")
            elif not ledger_of(st, k) and c["kind"] not in ("manuscript", "counterexample"):
                B["close"].append(f"{k}: accepted - ledger add --cand {k} (reusable premise)")
            continue
        if c["status"] != "proposed" or superseded_by(st, k):
            continue
        probs = gate_check(st, run, k)[0]
        if not probs:
            conflict = accept_conflict(st, run, k)
            if conflict:
                B["events"].append(f"{k}: passes its gates but {conflict}: contradiction - quarantine both (quarantine "
                                   "--code contradiction logs model-change), TARGETED review, fresh SECOND-INDEPENDENT "
                                   "review of the accepted proof (verification.md sec. 8)")
            else:
                B["close"].append(f"{k}: gates satisfied - accept (or ingest --accept)")
            continue
        miss = missing_scopes(st, k)
        for m in miss:
            if m == "cross" and c.get("lane") and not is_fragment(c):
                cohorts.setdefault((c["lane"], c.get("round") or 0), []).append(k)
            elif c["kind"] == "transfer" and not in_flight(st, k, "isolated"):
                transfers[k] = ""
            elif not any(in_flight(st, k, s) for s in m.split("/")):
                who = ", ".join(t for t, _ in authors_of(st, c))
                what = "SALVAGE" if c.get("gap") and m == "individual" else m.upper().replace("/", " or ")
                B["close" if is_fragment(c) else "lane"].append(f"{k}: needs {what} review (not by {who})")
        if blocking_objections(st, k) and not c.get("gap"):
            i8.setdefault((c.get("lane") or "-", c.get("round") or 0), []).append(k)
        elif not miss and not c.get("gap"):
            wait = [p for p in probs if p.endswith(" still running")]
            if c["kind"] == "transfer" and probs == [SECOND_PASS]:
                if not in_flight(st, k, "isolated"):
                    transfers[k] = " (second pass: new_argument yes)"
            else:
                B["lane"].append(f"{k}: reviews pass but {', '.join(wait)} - accept after it returns (ingest --accept)"
                                 if wait == probs
                                 else f"{k}: not acceptable - {probs[0]}")
    if transfers:  # K66: one ISOLATED task checks every transfer candidate waiting for a gate
        who = ", ".join(dict.fromkeys([t for k in transfers for t, _ in authors_of(st, C[k])]
                                      + [r["task"] for k in transfers for r in reviews_of(st, k)
                                         if r["scope"] == "isolated"]))
        B["close"].append(", ".join(k + why for k, why in transfers.items())
                          + f": needs ISOLATED review (not by {who}) - one task for all: task new RUN --role verifier "
                          f"--mode ISOLATED --cand {','.join(transfers)} --start (source cards by --extra-file)")
    per_lane = {}
    for (lane, rnd), ks in sorted(i8.items()):
        per_lane.setdefault(lane, []).append((rnd, ks))
    for lane, items in sorted(per_lane.items()):  # E10: one I8 line per lane round; older rounds collapsed
        rnd, ks = items[-1]
        B["i8"].append(f"{lane} r{rnd}: blocking objections on {', '.join(ks)} - route per I8 (repair, "
                       "reformulate, adjudicate, or park with a reason)")
        if items[:-1]:
            B["i8"].append(f"{lane} r{items[0][0]}-r{items[-2][0]}: {sum(len(x) for _, x in items[:-1])} older "
                           "blocked drafts (see record.md)")
    for (lane, rnd), ks in sorted(cohorts.items()):
        lt = lane_tasks(st, lane, rnd)
        if is_gate_only(st["questions"][lane], rnd):  # skeptic arguments: one SECOND-INDEPENDENT review each
            B["lane"] += [f"{k}: needs SECOND-INDEPENDENT review (gate-only round {lane} r{rnd})" for k in ks
                          if not in_flight(st, k, "cross")]
            continue
        if any(t["role"] == "verifier" and MODE_SCOPE.get(t.get("mode") or "") == "cross" and t["status"] in LIVE
               for t in lt.values()) or any(in_flight(st, k, "cross") for k in ks):
            continue
        provers = [t for t, x in lt.items() if x["role"] == "prover" and x["status"] in LIVE]
        group = cohort(st, lane, rnd)
        reviewers = {r["task"] for r in st["reviews"]}
        done = [t for t, x in sorted(lt.items()) if x["role"] == "verifier" and MODE_SCOPE.get(x.get("mode") or "") == "cross"
                and x["status"] in FINISHED and t in reviewers]
        if done:  # the cohort was cross-reviewed: a late or re-filed draft gets its own second gate
            B["lane"] += [f"{k}: needs SECOND-INDEPENDENT review (late draft; cohort {lane} r{rnd} already "
                          f"cross-reviewed by {done[0]})" for k in ks]
        elif provers:
            B["lane"].append(f"{', '.join(ks)}: CROSS-DRAFT waits for cohort {lane} r{rnd} (provers {', '.join(provers)} live)")
        elif len(group) == 1:
            B["lane"].append(f"{ks[0]}: needs SECOND-INDEPENDENT review (single-draft cohort {lane} r{rnd})")
        else:
            B["lane"].append(f"{', '.join(ks)}: needs CROSS-DRAFT (cohort {lane} r{rnd} complete: {', '.join(group)})")


def suggest_lanes(run, st, B):
    C, L, T = st["candidates"], st["ledger"], st["tasks"]
    contra = ({cl.split(".")[0] for cl, _, _ in contradictions(st, run)}
              | {C[k].get("lane") for k, _ in pending_conflicts(st, run)})
    for qid, q in sorted(st["questions"].items()):
        if q["status"] != "active":
            continue
        rnd, held = q["round"], bool(q.get("held_by"))
        live = [k for k, t in T.items() if t.get("lane") == qid and t["status"] in LIVE]
        wait = f"let live tasks finish ({', '.join(live)}), then " if live else ""
        if qid in contra:
            B["close"].append(f"{qid}: contradiction pending (see above) - settle it before closing the lane "
                              "(verification.md sec. 8)")
            continue
        excl = [lid for lid, e in sorted(L.items()) if e["kind"] == "exclusion" and e["status"] == "active"
                and covers(e)[0].startswith(qid + ".")]
        top = [k for k, c in sorted(C.items()) if c.get("lane") == qid and c["status"] == "accepted"
               and c["kind"] in RUNG_KINDS and c.get("claims") == qid + ".R1"]
        if excl:
            B["close"].append(f"{qid}: {span(covers(L[excl[0]]))} excluded ({excl[0]}) - {wait}q set {qid} --status refuted")
            continue
        if top:
            ass = C[top[0]].get("assumes") or []
            B["close"].append(f"{qid}: R1 accepted ({top[0]}" + (f"; assumes: {'; '.join(ass)}" if ass else "")
                              + f") - {wait}q set {qid} --status resolved --rung R1")
            continue
        end = focused_end(run, st, qid) if after_delivery(st) == "continue" else None
        best = best_rung(st, qid)[0]
        if end and best and end.startswith(best + " accepted"):  # SKILL.md sec. 5 focused step 4 (continue)
            B["close"].append(f"{qid}: {end} - no more rounds before the delivery (after delivery: continue): "
                              f"{wait}q set {qid} --status resolved --rung {best}; its stronger rungs go to the program")
            continue
        new = pending_statement(run, st, qid)
        if new and new[2] is None:
            how = ("its next QUESTION-GATE names it (at opening, the batched seed gate: program.md sec. 2 step 4b)"
                   if st["mode"] == "program" else f"light-gate it (task new --role skeptic --mode QUESTION-GATE "
                                                   f"--question {qid} --light: its packet names it)")
            B["lane"].append(f"{qid}: {new[1]} ({new[0]}) is not installed - {how}, then install it at the next round "
                             "boundary (SKILL.md sec. 5: focused step 3; program step 4)")
        elif new and new[2][1] == "ADVANCE":
            B["lane"].append(f"{qid}: install {new[1]} as lanes/{qid}/statement.md at the next round boundary (gate "
                             f"{new[2][0]} passed), before round {qid} --open")
        if rnd == 0:
            if not held:
                B["lane"].append(f"{qid}: lane open, no round yet - round {qid} --open, then write the plan")
            continue
        stage = lane_stage(st, qid)
        lt_live = any(t["status"] in LIVE for t in lane_tasks(st, qid, rnd).values())
        gate = round1_gate(st, qid) if stage in ("PLAN", "BRIEF") else None
        gate_live = gate and T[gate[0]]["status"] in LIVE
        kind = "light gate" if gate and T[gate[0]].get("light") else "gate"
        if gate and gate[1] and gate[1] != "ADVANCE" and not held:  # SKILL.md sec. 5 focused step 2
            succ = [k for k, x in sorted(st["questions"].items()) if x.get("parent") == qid]
            B["lane"].append(f"{qid} r{rnd}: no provers - its {kind} {gate[0]} returned {gate[1]}: " + (
                f"its successor {succ[-1]} is registered: q set {qid} --status parked --note-file <file>" if succ else
                "route it (program.md sec. 5.2; focused: SKILL.md sec. 5 step 2); the next version opens a new round"))
        elif stage == "PLAN" and not held:
            prev = round_close_pending(st, qid, rnd - 1) if rnd > 1 else []
            B["lane"].append(f"{qid} r{rnd}: write plan.md slots (allocation rules); " + (
                f"BRIEF waits for r{rnd - 1} close work: {', '.join(prev)}" if prev else "dispatch one summarizer per prover"))
        elif stage == "BRIEF" and not lt_live and not held:
            B["lane"].append(f"{qid} r{rnd}: briefings done - " + (
                f"provers wait for the {kind} {gate[0]} (program.md sec. 6.1)" if gate_live else "dispatch the provers"))
        elif stage == "CLOSE" and not lt_live:
            steps = close_steps(st, qid, rnd)
            if steps:
                B["close"].append(f"{qid} r{rnd} closed: " + "; ".join(steps))
    due = advisor_due(st)
    if due:
        by = {}
        for q, r in due:
            by.setdefault(q, []).append(r)
        B["close"].append("process advisor due (reviews since the last advisor task): " + ", ".join(
            f"{q} r{rs[0]}" + (f"-r{rs[-1]}" if len(rs) > 1 else "") for q, rs in sorted(by.items())))
    for lid in sorted(load_bearing(st)):
        if L[lid]["status"] == "active" and needs_second_isolated(st, lid):
            B["close"].append(f"{lid}: load-bearing - dispatch a second ISOLATED review of {L[lid]['cand']} "
                              f"(if it fails: quarantine {lid} --code failed-isolated)")


def lane_cap(st):
    """max(2, K//2): the lanes run at once (program.md sec. 6)."""
    return max(2, (st.get("k") or 1) // 2)


def first_select_done(st):
    return any(t["role"] == "investigator" and t.get("mode") == "SELECT" and t["status"] in FINISHED
               for t in st["tasks"].values())


def opening_minutes(run):
    """Minutes since the run's first log.jsonl entry (init); None if unreadable."""
    try:
        with open(xp(Path(run) / "log.jsonl"), encoding="utf-8") as f:
            t0 = json.loads(f.readline())["time"]
        start = datetime.datetime.strptime(t0, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return int((datetime.datetime.now(datetime.timezone.utc) - start).total_seconds() // 60)


def full_gated(st, after=0):
    """Questions named by a full (not light) QUESTION-GATE task created after seq `after`."""
    return {q for t in st["tasks"].values() if t["role"] == "skeptic" and t.get("mode") == "QUESTION-GATE"
            and not t.get("light") and t["status"] not in GONE
            and t.get("created_seq", 0) > after for q in t.get("questions") or []}


def foothold_seed(st):
    """Program mode, before the first SELECT and while no lane is active: the first primary seed (priority order)
    whose latest verdict is a light gate's ADVANCE; it opens at once as the foothold lane (SKILL.md sec. 5 step 4)."""
    Q, T = st["questions"], st["tasks"]
    if (st["mode"] != "program" or converted(st) or first_select_done(st)
            or any(q["status"] == "active" for q in Q.values())):
        return None
    for k, q in sorted(Q.items()):
        v = (q.get("verdicts") or [None])[-1]
        if (q.get("priority") != "secondary" and q["status"] in ("draft", "vetting", "ready") and v
                and v["code"] == "ADVANCE" and T.get(v["task"], {}).get("light")):
            return k
    return None


def foothold_line(qid):
    return (f"foothold: open {qid} now (its light gate's ADVANCE; SKILL.md sec. 5 step 4): q set RUN {qid} --status "
            f"active --slots 2 --rung R1 (no --model); round RUN {qid} --open; briefings, then provers")


def seed_gate_todo(run, st):
    """Primary seeds with an R1 that no full QUESTION-GATE names yet: the batched seed gate (program.md sec. 2 step
    4b), a foothold lane opened by the fast start included."""
    gated = full_gated(st)
    return [k for k, q in sorted(st["questions"].items()) if q.get("priority") != "secondary"
            and q["status"] in ("draft", "vetting", "active") and k not in gated and has_r1(run, k)]


def opening_step(run, st):
    """K02: the first missing program-mode opening step (program.md sec. 2), for the no-prover watchdog."""
    T, Q = st["tasks"], st["questions"]

    def has(role, mode):
        return [k for k, t in sorted(T.items()) if t["role"] == role and t.get("mode") == mode
                and t["status"] not in GONE]

    if foothold_seed(st):
        return foothold_line(foothold_seed(st))
    if not (has("literature-reviewer", "SURVEY") or has("literature-reviewer", "LANDSCAPE") or has("investigator", "MODEL")):
        return ("the first wave: SURVEY per family + LANDSCAPE + scout ANCHOR + one light QUESTION-GATE on the primary "
                "claim seeds (program.md sec. 2 step 2)")
    if not has("investigator", "MODEL"):
        return "investigator MODEL (once the baseline family's card is filed)"
    if not has("skeptic", "MODEL-GATE"):
        return "skeptic MODEL-GATEs on MODEL's models"
    seeds = seed_gate_todo(run, st)
    if seeds:
        return ("one batched full QUESTION-GATE on the primary seeds with an R1, once every MODEL-GATE has returned "
                f"(--question {','.join(seeds)})")
    if not has("investigator", "PROPOSE"):
        return "investigator PROPOSE x2-4 (after LANDSCAPE)"
    if not has("investigator", "SELECT"):
        return "investigator SELECT (when the sweep returns)"
    done = [T[k].get("created_seq", 0) for k in has("investigator", "SELECT") if T[k]["status"] in FINISHED]
    if not done:
        return "skeptic QUESTION-GATEs on the selected questions (after SELECT returns)"
    gated = full_gated(st, max(done))
    todo = [k for k, q in sorted(Q.items()) if q["status"] in ("draft", "vetting")
            and q.get("created_seq", 0) > max(done) and k not in gated]
    if todo:
        return f"skeptic QUESTION-GATEs on the selected questions (--question {','.join(todo)})"
    ready = [k for k, q in sorted(Q.items()) if q["status"] == "ready"]
    return (f"open a lane for {' '.join(ready)} (program.md sec. 6), then its provers" if ready
            else "none missing, and no question is ready")


CONT_HEAD = "continuation from focused delivery (program.md sec. 2.1): "


def continuation_tasks(st, role, mode):
    """Tasks of a role and mode created after the conversion (program.md sec. 2.1), not cancelled or superseded."""
    seq = (converted(st) or {}).get("seq", 0)
    return [k for k, t in sorted(st["tasks"].items()) if t["role"] == role and t.get("mode") == mode
            and t["status"] not in GONE and t.get("created_seq", 0) > seq]


def continuation_open(st):
    """The conversion record while a converted run has no finished SELECT created after the conversion (the
    continuation opening, program.md sec. 2.1), else None."""
    c = converted(st)
    return c if c and not any(st["tasks"][k]["status"] in FINISHED
                              for k in continuation_tasks(st, "investigator", "SELECT")) else None


def continuation_step(run, st):
    """program.md sec. 2.1: the next step of the continuation opening after a focused delivery - investigator RENEW
    on the delivered result (+ LANDSCAPE if none ran), then PROPOSE x2-4 (they see the grid the RENEW writes), then
    SELECT, then registering and gating the first continuation SELECT's cards. None once they are gated, or once any
    later investigator task exists: the run is an ordinary program from then on. The action comes first in each line
    (status --brief cuts lines at 220 characters)."""
    c = converted(st)
    if not c:
        return None
    T, Q, qid = st["tasks"], st["questions"], c.get("question") or "the delivered question"
    sels = continuation_tasks(st, "investigator", "SELECT")
    if not sels:
        renews, props = continuation_tasks(st, "investigator", "RENEW"), continuation_tasks(st, "investigator", "PROPOSE")
        if not renews:
            land = "" if any(t["role"] == "literature-reviewer" and t.get("mode") == "LANDSCAPE" and t["status"] not in GONE
                             for t in T.values()) else " + LANDSCAPE (none ran; if workers have web)"
            return (CONT_HEAD + f"investigator RENEW --title continuation on {qid}{land}, then PROPOSE x2-4, then SELECT. "
                    f"The RENEW applies {continuation_ops(run, st, c.get('question'))[0]} and writes the map grid if "
                    "missing (MODEL only if the RENEW or a gate asks)")
        live = [k for k in renews if T[k]["status"] in LIVE]
        if live and not props:
            return CONT_HEAD + f"PROPOSE x2-4 once RENEW {live[-1]} returns (it writes the map grid), then SELECT"
        if not props:
            return (CONT_HEAD + "PROPOSE x2-4 together now (one lens each: OBVIOUS-CONSTRUCTION and ADVERSARY, then "
                    "BARRIER and CURVE/EXTREMES; program.md sec. 5.1), then SELECT")
        live = [k for k in renews + props if T[k]["status"] in LIVE]
        if live:
            return (CONT_HEAD + f"SELECT once {', '.join(live)} return (RENEW {renews[-1]}'s cards and the sweep's "
                    "cards.md go to it by path)")
        return (CONT_HEAD + f"investigator SELECT now (task new --role investigator --mode SELECT --start): RENEW "
                f"{renews[-1]}'s successor cards are its first candidates (TIGHTNESS first), then the sweep's cards.md; "
                "it handles pending events")
    s = sels[0]
    if T[s]["status"] not in FINISHED:
        return CONT_HEAD + f"SELECT {s} running; then register its cards (program.md sec. 4) and QUESTION-GATE them"
    since = T[s].get("created_seq", 0)
    if any(t["role"] == "investigator" and t.get("mode") != "EXPLAIN" and t["status"] not in GONE
           and t.get("created_seq", 0) > since for t in T.values()):
        return None  # a later SELECT, RENEW or sweep: an ordinary program from here on
    new = [k for k, q in sorted(Q.items()) if q.get("created_seq", 0) > since]
    if not new:
        return (CONT_HEAD + f"register SELECT {s}'s cards now (program.md sec. 4: q add, card and statement), then "
                "skeptic QUESTION-GATEs on them" if new_cards(run, s) else None)
    gated = {q for t in T.values() if t["role"] == "skeptic" and t.get("mode") == "QUESTION-GATE"
             and t["status"] not in GONE and t.get("created_seq", 0) > since for q in t.get("questions") or []}
    todo = [k for k in new if Q[k]["status"] in ("draft", "vetting") and k not in gated]
    return (CONT_HEAD + f"skeptic QUESTION-GATEs on SELECT {s}'s cards (--question {','.join(todo)}; batching: "
            "program.md sec. 5.2), then open lanes at the ready gate (sec. 6)" if todo else None)


def suggest_outer(run, st, pending, B):
    T, Q = st["tasks"], st["questions"]
    ready = [k for k, q in sorted(Q.items()) if q["status"] == "ready"]
    active = [k for k, q in Q.items() if q["status"] == "active" and not in_gate_only_round(q)]  # outside the cap
    select_done = first_select_done(st)
    conv = converted(st)  # program.md sec. 2.1: a converted focused run has its own opening
    opening = st["mode"] == "program" and not select_done and not conv
    cont_line = continuation_step(run, st) if conv else None
    if foothold_seed(st):
        B["outer"].append(foothold_line(foothold_seed(st)))
    elif ready and opening:  # SKILL.md sec. 5 step 6: before SELECT only the foothold lane opens
        foot = sorted(k for k, q in Q.items() if q["status"] == "active")
        B["outer"].append(f"ready questions {' '.join(ready)}: " + (
            f"wait for SELECT's lanes_to_open (foothold {foot[0]} already open)" if foot else
            f"open {ready[0]} as the foothold lane (SKILL.md sec. 5 step 6): q set {ready[0]} --status active "
            f"--slots N --model M --rung Rc, then round {ready[0]} --open"))
    elif ready:
        B["outer"].append(f"ready questions {' '.join(ready)}: open lanes per the investigator's portfolio "
                          "(q set <Q> --status active --slots N --model M --rung Rc, then round <Q> --open)")
    inv_live = any(t["role"] == "investigator" and t.get("mode") in ("MODEL", "SELECT", "RENEW") and t["status"] in LIVE
                   for t in T.values())
    free = lane_cap(st) - len(active)
    vetting = [k for k, q in Q.items() if q["status"] == "vetting"]  # K54: questions still at their gate count
    if (st["mode"] == "program" and select_done and len(ready) + len(vetting) < free and not inv_live
            and not cont_line and not any(e["type"] == "queue-low" for e in pending)):
        B["outer"].append(f"queue low ({len(ready)} ready + {len(vetting)} vetting < {free} free lanes): "
                          "event --type queue-low, then a proposal sweep")
    last_b = max([e.get("lane_rounds", 0) for e in st["events"] if e["type"] == "breadth-review"]
                 + [(conv or {}).get("lane_rounds", 0)], default=0)  # a converted run counts from the conversion
    breadth = breadth_tasks_due(st)
    if st["counters"].get("lane_rounds", 0) - last_b >= 10:
        B["outer"].append("10+ lane-rounds since the last breadth review: event --type breadth-review")
    elif breadth:
        B["outer"].append(f"{breadth[0]} tasks finished since {breadth[1]} (30+): event --type breadth-review")
    runwide = advisor_runwide_due(st)
    if runwide:
        B["outer"].append(f"process advisor due (run-wide: {runwide}): task new --role process-advisor "
                          "--title run-wide --start")
    if st["mode"] == "program" and not conv and not any(t["role"] == "prover" for t in T.values()):  # K02 watchdog
        mins = opening_minutes(run)
        line = (f"no prover yet: {len(T)} tasks, {'?' if mins is None else mins} min; "  # minutes since init
                f"next opening step: {opening_step(run, st)}")
        if not Q and any(t["role"] == "investigator" and t.get("mode") == "MODEL" and t["status"] in FINISHED
                         for t in T.values()):
            line += "; no seeds and no foothold R1"
        B["outer"].append(line)
    why = no_prover_safeguard(st)  # a converted run has no watchdog line (sec. 2.1 is its opening), only the safeguard
    if why:
        B["outer"].append(f"no-prover safeguard ({why}): the next investigator SELECT or RENEW packet carries "
                          "the safeguard line" + ("; dispatch investigator RENEW" if select_done and not inv_live else ""))
    gates = [t for t in T.values() if t["role"] == "skeptic" and t.get("mode") == "MODEL-GATE" and t["status"] not in GONE]
    seeds = seed_gate_todo(run, st) if opening and gates and not any(t["status"] in LIVE for t in gates) else []
    if seeds and any(t["role"] == "prover" for t in T.values()):  # with no prover, the watchdog line names it
        B["outer"].append(f"seed gate (program.md sec. 2 step 4b): one batched full QUESTION-GATE --question "
                          f"{','.join(seeds)} (a foothold lane's verdict acts at its next round boundary)")
    if opening:
        B["outer"].append("opening (program.md sec. 2): intake (seeds in priority order) -> SURVEY + LANDSCAPE + scout "
                          "ANCHOR + one light QUESTION-GATE on primary claim seeds (fast start: the first ADVANCE opens "
                          "as the foothold lane) -> MODEL (R1s for primary direction seeds; opening budget) -> "
                          "MODEL-GATEs (ingest files patches) -> one batched full QUESTION-GATE on primary seeds + "
                          "PROPOSE x2-4 after LANDSCAPE -> SELECT -> QUESTION-GATEs; open a lane as soon as one "
                          "question is ready")
        B["outer"] += opening_budget(st)
    elif conv:
        if cont_line:
            B["outer"].append(cont_line)
    elif (st["mode"] == "focused" and delivered_manuscript(st)
          and not any(q["status"] in ("active", "ready", "vetting") for q in Q.values())):
        after = after_delivery(st)  # program.md sec. 3: after delivery, convert (continue) or end (stop)
        B["outer"].append(f"{delivered_question(st)} delivered ({delivered_manuscript(st)} passed PAPER; after delivery: "
                          f"{after}): " + (CONVERT_STEPS if after == "continue"
                                           else "the run ends (program.md sec. 3): final progress.md and checkpoint"))
    elif (st["mode"] == "focused" and all(q["status"] in ("draft", "vetting") for q in Q.values())
          and not st["counters"].get("lane_rounds")):
        B["outer"].append("focused (SKILL.md sec. 5): q add the claim. A claim to prove or disprove: fast start "
                          "(program.md sec. 6.1) - copy it as R1 into lanes/Q01/statement.md; light QUESTION-GATE + "
                          "SURVEY per source (+ LANDSCAPE, scout ANCHOR) + investigator MODEL in parallel; open the lane "
                          "and brief now; provers after the light gate. A 'determine' problem: MODEL (focused), then "
                          "MODEL-GATE + full QUESTION-GATE; ready gate -> lane")
    elif st["mode"] == "focused" and not any(q["status"] in ("active", "ready") for q in Q.values()):
        for k, q in sorted(Q.items()):  # a successor of the claim (READING, a next version) runs as a fast start
            if q.get("parent") and q["status"] in ("draft", "vetting"):
                B["outer"].append(f"{k} ({q.get('operator') or 'successor'} of {q['parent']}): fast start (program.md "
                                  f"sec. 3, 6.1) - lanes/{k}/statement.md is the RENEW's; light QUESTION-GATE (--question "
                                  f"{k} --light); q set {k} --status active --slots N --rung R1; round {k} --open; "
                                  "briefings now, provers after the light gate")
    lint = progress_findings(run, st)  # K08: at most 3 lines here; check --progress prints all
    B["outer"] += [f"progress.md: {x}" for x in lint[:3]]
    if len(lint) > 3:
        B["outer"][-1] += f" (+{len(lint) - 3} more: check RUN --progress)"


def suggest(run, st, flags, pending):
    """Mechanical next actions in priority order (E10): control flags, reconcile, holds and events,
    round-close work (I8 reminders last), lane stages, outer work. No mathematical judgment."""
    order = ("control", "reconcile", "events", "close", "i8", "lane", "outer")
    B = {k: [] for k in order}
    if flags["STOP"]:
        B["control"].append(f"STOP in force ({flag_desc(flags['STOP'][0])}): dispatch nothing; ingest tasks that have "
                            "result.md; mark other running tasks cancelled (unknown if a worker may be alive); "
                            "checkpoint; tell the user it is stopped. Lift only on the user's explicit words: "
                            "resume RUN --stop --reason-file <file>")
    elif flags["PAUSE"]:
        B["control"].append(f"PAUSE in force ({flag_desc(flags['PAUSE'][0])}): ingest returned results; let running "
                            "workers finish; checkpoint; brief status; end the turn")
    quiet = bool(flags["STOP"] or flags["PAUSE"])
    suggest_tasks(run, st, B["reconcile"].append, quiet)
    if quiet:
        return B["control"] + B["reconcile"]
    suggest_events(run, st, pending, B["events"].append)
    suggest_candidates(run, st, B)
    suggest_lanes(run, st, B)
    suggest_outer(run, st, pending, B)
    acts = [x for k in order for x in B[k]]
    work = [x for x in acts if not x.startswith("progress.md: ")]  # the lint lines come last
    if not work and not any(t["status"] in LIVE for t in st["tasks"].values()):
        acts.insert(0, "nothing runnable: program mode does not end here (I9) - queue-low + proposal sweep, or BREADTH "
                       "review" if st["mode"] == "program" else focused_fallback(run, st))
    return acts


def focused_fallback(run, st):
    qid = focused_question(st)
    why = focused_end(run, st, qid) or "" if qid else ""
    return ("nothing runnable: " + (
        f"consolidate {qid}'s strongest accepted rung (proof-lane.md sec. 6: a skeptic CLAIM-GATE; the comparator, "
        "skipped for one candidate (writer --cand); writer; verifier PAPER)" if qid and best_rung(st, qid)[0]
        else "the target is refuted: a refutation report from the record (its witness) -> verifier PAPER"
        if why == "refuted" or " excluded (" in why else "a failure report from the record")
        + (f"; {CONVERT_HINT}" if after_delivery(st) == "continue" else ""))


def capped(title, items, cap, full):
    if not items:
        return []
    if full or len(items) <= cap:
        return [title] + items
    return [title] + items[:cap - 1] + [f"  ... {len(items) - cap + 1} more (status --full)"]


def build_status(run, st, full=False, brief=False):
    """The status block: at most STATUS_LINES lines (BRIEF_LINES with brief) unless full."""
    run = Path(run)
    T, C, L, Q = st["tasks"], st["candidates"], st["ledger"], st["questions"]
    flags = control_flags(run)
    pending = [e for e in st["events"] if not e.get("handled_by")]
    conv = converted(st)
    mode = st["mode"] + (f" (from focused, seq {conv['seq']})" if conv else "")
    head = (f"ri status {now()} | seq {st['seq']} | mode {mode} | isolation {st['isolation_default']} | "
            f"K {st.get('k') or '-'} | STOP {'YES' if flags['STOP'] else 'no'} | PAUSE {'YES' if flags['PAUSE'] else 'no'}")
    acts = suggest(run, st, flags, pending)
    if brief:
        live = [f"{k} {t['status']} {t['role']}" + (f"/{t['mode']}" if t.get("mode") else "")
                for k, t in sorted(T.items()) if t["status"] in LIVE]
        held = [f"{k} by {holds_desc(st, q)}" for k, q in sorted(Q.items()) if q["status"] == "active" and q.get("held_by")]
        out = [head, "live: " + cell("; ".join(live) or "none", 300)]
        if held:
            out.append("held: " + cell("; ".join(held), 300))
        out.append("next:")
        room = BRIEF_LINES - len(out)
        shown = acts[:room] if len(acts) <= room else acts[:room - 1]
        out += ["  - " + cell(x, 220) for x in shown] or ["  - (none)"]
        if len(acts) > len(shown):
            out.append(f"  ... {len(acts) - len(shown)} more (status)")
        return out[:BRIEF_LINES]
    ts = [t["status"] for t in T.values()]
    le = [(e["kind"] == "exclusion", e["status"]) for e in L.values()]
    out = [head,
           f"counts: questions {len(Q)}; tasks {len(T)} (queued {ts.count('queued')}, running {ts.count('running')}, "
           f"unknown {ts.count('unknown')}); candidates {len(C)} (accepted "
           f"{sum(c['status'] == 'accepted' for c in C.values())}); ledger active {le.count((False, 'active'))}, "
           f"exclusions {le.count((True, 'active'))}, quarantined {sum(s == 'quarantined' for _, s in le)}; "
           f"events pending {len(pending)}"]
    byq = {}
    for k, q in sorted(Q.items(), key=lambda kq: (kq[1].get("priority") == "secondary", kq[0])):  # primary seeds first
        byq.setdefault(q["status"], []).append(k + (f"@{q['rung']}" if q["status"] == "resolved" and q.get("rung") else "")
                                               + ("(2nd)" if q.get("priority") == "secondary" else ""))
    out.append("questions: " + (" | ".join(f"{s} {' '.join(byq[s])}" for s in Q_STATUSES if s in byq) or "none"))
    lanes = []
    for qid, q in sorted(Q.items()):
        if q["status"] != "active":
            continue
        rung, bc = best_rung(st, qid)
        hold = f" HELD({holds_desc(st, q)})" if q.get("held_by") else ""
        lanes.append(f"{qid} [{q.get('tier') or '-'}] N={q.get('slots') or '-'} {q.get('plausibility') or '-'} "
                     f"round {q['round']} (budget {budget_used(q)}/{lane_budget(st, q)}) "
                     f"{lane_stage(st, qid)}{hold} | best accepted {rung or 'none'}"
                     + (assumes_note(C[bc].get("assumes") or []) if bc else "") + f" | {cell(q['title'], 40)}")
        for k, c in sorted(C.items()):
            if (c.get("lane") == qid and c["status"] == "proposed" and not superseded_by(st, k)
                    and (c.get("round") == q["round"] or missing_scopes(st, k))):
                lanes.append(f"  {k} {c.get('claims') or '-'} {c['kind']} r{c.get('round') or '-'}: "
                             f"{gate_summary(st, k)} => {outcome(st, run, k)}")
    tasks = [f"  {k} {t['status']} {t['role']}" + (f"/{t['mode']}" if t.get("mode") else "")
             + (f" {t['lane']} r{t.get('round')}" if t.get("lane") else "")
             + f" ctx {t.get('context') or '-'} {t.get('isolation')}" + (f" | {cell(t['title'], 40)}" if t.get("title") else "")
             for k, t in sorted(T.items()) if full or t["status"] in ("queued", "running", "unknown")]
    evs = [f"  {e['id']} {e['type']}" + (f" {e['lane']}" if e.get("lane") else "")
           + f": {cell(e.get('note'), 50)} -> first: "
           + ("focused ending: consolidate or a failure report, no RENEW" if focused_ending(run, st, e)
              else event_action(st, e["type"], e.get("lane"))) for e in pending]
    quar = sorted(k for k, e in L.items() if e["status"] == "quarantined") + \
        sorted(k for k, c in C.items() if c["status"] == "quarantined")
    out += capped("LANES:", lanes, 20, full) + capped("TASKS (live/unknown):", tasks, 7, full)
    out += capped("EVENTS PENDING:", evs, 5, full)
    if quar:
        out.append("QUARANTINED: " + " ".join(quar[:20]) + (" ..." if len(quar) > 20 else ""))
    out += capped("SUGGESTED NEXT ACTIONS:", ["  - " + x for x in acts], 18, full) or ["SUGGESTED NEXT ACTIONS:", "  - (none)"]
    if not full and len(out) > STATUS_LINES:
        out = out[:STATUS_LINES - 1] + ["... (truncated; status --full)"]
    return out


def cmd_status(a):
    run, st = open_run(a)
    block = build_status(run, st)
    if not a.no_write:  # K51: observers read without rewriting the checkpoint
        cp = run / "checkpoint.md"
        base = read(cp) if is_file(cp) else checkpoint_md()
        atomic_write(cp, replace_block(base, ST_BEGIN, ST_END, "\n".join(block)))
    if a.full:
        block = build_status(run, st, full=True)
    elif a.brief:
        block = build_status(run, st, brief=True)
    print("\n".join(block))


# ---------------------------------------------------------------- check

def check_findings(run, st):
    """Consistency audit; returns a list of findings (empty = consistent)."""
    F = []
    T, C, L, Q = st["tasks"], st["candidates"], st["ledger"], st["questions"]
    if st.get("after") not in (None,) + AFTER_CHOICES:
        F.append(f"after-delivery choice {st.get('after')!r} is not one of {', '.join(AFTER_CHOICES)}")
    if st.get("converted") and st["mode"] != "program":
        F.append(f"a conversion is recorded (seq {st['converted'].get('seq')}) but the mode is {st['mode']}")
    for prefix, table in (("Q", Q), ("T", T), ("C", C), ("L", L)):
        for k in table:
            if not re.fullmatch(prefix + r"\d+", k):
                F.append(f"malformed ID {k}")
            elif int(k[1:]) > st["counters"].get(prefix, 0):
                F.append(f"{k} exceeds the {prefix} counter (IDs must come from ri.py)")
    for label, keys in (("event", [e["id"] for e in st["events"]]),
                        ("review (candidate, task)", [f"{r['cand']}/{r['task']}" for r in st["reviews"]])):
        F += [f"duplicate {label} {k}" for k in sorted({k for k in keys if keys.count(k) > 1})]
    on = {}
    for r in st["reviews"]:
        for o in r["objections"]:
            on.setdefault(o["id"], set()).add(r["cand"])
    F += [f"objection {oid} is used on several candidates ({', '.join(sorted(cs))}): resolve with --cand (D1)"
          for oid, cs in sorted(on.items()) if len(cs) > 1]
    for qid, q in Q.items():
        if not is_file(run / "questions" / f"{qid}.md"):
            F.append(f"{qid}: questions/{qid}.md is missing")
        if q["status"] == "active" and not xp(run / "lanes" / qid).is_dir():
            F.append(f"{qid}: active but lanes/{qid}/ is missing")
        F += [f"{qid}: held by unknown event {h}" for h in q.get("held_by") or []
              if h not in {e["id"] for e in st["events"]}]
    for tid, t in T.items():
        if not is_file(run / t["packet"]):
            F.append(f"{tid}: packet {t['packet']} is missing")
        F += [f"{tid}: {key} {t[key]} does not exist" for key in ("redo_of", "superseded_by", "brief")
              if t.get(key) and t[key] not in T]
    for cid, c in C.items():
        p = run / c["path"]
        if not is_file(p):
            F.append(f"{cid}: {c['path']} is missing")
        elif sha256_file(p) != c["sha256"]:
            F.append(f"{cid}: {c['path']} does not match its frozen sha256 (edited or tampered)")
        F += [f"{cid}: {x}" for x in attachment_problems(run, c)]
        if c["author"] not in T:
            F.append(f"{cid}: author task {c['author']} does not exist")
        F += [f"{cid}: {key} {c[key]} does not exist" for key in ("revises", "from") if c.get(key) and c[key] not in C]
        if c.get("lane") and c["lane"] not in Q:
            F.append(f"{cid}: lane {c['lane']} does not exist")
        if c["status"] == "accepted":
            F += [f"{cid}: accepted but gate fails: {p_}" for p_ in gate_check(st, run, cid)[0]
                  if not p_.startswith(("candidate file", "attachment "))]
    for r in st["reviews"]:
        if r["cand"] not in C or r["task"] not in T:
            F.append(f"review {r['cand']}/{r['task']}: unknown candidate or task")
        elif r["sha256"] != C[r["cand"]]["sha256"]:
            F.append(f"review {r['cand']}/{r['task']}: reviewed a different version")
        if r.get("report") and not is_file(run / r["report"]):
            F.append(f"review {r['cand']}/{r['task']}: report {r['report']} is missing")
        F += [f"{o['id']}: resolved_by {o['resolved_by']} does not exist" for o in r["objections"]
              if o.get("resolved_by") and o["resolved_by"] not in T and o["resolved_by"] not in C]
    for lid, e in L.items():
        if e["cand"] not in C:
            F.append(f"{lid}: source candidate {e['cand']} does not exist")
        elif e["status"] == "active" and C[e["cand"]]["status"] != "accepted":
            F.append(f"{lid}: active but its candidate {e['cand']} is {C[e['cand']]['status']}")
        if e["status"] == "active":
            F += [f"{lid}: dependency {d} is not active" for d in e.get("deps") or [] if L.get(d, {}).get("status") != "active"]
        if e["kind"] == "exclusion" and e["status"] == "active" and e["cand"] in C:
            if not re.fullmatch(r"Q\d+\.(R\d+|D)", e.get("excludes") or "") or (e["excludes"].split(".")[0] not in Q):
                F.append(f"{lid}: exclusion of unknown claim {e.get('excludes')!r}")
            else:
                prob = exclusion_problem(st, run, e["excludes"], e["cand"])
                if prob:
                    F.append(f"{lid}: invalid exclusion: {prob}")
    F += [contradiction_text(*x) + " (contradiction)" for x in contradictions(st, run)]
    F += [f"{k} ({C[k].get('claims') or C[k]['kind']}) passes its gates but {why} (contradiction)"
          for k, why in pending_conflicts(st, run)]
    F += ledger_cycles(L)
    ql, qc = quarantine_closure(st, {k for k, e in L.items() if e["status"] == "quarantined"},
                                {k for k, c in C.items() if c["status"] == "quarantined"})
    F += [f"{k}: should be quarantined (transitive closure)" for k in sorted(ql) if L[k]["status"] == "active"]
    F += [f"{k}: should be quarantined (transitive closure)" for k in sorted(qc) if C[k]["status"] == "accepted"]
    for e in st["events"]:
        if e.get("handled_by") and e["handled_by"] not in T:
            F.append(f"{e['id']}: handled_by {e['handled_by']} does not exist")
        if e.get("lane") and e["lane"] not in Q:
            F.append(f"{e['id']}: lane {e['lane']} does not exist")
    F += check_log(run, st)
    return F


def ledger_cycles(L):
    color, found = {}, []

    def visit(n, path):
        color[n] = 1
        for d in L[n].get("deps") or []:
            if d in L and color.get(d) == 1:
                found.append("ledger dependency cycle: " + " -> ".join(path + [d]))
            elif d in L and not color.get(d):
                visit(d, path + [d])
        color[n] = 2

    for n in sorted(L):
        if not color.get(n):
            visit(n, [n])
    return found


def check_log(run, st):
    lp = xp(Path(run) / "log.jsonl")
    if not lp.is_file():
        return ["log.jsonl is missing"]
    seqs, out = [], []
    for i, line in enumerate(lp.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                seqs.append(json.loads(line)["seq"])
            except (ValueError, KeyError, TypeError):
                out.append(f"log.jsonl line {i} does not parse")
    if any(b <= a for a, b in zip(seqs, seqs[1:])):
        out.append("log.jsonl seq is not strictly increasing (log edited, or ri.py commands ran in parallel?)")
    if seqs and seqs[-1] != st["seq"]:
        out.append(f"log.jsonl ends at seq {seqs[-1]} but state.json is at seq {st['seq']}")
    return out


def cmd_check(a):
    run = Path(a.run)
    sp = run / "state.json"
    if not is_file(sp):
        usage(f"{run} is not a run directory (no state.json)")
    dups = []

    def hook(pairs):
        keys = [k for k, _ in pairs]
        dups.extend(sorted({k for k in keys if keys.count(k) > 1}))
        return dict(pairs)

    try:
        st = json.loads(xp(sp).read_text(encoding="utf-8"), object_pairs_hook=hook)
    except json.JSONDecodeError as e:
        fail(f"check: state.json does not parse: {e}")
    findings = [f"duplicate JSON key {k}" for k in dups]
    if st.get("schema") != SCHEMA:
        findings.append(f"schema is {st.get('schema')!r}, expected {SCHEMA}")
    else:
        try:
            findings += check_findings(run, st)
        except (KeyError, TypeError, AttributeError, ValueError) as e:
            findings.append(f"malformed state record: {e!r}")
    running = [k for k, t in st.get("tasks", {}).items() if isinstance(t, dict) and t.get("status") == "running"]
    print(f"running tasks: {', '.join(running) or 'none'}")
    warnings = checkpoint_warnings(run)
    if a.progress and st.get("schema") == SCHEMA:
        try:
            warnings += [f"progress.md: {x}" for x in progress_findings(run, st)]
        except (KeyError, TypeError, AttributeError, ValueError):
            pass  # a malformed state record is already a finding
    for w in warnings:  # warnings never change the exit code
        print(f"warning: {w}")
    if findings:
        fail(f"check: {len(findings)} finding(s):\n" + "\n".join(f"  - {f}" for f in findings))
    print("check OK")


def checkpoint_warnings(run):
    """K18: checkpoint.md is rewritten whole each iteration, with at most about 60 lines of notes
    outside the ri:status block and a '## Next actions' section."""
    text = read(Path(run) / "checkpoint.md")
    if not text:
        return []
    if ST_BEGIN in text and ST_END in text:
        head, rest = text.split(ST_BEGIN, 1)
        text = head + rest.split(ST_END, 1)[1]
    lines = [x for x in text.splitlines() if x.strip()]
    out = [f"checkpoint.md has {len(lines)} non-empty lines outside the status block (at most about 60): "
           "rewrite it whole; history goes to the Log"] if len(lines) > 60 else []
    if not any(re.match(r"#{1,6}\s+Next actions\b", x.strip(), re.I) for x in lines):
        out.append("checkpoint.md has no '## Next actions' heading")
    return out


# ---------------------------------------------------------------- CLI

TWO_WORD = {"q": ("add", "set"), "task": ("new", "set"), "cand": ("add",), "review": ("add",),
            "objection": ("resolve",)}
LOCK_FREE = ("check",)


def normalize_argv(argv):
    """Join two-word commands ('q add' -> 'q add' as one token); 'ledger add' vs 'ledger RUN'."""
    if argv and argv[0] in TWO_WORD:
        if len(argv) < 2 or argv[1] not in TWO_WORD[argv[0]]:
            usage(f"'{argv[0]}' needs one of: {', '.join(TWO_WORD[argv[0]])}")
        return [f"{argv[0]} {argv[1]}"] + argv[2:]
    if argv[:2] == ["ledger", "add"]:
        return ["ledger add"] + argv[2:]
    return argv


def build_parser():
    p = argparse.ArgumentParser(prog="ri.py", description=__doc__.split("\n\n")[0],
                                epilog="Exit codes: 0 ok; 1 refused or gate/audit failure; 2 usage error. "
                                       "Run commands one at a time; pass free text with the -file flags.")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True
    up, low = str.upper, str.lower

    def cmd(name, func, text):
        s = sub.add_parser(name, help=text, description=text)
        s.add_argument("run", metavar="RUN", help="run directory")
        s.set_defaults(func=func)
        return s

    def text_opt(s, name, help_=None):
        s.add_argument(f"--{name}", help=help_)
        s.add_argument(f"--{name}-file", metavar="PATH", help=f"read --{name} from a UTF-8 file (no shell expansion)")

    s = cmd("init", cmd_init, "create the run skeleton (refuses if state.json exists)")
    text_opt(s, "objective", "the user's objective, verbatim")
    text_opt(s, "key-difference", "the key difference X, verbatim")
    s.add_argument("--mode", type=low, choices=("program", "focused"), default="program")
    s.add_argument("--after", type=low, choices=AFTER_CHOICES, default="continue",
                   help="focused mode: after delivering the claim, continue as a research program (default) or stop "
                        "(only when the user's own words limit the run to this claim: give them with --stop-quote; a "
                        "budget keeps continue: program.md sec. 3)")
    text_opt(s, "stop-quote", "with --after stop: the user's words that limit the run to this claim, verbatim")
    s.add_argument("--isolation", type=up, choices=("L2", "L1"), required=True,
                   help="from the capability card: L2 = fresh worker contexts, L1 = role passes in one context")
    s.add_argument("--k", type=int, help="K, max concurrent workers (from the capability card)")
    s.add_argument("--lane-budget", type=int, default=8)
    s.add_argument("--no-code", action="store_true",
                   help="workers cannot run code (capability card worker_io: shell no): no WITNESS gate")
    s = cmd("intake", cmd_intake, "unpack a zip/tar bundle safely into sources/raw/ and add sources/index.md rows")
    s.add_argument("--archive", required=True, metavar="FILE")
    s.add_argument("--max-mb", type=int, default=500,
                   help="cap on the total unpacked size (default 500; a higher cap is recorded in contract.md)")
    s.add_argument("--only", action="append", metavar="PREFIX",
                   help="extract only members under this path prefix inside the archive (repeatable)")
    s = cmd("status", cmd_status, "status block with SUGGESTED NEXT ACTIONS; also written into checkpoint.md")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--full", action="store_true", help="everything, uncapped")
    g.add_argument("--brief", action="store_true", help="at most 15 lines (the checkpoint block stays full)")
    s.add_argument("--no-write", action="store_true", help="do not rewrite checkpoint.md (observers)")
    s = cmd("q add", cmd_q_add, "create a question card (status draft)")
    s.add_argument("--title", required=True)
    s.add_argument("--tier", type=up, choices=TIERS)
    s.add_argument("--parent")
    s.add_argument("--operator")
    s.add_argument("--model")
    s.add_argument("--priority", type=low, choices=("primary", "secondary"),
                   help="a seed's priority from the user's notes (default primary); status lists primary seeds first")
    s = cmd("q set", cmd_q_set, "set question status, rung, tier, slots, budget, plausibility, model, title or note")
    s.add_argument("qid", metavar="Qxx")
    s.add_argument("--status", type=low, choices=Q_STATUSES)
    s.add_argument("--rung")
    s.add_argument("--tier", type=up, choices=TIERS)
    s.add_argument("--slots", type=int, help="the lane's N (prover slots per round)")
    s.add_argument("--budget", type=int, help="this lane's rounds before a lane-budget event (overrides the run's)")
    s.add_argument("--plausibility", type=low, choices=PLAUSIBILITY, help="the skeptic's verdict")
    s.add_argument("--model")
    s.add_argument("--title")
    text_opt(s, "note")
    s = cmd("round", cmd_round, "open the next lane round (writes round-NN/plan.md's header line)")
    s.add_argument("qid", metavar="Qxx")
    s.add_argument("--open", action="store_true")
    s.add_argument("--override-hold", action="store_true", help="open a round on a held lane (investigator's decision only)")
    s.add_argument("--gate-only", action="store_true",
                   help="a round with no provers that gates a skeptic's argument (program.md sec. 5.3); it counts "
                        "toward neither the lane cap nor the lane's round budget")
    s = cmd("task new", cmd_task_new, "assign Txxx and build tasks/Txxx/packet.md (default Assignment where one exists)")
    s.add_argument("--role", type=low, choices=ROLES)
    s.add_argument("--mode")
    s.add_argument("--lane")
    s.add_argument("--round", type=int)
    s.add_argument("--title")
    s.add_argument("--cand", help="candidate IDs the task targets (comma list)")
    s.add_argument("--direction", help='e.g. "PROVE Q07.R1" (summarizer, prover)')
    s.add_argument("--brief", metavar="Txxx", help="the summarizer task whose briefing.md a prover reads")
    s.add_argument("--question", metavar="Qxx", help="question(s) for a skeptic QUESTION-GATE, or with a MODEL-GATE (comma list)")
    s.add_argument("--objection", metavar="Txxx.Ok", help="the objection an ADJUDICATE task rules on")
    s.add_argument("--light", action="store_true", help="skeptic QUESTION-GATE (or MODEL-GATE with --question) only: "
                                                         "a light gate (checks 1-3b)")
    s.add_argument("--assignment-file", metavar="PATH", help="the whole Assignment, from a file")
    s.add_argument("--extra", action="append", metavar="TEXT", help="a line appended to the Assignment (repeatable)")
    s.add_argument("--extra-file", metavar="PATH", help="lines appended to the Assignment, from a file")
    s.add_argument("--start", action="store_true", help="mark the task running now (before the spawn); writes dispatch.md")
    s.add_argument("--context", help="context label (default with --start: the task ID)")
    s.add_argument("--isolation", type=up, choices=("L2", "L1"), help="default: the run's isolation")
    s.add_argument("--redo", metavar="Txxx", help="redo Txxx: copy its role, inputs and Assignment; supersede it")
    s.add_argument("--force-empty", action="store_true", help="allow --start with the placeholder (recovery only)")
    s = cmd("task set", cmd_task_set, "record status, context label and isolation of one or more tasks")
    s.add_argument("ids", nargs="+", metavar="Txxx", help="task IDs, optionally followed by a STATUS word")
    s.add_argument("--status")
    s.add_argument("--context")
    s.add_argument("--isolation", type=up, choices=("L2", "L1"))
    text_opt(s, "note")
    s.add_argument("--force-empty", action="store_true", help="allow running with the placeholder (recovery only)")
    s = cmd("ingest", cmd_ingest, "integrate returned tasks from their result.md headers")
    s.add_argument("tids", nargs="+", metavar="Txxx")
    s.add_argument("--accept", action="store_true", help="accept candidates whose gates now hold; ledger add lane results and fragments")
    s.add_argument("--brief", action="store_true", help="only task status lines, what is left and the manual block")
    s = cmd("file-cards", cmd_file_cards, "file literature-reviewer cards (sources/Sxx.md, deduped), bound rows "
                                          "(sources/bounds.md) and raw/ downloads; logs new-source after MODEL")
    s.add_argument("tids", nargs="+", metavar="Txxx")
    s = cmd("cand add", cmd_cand_add, "freeze a draft as candidates/Cxxx.md with its sha256")
    s.add_argument("--lane")
    s.add_argument("--claims", metavar="Qxx.Ri|Qxx.D|TEXT")
    s.add_argument("--file", required=True)
    s.add_argument("--author", required=True)
    s.add_argument("--kind", type=low, choices=KINDS)
    s.add_argument("--direction", help='the prover\'s direction, e.g. "PROVE Q07.R1"')
    s.add_argument("--method")
    s.add_argument("--deps", metavar="L001,L002")
    s.add_argument("--revises", metavar="Cxxx")
    s.add_argument("--from", dest="from_", metavar="Cxxx", help="source candidate of an auditor fragment or dead end")
    s.add_argument("--step", help="the confirmed step of the source a fragment rewrites, e.g. 'Lemma 2'")
    s.add_argument("--round", type=int)
    s.add_argument("--gap")
    s.add_argument("--allow-pending-deps", action="store_true")
    s.add_argument("--for", dest="for_", metavar="Qxx|Hn|Cxxx",
                   help="the citer: the question, story.md headline or candidate that uses this fact as a premise "
                        "(required for an implied-Qxx.md argument)")
    s.add_argument("--attach", nargs="+", action="extend", metavar="FILE",
                   help="data files a computer-assisted step uses: copied to candidates/Cxxx/ and hashed")
    s = cmd("review add", cmd_review_add, "record a review (checks staleness, independence, objection IDs)")
    s.add_argument("--cand", required=True)
    s.add_argument("--scope", type=low, choices=SCOPES, required=True)
    s.add_argument("--task", required=True)
    s.add_argument("--verdict", type=up, choices=VERDICTS, required=True)
    s.add_argument("--fidelity", type=up, choices=FIDELITIES)
    s.add_argument("--assumes", help="an allowed simplifying assumption the proof uses (still MATCH)")
    s.add_argument("--blocking", help='"O1 CRITICAL: <location> [<TAG>] - <one line>; O2 MAJOR: ..."')
    s.add_argument("--report")
    text_opt(s, "note")
    s.add_argument("--confirmed", help='confirmed steps, e.g. "Lemma 2; Claim 3.1" (feeds the ledger auditor)')
    s = cmd("objection resolve", cmd_objection_resolve, "resolve an objection (original record kept)")
    s.add_argument("objection", metavar="Txxx.Ok")
    s.add_argument("--how", type=low, choices=("fixed", "rejected", "withdrawn"), required=True)
    s.add_argument("--by", required=True)
    s.add_argument("--cand", help="the candidate the objection was raised on (required when ambiguous)")
    text_opt(s, "note")
    s = cmd("accept", cmd_accept, "accept a candidate if its gate holds (I3/I4); exit 1 lists what is missing")
    s.add_argument("cand", metavar="Cxxx")
    s = cmd("ledger add", cmd_ledger_add, "create a ledger entry from an accepted candidate")
    s.add_argument("--cand", required=True)
    text_opt(s, "statement", "the entry's statement (default: the candidate's Theorem/Statement paragraph)")
    s = cmd("exclude", cmd_exclude, "record an exclusion (refuted rungs) from an accepted counterexample or proof of D")
    s.add_argument("--claim", required=True)
    s.add_argument("--cand", required=True)
    text_opt(s, "note")
    s = cmd("quarantine", cmd_quarantine, "quarantine a ledger entry (or candidate) and all dependants")
    s.add_argument("target", metavar="Lxxx|Cxxx")
    s.add_argument("--code", type=low, choices=QUARANTINE_CODES, required=True,
                   help="the verification.md sec. 9 reason; a label or metadata in a file is never one")
    text_opt(s, "reason")
    cmd("record", cmd_record, "regenerate lanes/Qxx/record.md").add_argument("qid", metavar="Qxx")
    cmd("ledger", cmd_ledger, "regenerate ledger.md")
    s = cmd("event", cmd_event, "log a renewal event (holds a lane for stall, lane-budget, literature-hit, "
                                "new-source), or mark events handled (releases holds)")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--type", type=low, choices=EVENT_TYPES)
    g.add_argument("--handled", nargs="+", metavar="E#")
    s.add_argument("--lane")
    text_opt(s, "note")
    s.add_argument("--by", metavar="Txxx", help="with --handled: the task that handled the events (any existing task: "
                                                "RENEW, SELECT, BREADTH, comparator, writer, ...)")
    for name, text in (("stop", "create the STOP sentinel and log it"), ("pause", "create the PAUSE sentinel and log it"),
                       ("resume", "remove PAUSE files (with --stop also STOP files) and log it")):
        s = cmd(name, cmd_control, text)
        text_opt(s, "reason")
        if name == "resume":
            s.add_argument("--stop", action="store_true", help="also lift a STOP (only on the user's explicit words)")
    s = cmd("mode", cmd_mode, "after a focused delivery: convert the run to program mode (program.md sec. 3); "
                              "never re-runs intake")
    s.add_argument("--to", type=low, choices=("program",), required=True)
    text_opt(s, "reason", "why (the contract's 'After delivery: continue', or the user's words)")
    s = cmd("check", cmd_check, "consistency audit (exit 1 with findings); warnings never change the exit code")
    s.add_argument("--progress", action="store_true", help="also lint progress.md (warnings)")
    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
    try:
        argv = normalize_argv(argv)
        try:
            args = build_parser().parse_args(argv)
        except SystemExit as e:  # argparse: usage error (2) or --help (0)
            return int(e.code or 0)
        args.run = os.path.abspath(args.run)  # B8: once, so '.' or a relative RUN is absolute from here on
        run = Path(args.run)
        if args.command == "init":
            if IS_WINDOWS and len(str(apath(run))) > PATH_WARN:  # B8: before anything can fail on length
                print(f"warning: the run path is {len(str(apath(run)))} characters; worker files may pass the "
                      "260-character MAX_PATH limit. Use a short path such as C:\\ri\\<name> or a short folder "
                      "inside the host workspace.", file=sys.stderr)
            xp(run).mkdir(parents=True, exist_ok=True)
        if args.command in LOCK_FREE or not xp(run).is_dir():
            args.func(args)
        else:
            with run_lock(run):
                args.func(args)
        return 0
    except RiError as e:
        print(f"ri.py: {'usage error' if e.code == 2 else 'refused'}: {e}", file=sys.stderr)
        return e.code
    except OSError as e:  # e.g. Windows MAX_PATH: keep run directories short
        print(f"ri.py: file system error: {e} (on Windows keep the run directory path short)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
