"""Tests for scripts/ri.py (stdlib unittest).

Every test builds a temporary fake skill directory (prompts/_envelope.md and
prompts/<role>.md) and points RI_SKILL_DIR at it, and keeps its run directory in
a temporary directory. Nothing is written inside the real skill folder.

Run:  python -B -m unittest discover -s tests -v     (from the skill directory;
      -B keeps bytecode caches out of the skill folder)
"""
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

SCRIPT = Path(os.path.abspath(__file__)).parent.parent / "scripts" / "ri.py"
sys.dont_write_bytecode = True  # no __pycache__ inside the skill folder
sys.path.insert(0, str(SCRIPT.parent))
import ri  # noqa: E402

INSTRUCTIONS = """# Standing instructions

Revision 3

## SI-1 Lemma DAG
applies: prover
review-safe: no
Provers submit a numbered lemma DAG.

## SI-2 Paths
applies: all
review-safe: yes
Pass long documents by path.

## SI-3 Verifier hint
applies: verifier
review-safe: no
Unsafe hint for verifiers.

## SI-4 Check citations
applies: verifier, skeptic
review-safe: yes
Open every cited source.
"""

# The literal example of prompts/process-advisor.md (C5 format).
ADVISOR_EXAMPLE = """# Standing instructions
revision: 5

## SI03
applies: prover, verifier
review-safe: yes
text: Every O(·), Ω(·) or constant states what it depends on; dependence on k appears in the theorem statement.
reason: CONST objections T045.O1, T050.O2, T061.O1 in three rounds.
since: 2

## Removed in revision 5
- SI01: pattern absent for 7 lane-rounds.
"""



def with_isolation(args):
    """`init` requires --isolation (from the capability card); tests default to L2."""
    args = tuple(str(a) for a in args)
    if args[:1] == ("init",) and "--isolation" not in args:
        args += ("--isolation", "L2")
    return args

class RiCase(unittest.TestCase):
    """Fixture: fake skill dir + run dir in a TemporaryDirectory."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.skill = base / "skill"
        (self.skill / "prompts").mkdir(parents=True)
        (self.skill / "prompts" / "_envelope.md").write_text("ENVELOPE RULES: finish with result.md\n", encoding="utf-8")
        for role in ri.ROLES:
            (self.skill / "prompts" / f"{role}.md").write_text(f"ROLE PROMPT {role}\n", encoding="utf-8")
        self.env = mock.patch.dict(os.environ, {"RI_SKILL_DIR": str(self.skill)})
        self.env.start()
        self.R = str(base / "run")
        self.n = 0

    def tearDown(self):
        self.env.stop()
        if os.name == "nt":  # a run directory beyond 260 characters is removed only in the extended-length form
            shutil.rmtree("\\\\?\\" + os.path.abspath(self.tmp.name), ignore_errors=True)
        self.tmp.cleanup()

    # -- helpers
    def ri(self, *args, code=0):
        args = with_isolation(args)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            got = ri.main([str(a) for a in args])
        if code is not None:
            self.assertEqual(got, code, f"ri {args} -> {got}\nstdout:\n{out.getvalue()}\nstderr:\n{err.getvalue()}")
        return out.getvalue() + err.getvalue()

    def init(self, *extra):
        self.ri("init", self.R, "--objective", "Explore bounds for task T", "--key-difference", "now allow resource X", *extra)

    def state(self):
        return json.loads(ri.xp(Path(self.R, "state.json")).read_text(encoding="utf-8"))

    def save(self, st):
        ri.xp(Path(self.R, "state.json")).write_text(json.dumps(st), encoding="utf-8")

    def path(self, *parts):
        return Path(self.R, *parts)

    def write(self, rel, text):
        p = ri.xp(self.path(*rel.split("/")))  # the extended-length form when the run directory is deep
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return rel

    def task(self, role, mode=None, lane=None, ctx=None, title=None, rnd=None, fill=True, extra=()):
        """task new; fill=True adds a one-line Assignment so the task may be marked running."""
        args = ["task", "new", self.R, "--role", role]
        args += ["--mode", mode] if mode else []
        args += ["--lane", lane] if lane else []
        args += ["--title", title] if title else []
        args += ["--round", rnd] if rnd is not None else []
        args += ["--extra", "Test assignment."] if fill else []
        tid = self.ri(*args, *extra).split()[0]
        if ctx:
            self.ri("task", "set", self.R, tid, "running", "--context", ctx)
        return tid

    def r1(self, qid="Q01"):
        """Give a question's card an exact R1 (a QUESTION-GATE is refused without one)."""
        card = ri.xp(self.path("questions", f"{qid}.md"))
        card.write_text(re.sub(r"(?m)^R1:.*$", "R1: x", card.read_text(encoding="utf-8")), encoding="utf-8")

    def lane(self, title="Does X help?"):
        qid = self.ri("q", "add", self.R, "--title", title, "--tier", "CORE", "--model", "M1").split()[0]
        self.ri("q", "set", self.R, qid, "--status", "active")
        self.ri("round", self.R, qid, "--open")
        return qid

    def cand(self, author, claims="Q01.R1", *extra, text=None):
        self.n += 1
        draft = ri.xp(self.path("tasks", author, f"draft{self.n}.md"))
        draft.write_text(text or f"# Theorem {self.n}\nProof body {self.n}.\n", encoding="utf-8")
        args = ["cand", "add", self.R, "--file", f"tasks/{author}/draft{self.n}.md", "--author", author]
        args += ["--claims", claims] if claims else []
        return self.ri(*args, *extra).split()[0]

    def review(self, cid, tid, scope, verdict, *extra, code=0, fidelity="MATCH"):
        """Record a review. Main gates (individual, cross) report fidelity, as verifiers must;
        pass fidelity=None to omit it."""
        if scope in ("individual", "cross") and fidelity and "--fidelity" not in extra:
            extra = extra + ("--fidelity", fidelity)
        return self.ri("review", "add", self.R, "--cand", cid, "--task", tid, "--scope", scope,
                       "--verdict", verdict, *extra, code=code)

    def accepted(self, claims="Q01.R1", *extra):
        """A candidate that passes both gates and is accepted."""
        p = self.task("prover", "PROVE", lane=claims.split(".")[0])
        c = self.cand(p, claims, *extra)
        self.review(c, self.task("verifier", "INDIVIDUAL", lane="Q01"), "individual", "PASS", "--fidelity", "MATCH")
        self.review(c, self.task("verifier", "CROSS-DRAFT", lane="Q01"), "cross", "PASS", "--fidelity", "MATCH")
        self.ri("accept", self.R, c)
        return c

    def accepted_ce(self, claims="Q01.R2"):
        """An accepted counterexample from a prover cohort (INDIVIDUAL + WITNESS + CROSS-DRAFT)."""
        p = self.task("prover", "DISPROVE", lane=claims.split(".")[0])
        ce = self.cand(p, claims, "--kind", "counterexample")
        self.review(ce, self.task("verifier", "INDIVIDUAL", lane="Q01"), "individual", "PASS")
        self.review(ce, self.task("scout", "WITNESS", lane="Q01"), "witness", "PASS")
        self.review(ce, self.task("verifier", "CROSS-DRAFT", lane="Q01"), "cross", "PASS")
        self.ri("accept", self.R, ce)
        return ce

    def result(self, tid, *lines, status="completed", body="Body.\n"):
        t = self.state()["tasks"][tid]
        text = (f"---\ntask: {tid}\nrole: {t['role']}\nstatus: {status}\nsummary: test result\n"
                + "".join(x + "\n" for x in lines) + "---\n" + body)
        ri.xp(self.path("tasks", tid, "result.md")).write_text(text, encoding="utf-8")

    def assignment(self, tid):
        text = ri.xp(self.path("tasks", tid, "packet.md")).read_text(encoding="utf-8")
        return text.split("## Assignment\n\n", 1)[1].split("\n\n## Role instructions", 1)[0]

    def status(self, *extra):
        return self.ri("status", self.R, *extra)

    def selected(self):
        """A finished investigator SELECT: from then on, program-mode events route to RENEW (program.md sec. 7)."""
        sel = self.task("investigator", "SELECT")
        self.ri("task", "set", self.R, sel, "done")
        return sel


class TestInit(RiCase):
    def test_init_skeleton(self):
        self.init()
        for d in ("sources/raw", "frontier", "questions", "lanes", "candidates", "tasks", "scout", "reports"):
            self.assertTrue(self.path(d).is_dir(), d)
        for f in ("contract.md", "checkpoint.md", "progress.md", "sources/index.md", "frontier/model.md",
                  "frontier/map.md", "frontier/transfer.md", "frontier/story.md", "ledger.md",
                  "instructions.md", "state.json", "log.jsonl"):
            self.assertTrue(self.path(f).is_file(), f)
        st = self.state()
        self.assertEqual((st["schema"], st["mode"], st["isolation_default"], st["lane_budget"]), (6, "program", "L2", 8))
        self.assertEqual(st["objective"], "Explore bounds for task T")
        contract = self.path("contract.md").read_text(encoding="utf-8")
        for section in ("Objective", "Key difference", "Mode", "Scope boundaries", "Limits", "Lane budgets",
                        "## Capability card (checked <date>)", "now allow resource X"):
            self.assertIn(section, contract)
        card = contract.split("## Capability card (checked <date>)\n", 1)[1].splitlines()
        self.assertEqual([x.split(":")[0] for x in card if x.strip()],
                         ["isolation", "dispatch", "K", "worker_io", "solvers", "file_scope", "python", "skill_dir",
                          "run_dir", "turn_model"])
        self.assertIn(f"run_dir:    {os.path.abspath(self.R)}", contract)
        self.assertIn("revision: 0", self.path("instructions.md").read_text(encoding="utf-8"))
        pointer = f"Driven by research-investigator (skill_dir {os.path.abspath(str(self.skill))}); to resume read SKILL.md §5."
        cp = self.path("checkpoint.md").read_text(encoding="utf-8").splitlines()
        self.assertEqual(cp[0], pointer)
        self.assertEqual(self.path("progress.md").read_text(encoding="utf-8").splitlines()[0], pointer)
        heads = [x for x in cp if x.startswith("## ")]
        self.assertEqual(heads, ["## Running", "## Waiting on", "## Pending events", "## Next actions", "## Notes"])
        self.assertLess(cp.index(ri.ST_END), cp.index("## Running"))
        self.assertIn("Picture", self.path("progress.md").read_text(encoding="utf-8"))
        log = self.path("log.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(x)["seq"] for x in log], [1])

    def test_init_refuses_existing_state(self):
        self.init()
        before = self.path("state.json").read_bytes()
        out = self.ri("init", self.R, "--objective", "other", code=1)
        self.assertIn("already exists", out)
        self.assertEqual(before, self.path("state.json").read_bytes())

    def test_init_into_existing_directory_keeps_files(self):
        raw = self.path("sources", "raw")
        raw.mkdir(parents=True)
        (raw / "paper.pdf").write_bytes(b"%PDF")
        self.init("--mode", "focused", "--isolation", "L1", "--lane-budget", "5")
        self.assertEqual((raw / "paper.pdf").read_bytes(), b"%PDF")
        self.assertEqual(self.state()["mode"], "focused")
        self.assertIn("isolation:  L1 only", self.path("contract.md").read_text(encoding="utf-8"))

    def test_usage_errors_exit_2(self):
        self.ri("nonsense", self.R, code=2)
        self.ri("q", self.R, code=2)
        self.ri("status", self.R, code=2)  # no state.json yet
        self.init()
        self.ri("q", "set", self.R, "QX", "--status", "ready", code=2)
        self.ri("q", "set", self.R, "Q09", "--status", "ready", code=2)
        self.ri("init", self.R, code=1)  # state exists: refused before argument checks

    def test_free_text_files_keep_dollar_and_backticks(self):
        tmp = Path(self.tmp.name)
        (tmp / "obj.txt").write_text("Bound $c(k)$ for `task` T\n", encoding="utf-8")
        (tmp / "kd.txt").write_text("now allow $X advice bits\n", encoding="utf-8")
        self.ri("init", self.R, "--objective-file", tmp / "obj.txt", "--key-difference-file", tmp / "kd.txt", "--k", "6")
        st = self.state()
        self.assertEqual((st["objective"], st["key_difference"], st["k"]),
                         ("Bound $c(k)$ for `task` T", "now allow $X advice bits", 6))
        contract = self.path("contract.md").read_text(encoding="utf-8")
        self.assertIn("now allow $X advice bits", contract)
        self.assertIn("K:          6", contract)
        other = str(Path(self.tmp.name, "run2"))
        self.ri("init", other, "--objective", "x", "--objective-file", tmp / "obj.txt", code=2)
        self.ri("init", other, "--key-difference", "y", code=2)  # no objective
        self.ri("init", other, "--objective", "x", "--k", "0", code=2)

    def test_long_run_path_warning_on_windows(self):
        with mock.patch.object(ri, "IS_WINDOWS", True), mock.patch.object(ri, "PATH_WARN", 10):
            out = self.ri("init", self.R, "--objective", "x")
        self.assertIn("warning: the run path is", out)
        self.assertIn("C:\\ri\\<name>", out)
        with mock.patch.object(ri, "IS_WINDOWS", False), mock.patch.object(ri, "PATH_WARN", 10):
            self.assertNotIn("warning", self.ri("init", str(Path(self.tmp.name, "r2")), "--objective", "x"))


class TestControl(RiCase):
    def setUp(self):
        super().setUp()
        self.init()

    def test_stop_txt_and_lowercase_variants_are_detected(self):
        for name in ("STOP.txt", "stop", "Stop.md"):
            p = self.path(name)
            p.write_text("", encoding="utf-8")
            self.assertEqual(ri.control_flags(self.R)["STOP"], [p])
            out = self.status()
            self.assertIn("STOP YES", out)
            self.assertIn(f"STOP in force ({name} at", out)
            self.assertIn("STOP in force", self.ri("task", "new", self.R, "--role", "scout", "--extra", "x", code=1))
            p.unlink()
        self.path("PAUSE.txt").write_text("", encoding="utf-8")
        self.assertIn("PAUSE YES", self.status())
        self.assertEqual(self.state()["counters"]["T"], 0)

    def test_task_set_running_refused_under_stop(self):
        tid = self.task("scout")
        self.ri("stop", self.R, "--reason", "user said stop")
        self.assertIn("STOP in force", self.ri("task", "set", self.R, tid, "running", code=1))
        self.ri("task", "set", self.R, tid, "cancelled")  # cancelling is allowed

    def test_resume_does_not_clear_stop_without_flag(self):
        self.ri("stop", self.R, "--reason", "user said stop")
        self.path("pause.md").write_text("", encoding="utf-8")
        out = self.ri("resume", self.R)
        self.assertIn("removed pause.md", out)
        self.assertIn("STOP still in force", out)
        self.assertTrue(self.path("STOP").is_file())
        self.assertFalse(self.path("pause.md").exists())
        self.assertIn("STOP in force", self.ri("task", "new", self.R, "--role", "scout", "--extra", "x", code=1))
        self.ri("resume", self.R, "--stop", code=2)  # the user's words are required
        Path(self.tmp.name, "words.txt").write_text("resume the stopped run at $RUN", encoding="utf-8")
        out = self.ri("resume", self.R, "--stop", "--reason-file", Path(self.tmp.name, "words.txt"))
        self.assertIn("removing STOP at", out)
        self.assertIn("(user said stop)", out)
        self.assertEqual(ri.control_flags(self.R), {"STOP": [], "PAUSE": []})
        last = json.loads(self.path("log.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(last["cmd"], "resume")
        self.assertEqual(last["args"]["reason"], "resume the stopped run at $RUN")
        self.assertTrue(any("user said stop" in x for x in last["args"]["old"]))

    def test_resume_removes_pause_variants_only(self):
        self.ri("pause", self.R, "--reason", "hold")
        self.path("Pause.txt").write_text("", encoding="utf-8")
        self.assertIn("PAUSE in force", self.status())
        self.ri("task", "new", self.R, "--role", "scout", "--extra", "x", code=1)
        out = self.ri("resume", self.R)
        self.assertIn("removed", out)
        self.assertEqual(ri.control_flags(self.R)["PAUSE"], [])
        self.ri("task", "new", self.R, "--role", "scout", "--extra", "x")
        cmds = [json.loads(x)["cmd"] for x in self.path("log.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(cmds[1:4], ["pause", "resume", "task new"])

    def test_status_under_stop_lists_only_control_and_reconcile(self):
        self.lane()
        p = self.task("prover", "PROVE", lane="Q01", ctx="a1")
        self.result(p, "direction: PROVE Q01.R1", "claims: none")
        self.task("verifier", "INDIVIDUAL", lane="Q01")
        self.ri("stop", self.R, "--reason", "enough")
        acts = self.status().split("SUGGESTED NEXT ACTIONS:")[1]
        lines = [x for x in acts.splitlines() if x.strip()]
        self.assertTrue(lines[0].strip().startswith("- STOP in force"))
        self.assertIn(f"{p}: result.md present - ingest", acts)
        self.assertNotIn("queued verifier", acts)
        self.assertNotIn("opening", acts)


class TestLock(RiCase):
    def test_ten_concurrent_task_new_calls_give_ten_tasks(self):
        self.init()
        env = dict(os.environ, RI_SKILL_DIR=str(self.skill))
        procs = [subprocess.Popen([sys.executable, "-B", str(SCRIPT), "task", "new", self.R, "--role", "prover",
                                   "--extra", f"job {i}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
                 for i in range(10)]
        outs = [p.communicate(timeout=120) for p in procs]
        self.assertEqual([p.returncode for p in procs], [0] * 10, [o[1] for o in outs])
        st = self.state()
        self.assertEqual(sorted(st["tasks"]), [f"T{i:03d}" for i in range(1, 11)])
        jobs = sorted(re.search(r"job \d", self.path("tasks", t, "packet.md").read_text(encoding="utf-8")).group(0)
                      for t in st["tasks"])
        self.assertEqual(jobs, sorted(f"job {i}" for i in range(10)))
        self.assertIn("check OK", self.ri("check", self.R))
        self.assertFalse(self.path(".ri.lock").exists())

    def test_stale_lock_is_taken_over(self):
        self.init()
        lock = self.path(".ri.lock")
        lock.write_text("pid 1 since long ago\n", encoding="utf-8")
        old = time.time() - ri.LOCK_STALE - 60
        os.utime(lock, (old, old))
        self.assertIn("stale lock", self.ri("q", "add", self.R, "--title", "t"))
        self.assertFalse(lock.exists())

    def test_live_lock_blocks_writers_but_not_check(self):
        self.init()
        self.path(".ri.lock").write_text("pid 99 since now\n", encoding="utf-8")
        with mock.patch.object(ri, "LOCK_WAIT", 0.3):
            out = self.ri("q", "add", self.R, "--title", "t", code=1)
        self.assertIn("run ri.py commands one at a time", out)
        self.assertIn("pid 99", out)
        self.ri("check", self.R)
        self.assertEqual(self.state()["questions"], {})


class TestTasks(RiCase):
    def setUp(self):
        super().setUp()
        self.init()
        self.path("instructions.md").write_text(INSTRUCTIONS, encoding="utf-8")
        self.q = self.lane()

    def test_packet_has_role_prompt_envelope_and_filtered_instructions(self):
        self.path("assign.md").write_text("Prove Q01.R1 using the lane statement.\n", encoding="utf-8")
        out = self.ri("task", "new", self.R, "--role", "prover", "--mode", "prove", "--lane", "q1",
                      "--title", "PROVE Q01.R1", "--assignment-file", "assign.md")
        tid = out.split()[0]
        self.assertEqual(tid, "T001")
        self.assertIn(os.path.abspath(self.R), out)
        packet = self.path("tasks", "T001", "packet.md").read_text(encoding="utf-8")
        self.assertTrue(packet.startswith("# Task T001 — prover (PROVE)"))
        for needle in (f"Run: {os.path.abspath(self.R)}", "Lane: Q01   Round: 1   Direction/target: PROVE Q01.R1",
                       "Output directory (write only here): tasks/T001/ (relative to Run)",
                       "## Assignment", "Prove Q01.R1 using the lane statement.", "ROLE PROMPT prover",
                       "ENVELOPE RULES", "## Standing instructions (revision 3)", "SI-1: Provers submit",
                       "SI-2: Pass long documents"):
            self.assertIn(needle, packet)
        self.assertNotIn("SI-3", packet)
        self.assertNotIn("SI-4", packet)
        self.assertTrue(self.assignment(tid).endswith(f"Stop condition: {ri.STOP_DEFAULT['prover']}."))
        task = self.state()["tasks"]["T001"]
        self.assertEqual((task["status"], task["role"], task["mode"], task["lane"], task["round"]),
                         ("queued", "prover", "PROVE", "Q01", 1))

    def test_review_packets_get_only_review_safe_rules(self):
        tid = self.task("verifier", "INDIVIDUAL", lane="Q01", fill=False)
        packet = self.path("tasks", tid, "packet.md").read_text(encoding="utf-8")
        self.assertIn("SI-2", packet)
        self.assertIn("SI-4", packet)
        self.assertNotIn("SI-3", packet)
        self.assertNotIn("SI-1", packet)
        self.assertIn(ri.PLACEHOLDER, packet)
        skeptic = self.path("tasks", self.task("skeptic", "QUESTION-GATE"), "packet.md").read_text(encoding="utf-8")
        self.assertIn("SI-4", skeptic)
        self.assertNotIn("SI-3", skeptic)

    def test_process_advisor_literal_example_is_parsed(self):
        rev, rules = ri.parse_instructions(ADVISOR_EXAMPLE)
        self.assertEqual(rev, 5)
        self.assertEqual([(r["id"], r["applies"], r["review_safe"]) for r in rules], [("SI03", ["prover", "verifier"], True)])
        self.assertTrue(rules[0]["text"].startswith("SI03: Every O(·), Ω(·) or constant"))
        self.path("instructions.md").write_text(ADVISOR_EXAMPLE, encoding="utf-8")
        for role, mode in (("prover", "PROVE"), ("verifier", "INDIVIDUAL"), ("summarizer", None)):
            packet = self.path("tasks", self.task(role, mode, lane="Q01"), "packet.md").read_text(encoding="utf-8")
            self.assertIn("## Standing instructions (revision 5)", packet)
            self.assertNotIn("reason:", packet)
            self.assertNotIn("T045.O1", packet)
            self.assertNotIn("Removed in revision", packet)
            self.assertNotIn("since:", packet)
            self.assertEqual("SI03: Every O(·)" in packet, role != "summarizer", role)

    def test_skill_process_advisor_prompt_example_parses(self):
        prompt = SCRIPT.parent.parent / "prompts" / "process-advisor.md"
        text = prompt.read_text(encoding="utf-8") if prompt.is_file() else ""
        m = re.search(r"```\n(# Standing instructions.*?)```", text, re.S)
        if not m:
            self.skipTest("no instructions.md example in the skill's prompts/process-advisor.md")
        rev, rules = ri.parse_instructions(m.group(1))
        self.assertGreater(rev, 0)
        self.assertTrue(rules)
        for r in rules:
            self.assertNotIn("reason:", r["text"])
            self.assertTrue(re.match(r"SI\d+: \S", r["text"]), r["text"])

    def test_missing_prompt_and_bad_mode(self):
        (self.skill / "prompts" / "scout.md").unlink()
        self.assertIn("missing prompt file", self.ri("task", "new", self.R, "--role", "scout", code=1))
        self.ri("task", "new", self.R, "--role", "prover", "--mode", "EXPLORE", code=2)
        self.ri("task", "new", self.R, "--role", "wizard", code=2)
        self.ri("task", "new", self.R, code=2)  # neither --role nor --redo
        self.assertEqual(self.state()["counters"]["T"], 0)
        self.ri("task", "new", self.R, "--role", "scout", "--mode", "ANCHOR", code=2)  # ANCHOR is an EXPLORE title
        for role, mode in (("scout", "CERTIFY"), ("literature-reviewer", "LANDSCAPE"),
                           ("investigator", "EXPLAIN"), ("verifier", "SALVAGE")):
            if role != "scout":
                self.task(role, mode)

    def test_task_set_placeholder_refusal_and_several_ids(self):
        tid = self.task("summarizer", lane="Q01", fill=False)
        out = self.ri("task", "set", self.R, tid, "running", "--context", "agent-7", code=1)
        self.assertIn("still the placeholder", out)
        self.ri("task", "set", self.R, tid, "running", "--context", "agent-7", "--force-empty")
        t = self.state()["tasks"][tid]
        self.assertEqual((t["status"], t["context"], t["isolation"]), ("running", "agent-7", "L2"))
        t2, t3 = self.task("scout"), self.task("scout")
        out = self.ri("task", "set", self.R, tid, t2, t3, "--status", "done", "--isolation", "L1")
        self.assertIn("result.md is missing", out)
        st = self.state()["tasks"]
        self.assertEqual([st[x]["status"] for x in (tid, t2, t3)], ["done"] * 3)
        self.ri("task", "set", self.R, t2, t3, "cancelled")
        self.assertEqual(self.state()["tasks"][t3]["status"], "cancelled")
        self.ri("task", "set", self.R, tid, "finished", code=2)
        self.ri("task", "set", self.R, tid, code=2)
        self.ri("task", "set", self.R, tid, "superseded", code=2)
        self.ri("task", "set", self.R, tid, "running", "--status", "done", code=2)

    def test_start_marks_running_and_prints_dispatch(self):
        out = self.ri("task", "new", self.R, "--role", "prover", "--direction", "PROVE Q01.R1", "--start")
        tid = out.split()[0]
        t = self.state()["tasks"][tid]
        self.assertEqual((t["status"], t["context"], t["isolation"], t["lane"], t["round"], t["direction"]),
                         ("running", tid, "L2", "Q01", 1, "PROVE Q01.R1"))
        pk = os.path.join(os.path.abspath(self.R), "tasks", tid, "packet.md")
        self.assertIn(f"dispatch: Read {pk} and follow it. Write only in "
                      f"{os.path.join(os.path.abspath(self.R), 'tasks', tid)}{os.sep} "
                      "and in the canonical files your packet says your role owns. "
                      "When done, reply with only the result.md header.", out)
        out = self.ri("task", "new", self.R, "--role", "scout", "--mode", "SANITY", "--extra", "x", "--start",
                      "--context", "sub-9", "--isolation", "L1")
        t = self.state()["tasks"][out.split()[0]]
        self.assertEqual((t["context"], t["isolation"]), ("sub-9", "L1"))
        self.assertIn("still the placeholder", self.ri("task", "new", self.R, "--role", "writer", "--start", code=1))
        self.ri("task", "new", self.R, "--role", "writer", "--start", "--force-empty")

    def test_extra_lines_come_before_the_stop_condition(self):
        Path(self.tmp.name, "x.txt").write_text("Focus on $k$ = 1 first.\nSecond line.\n", encoding="utf-8")
        tid = self.ri("task", "new", self.R, "--role", "summarizer", "--direction", "PROVE Q01.R1",
                      "--extra", "One more line.", "--extra-file", Path(self.tmp.name, "x.txt")).split()[0]
        lines = self.assignment(tid).splitlines()
        i = lines.index("One more line.")  # extra lines join the Inputs list, before "Never open" and "Return"
        self.assertEqual(lines[i:i + 3], ["One more line.", "Focus on $k$ = 1 first.", "Second line."])
        self.assertTrue(lines[i - 1].startswith("- standing instructions"))
        self.assertTrue(lines[i + 3].startswith("Never open:"))
        self.assertTrue(lines[-1].startswith("Stop condition:"))
        self.path("a.md").write_text("Do it.\nStop condition: after one page.\n", encoding="utf-8")
        tid = self.ri("task", "new", self.R, "--role", "writer", "--assignment-file", "a.md", "--extra", "Also this.").split()[0]
        self.assertEqual(self.assignment(tid).splitlines(),
                         ["Do it.", "Also this.", ri.RETURN_DEFAULT, ri.time_line("writer"), "Stop condition: after one page."])

    def test_round_requires_active_question(self):
        q2 = self.ri("q", "add", self.R, "--title", "Other").split()[0]
        self.ri("round", self.R, q2, "--open", code=1)
        self.ri("round", self.R, q2, code=2)
        self.assertEqual(self.ri("round", self.R, self.q, "--open").strip(), "2")
        self.assertTrue(self.path("lanes", "Q01", "round-02", "plan.md").is_file())
        self.assertIn("D refutes:", self.path("lanes", "Q01", "statement.md").read_text(encoding="utf-8"))
        self.assertIn("Sanity.", self.path("lanes", "Q01", "statement.md").read_text(encoding="utf-8"))


class TestDefaultAssignments(RiCase):
    def setUp(self):
        super().setUp()
        self.init()
        self.q = self.lane()
        self.write("sources/S03.md", "# S03 card\n")
        base = self.accepted("Q01.R3")
        self.ri("ledger", "add", self.R, "--cand", base)  # L001
        self.p = self.task("prover", "PROVE", lane="Q01", ctx="agent-p")
        self.c = self.cand(self.p, "Q01.R1", "--deps", "L001",
                           text="# Draft\n## Theorem\nFor all n. Uses S03 Thm 2.\n")

    def test_verifier_default_never_lists_record(self):
        out = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "INDIVIDUAL", "--cand", self.c, "--start")
        tid = out.split()[0]
        a = self.assignment(tid)
        for needle in (f"- candidates/{self.c}.md (frozen; claims Q01.R1)", "- lanes/Q01/statement.md (rung texts)",
                       "- frontier/model.md", "- candidates/C001.md (ledger entry L001)", "- sources/S03.md (cited)",
                       "standing instructions", "`review Cxxx:`"):
            self.assertIn(needle, a)
        for banned in ("record.md", "questions/", "notes.md", "briefing.md", f"tasks/{self.p}/"):
            self.assertNotIn(banned, a)
        t = self.state()["tasks"][tid]
        self.assertEqual((t["lane"], t["round"], t["cands"], t["title"]), ("Q01", 1, [self.c], f"INDIVIDUAL {self.c}"))
        for mode in ("CROSS-DRAFT", "SECOND-INDEPENDENT", "SALVAGE"):
            a = self.assignment(self.ri("task", "new", self.R, "--role", "verifier", "--mode", mode, "--cand", self.c).split()[0])
            self.assertIn(mode, a)
            self.assertNotIn("record.md", a)

    def test_never_include_is_enforced(self):
        out = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "INDIVIDUAL", "--cand", self.c,
                      "--extra", "Also read lanes/Q01/record.md.", code=1)
        self.assertIn("never-include", out)
        self.ri("task", "new", self.R, "--role", "verifier", "--mode", "CROSS-DRAFT", "--cand", self.c,
                "--extra", f"See tasks/{self.p}/notes.md", code=1)
        self.ri("task", "new", self.R, "--role", "scout", "--mode", "SANITY", "--cand", self.c,
                "--extra", f"Prover result: tasks/{self.p}/result.md", code=1)
        self.ri("task", "new", self.R, "--role", "summarizer", "--direction", "PROVE Q01.R1",
                "--extra", "Read questions/Q01.md too.", code=1)
        aud = self.task("ledger-auditor", lane="Q01")
        frag = self.cand(aud, None, "--from", self.c)
        self.ri("task", "new", self.R, "--role", "verifier", "--mode", "ISOLATED", "--cand", frag,
                "--extra", f"Its parent is {self.c}.", code=1)
        a = self.assignment(self.ri("task", "new", self.R, "--role", "verifier", "--mode", "ISOLATED", "--cand", frag).split()[0])
        self.assertIn(f"- candidates/{frag}.md", a)
        self.assertNotIn(self.c, a)
        self.assertEqual(self.state()["tasks"].get("T020"), None)

    def test_summarizer_prover_scout_auditor_defaults(self):
        s = self.ri("task", "new", self.R, "--role", "summarizer", "--direction", "prove q1.r1").split()[0]
        a = self.assignment(s)
        for needle in ("- direction: PROVE Q01.R1", "- lanes/Q01/statement.md", "- lanes/Q01/record.md", "- ledger.md", "- scout/"):
            self.assertIn(needle, a)
        self.assertNotIn("questions/", a)
        self.assertEqual(self.state()["tasks"][s]["title"], "brief PROVE Q01.R1")
        p = self.ri("task", "new", self.R, "--role", "prover", "--mode", "PROVE", "--direction", "PROVE Q01.R1",
                    "--brief", s).split()[0]
        a = self.assignment(p)
        self.assertIn(f"- tasks/{s}/briefing.md (your briefing; read it first)", a)
        self.assertIn("Obstacle to the assigned target", a)
        r = self.ri("task", "new", self.R, "--role", "prover", "--direction", f"REPAIR {self.c}").split()[0]
        self.assertIn(f"- candidates/{self.c}.md (the draft to repair)", self.assignment(r))
        sc = self.ri("task", "new", self.R, "--role", "scout", "--mode", "WITNESS", "--cand", self.c).split()[0]
        a = self.assignment(sc)
        self.assertIn("not the proof", a)
        self.assertIn("`check Cxxx: outcome=...; exact=...`", a)
        v = self.task("verifier", "INDIVIDUAL", lane="Q01")
        self.review(self.c, v, "individual", "FAIL", "--blocking", "O1 CRITICAL: Lemma 3 [PROB] - false",
                    "--confirmed", "Lemma 2", "--report", self.write(f"tasks/{v}/report.md", "r"))
        aud = self.ri("task", "new", self.R, "--role", "ledger-auditor", "--lane", "Q01", "--round", "1").split()[0]
        a = self.assignment(aud)
        self.assertIn(f"- tasks/{v}/report.md (review report)", a)
        self.assertIn(f"- candidates/{self.c}.md", a)
        self.assertIn("dead-end fragment", a)

    def test_adjudicate_paper_advisor_renew_and_question_gate_defaults(self):
        v = self.task("verifier", "INDIVIDUAL", lane="Q01")
        self.review(self.c, v, "individual", "FAIL", "--blocking", "O2 CRITICAL: Lemma 3 [ALG] - sign error")
        rep = self.cand(self.p, "Q01.R1", "--revises", self.c,
                        text=f"# Draft\n## Theorem\nX.\n## Rebuttals\n{v}.O2: the sign is right.\n")
        adj = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "ADJUDICATE", "--objection", f"{v}.O2").split()[0]
        a = self.assignment(adj)
        self.assertIn("the objection, copied from state: O2 CRITICAL: Lemma 3 [ALG] - sign error", a)
        self.assertIn(f"- candidates/{rep}.md, section '## Rebuttals' ({v}.O2)", a)
        self.assertEqual(self.state()["tasks"][adj]["cands"], [self.c])
        for c in (rep, self.c):
            a2 = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "ADJUDICATE", "--objection", f"{v}.O2",
                         "--cand", c).split()[0]
            self.assertEqual(self.state()["tasks"][a2]["cands"], [self.c])
        self.ri("task", "new", self.R, "--role", "verifier", "--mode", "ADJUDICATE", "--objection", f"{v}.O9", code=2)
        w = self.task("writer")
        m = self.cand(w, None, "--kind", "manuscript")
        a = self.assignment(self.ri("task", "new", self.R, "--role", "verifier", "--mode", "PAPER", "--cand", f"{m},C001").split()[0])
        self.assertLess(a.index("- lanes/Q01/statement.md"), a.index("Phase 2 only"))
        self.assertLess(a.index("Phase 2 only"), a.index("- lanes/Q01/record.md"))
        adv = self.ri("task", "new", self.R, "--role", "process-advisor").split()[0]
        a = self.assignment(adv)
        self.assertIn(f"- tasks/{adv}/status.md (ri.py status output)", a)
        self.assertIn("- lanes/Q01/record.md", a)
        self.assertIn("SUGGESTED NEXT ACTIONS", self.path("tasks", adv, "status.md").read_text(encoding="utf-8"))
        self.write(f"tasks/{self.p}/notes.md", "side observations")
        self.ri("event", self.R, "--type", "stall", "--lane", "Q01", "--note", "Lemma 3 again")
        sk = self.task("skeptic", "CLAIM-GATE")
        self.write(f"tasks/{sk}/result.md", "---\nstatus: completed\n---\n")
        self.ri("task", "set", self.R, sk, "done")
        ren = self.ri("task", "new", self.R, "--role", "investigator", "--mode", "RENEW").split()[0]
        a = self.assignment(ren)
        for needle in ("stall Q01: Lemma 3 again", "- lanes/Q01/record.md", f"- tasks/{self.p}/notes.md (prover {self.p})",
                       "- frontier/model.md", f"- tasks/{sk}/result.md (skeptic CLAIM-GATE)", "- ledger.md"):
            self.assertIn(needle, a)
        self.r1()
        qg = self.ri("task", "new", self.R, "--role", "skeptic", "--mode", "QUESTION-GATE", "--question", "Q01").split()[0]
        a = self.assignment(qg)
        for needle in (f"- tasks/{qg}/card-Q01.md", "- lanes/Q01/statement.md", "- frontier/transfer.md"):
            self.assertIn(needle, a)

    def test_redo_copies_assignment_and_supersedes(self):
        old = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "INDIVIDUAL", "--cand", self.c,
                      "--extra", "Extra focus line.", "--start").split()[0]
        self.ri("task", "set", self.R, old, "unknown")
        self.assertIn(f"{old}: status unknown - worker alive -> wait; else task new --redo {old}", self.status())
        out = self.ri("task", "new", self.R, "--redo", old, "--start")
        new = out.split()[0]
        self.assertIn(f"(supersedes {old})", out)
        st = self.state()["tasks"]
        self.assertEqual((st[old]["status"], st[old]["superseded_by"], st[new]["redo_of"]), ("superseded", new, old))
        self.assertEqual((st[new]["role"], st[new]["mode"], st[new]["lane"], st[new]["round"], st[new]["cands"], st[new]["status"]),
                         ("verifier", "INDIVIDUAL", "Q01", 1, [self.c], "running"))
        self.assertEqual(self.assignment(new), self.assignment(old))
        self.assertIn("Extra focus line.", self.assignment(new))
        out = self.status()
        self.assertNotIn(f"{old}: status unknown", out)
        self.write(f"tasks/{old}/result.md", "---\nstatus: completed\n---\n")
        self.assertIn(f"{old} (superseded by {new}): late result.md - extra evidence: file, do not re-ingest", self.status())
        self.assertIn("extra evidence: file it, do not re-ingest", self.ri("ingest", self.R, old))
        self.assertNotIn("late result.md", self.status())
        self.ri("task", "new", self.R, "--redo", old, code=1)  # already superseded
        self.write(f"tasks/{new}/result.md", "---\nstatus: completed\n---\n")
        self.assertIn("ingest it first", self.ri("task", "new", self.R, "--redo", new, code=1))
        self.assertIn("check OK", self.ri("check", self.R))


class TestCandidatesAndGates(RiCase):
    def setUp(self):
        super().setUp()
        self.init()
        self.q = self.lane()
        self.p = self.task("prover", "PROVE", lane="Q01", ctx="agent-p")
        self.c = self.cand(self.p)
        self.v1 = self.task("verifier", "INDIVIDUAL", lane="Q01", ctx="agent-v1")
        self.v2 = self.task("verifier", "CROSS-DRAFT", lane="Q01", ctx="agent-v2")

    def test_cand_add_freezes_and_hashes(self):
        c = self.state()["candidates"][self.c]
        frozen = self.path("candidates", "C001.md").read_bytes()
        self.assertEqual(frozen, self.path("tasks", self.p, "draft1.md").read_bytes())
        self.assertEqual(c["sha256"], hashlib.sha256(frozen).hexdigest())
        self.assertEqual((c["status"], c["round"], c["author"], c["author_context"], c["claims"], c["kind"]),
                         ("proposed", 1, self.p, "agent-p", "Q01.R1", "proof"))
        self.ri("cand", "add", self.R, "--file", "tasks/T001/draft1.md", "--author", self.p, code=2)  # no claims
        self.ri("cand", "add", self.R, "--file", "tasks/T001/draft1.md", "--author", self.p,
                "--claims", "Q02.R1", "--lane", "Q01", code=2)
        self.ri("cand", "add", self.R, "--file", "tasks/T001/draft1.md", "--author", self.p, "--claims", "Q01.R1",
                "--direction", "PROVE Q02.R1", code=2)
        self.ri("cand", "add", self.R, "--file", "tasks/T001/draft1.md", "--author", self.p, "--claims", "Q01.R1",
                "--direction", "WANDER Q01.R1", code=2)
        c2 = self.cand(self.p, "Q01.R2", "--direction", "repair c1")
        self.assertEqual((self.state()["candidates"][c2]["direction"], self.state()["candidates"][c2]["revises"]),
                         ("REPAIR C001", "C001"))

    def test_stale_review_rejected_after_file_edit(self):
        self.path("candidates", "C001.md").write_text("edited after freeze\n", encoding="utf-8")
        out = self.review(self.c, self.v1, "individual", "PASS", code=1)
        self.assertIn("stale", out)
        self.assertEqual(self.state()["reviews"], [])

    def test_author_and_shared_context_cannot_review(self):
        self.assertIn("must come from a verifier", self.review(self.c, self.p, "individual", "PASS", code=1))
        v_author = self.task("verifier", "INDIVIDUAL", lane="Q01")
        c2 = self.cand(v_author, "Q01.R2")
        self.assertIn("authored", self.review(c2, v_author, "individual", "PASS", code=1))
        same = self.task("verifier", "INDIVIDUAL", lane="Q01", ctx="agent-p")
        self.assertIn("shares context", self.review(self.c, same, "individual", "PASS", code=1))

    def test_one_scope_per_task_and_distinct_gate_tasks(self):
        self.review(self.c, self.v1, "individual", "PASS")
        self.assertIn("at most one scope", self.review(self.c, self.v1, "cross", "PASS", code=1))
        v3 = self.task("verifier", "CROSS-DRAFT", lane="Q01", ctx="agent-v1")
        self.assertIn("different contexts", self.review(self.c, v3, "cross", "PASS", code=1))

    def test_accept_fails_without_cross(self):
        self.review(self.c, self.v1, "individual", "PASS")
        out = self.ri("accept", self.R, self.c, code=1)
        self.assertIn("needs CROSS pass", out)
        self.assertEqual(self.state()["candidates"][self.c]["status"], "proposed")

    def test_accept_passes_with_both_and_logs_top_accepted(self):
        self.review(self.c, self.v1, "individual", "PASS", "--fidelity", "MATCH")
        self.review(self.c, self.v2, "cross", "PASS_WITH_MINOR", "--fidelity", "match",
                    "--blocking", "O1 MINOR: constant should be 2c")
        out = self.ri("accept", self.R, self.c)
        self.assertIn("agent-checked", out)
        self.assertIn(f"next: ri.py ledger add RUN --cand {self.c}", out)
        st = self.state()
        self.assertEqual((st["candidates"][self.c]["status"], st["candidates"][self.c]["label"]),
                         ("accepted", "agent-checked"))
        self.assertEqual([(e["type"], e["lane"]) for e in st["events"]], [("top-accepted", "Q01")])
        self.ri("accept", self.R, self.c, code=1)  # already accepted
        record = self.path("lanes", "Q01", "record.md").read_text(encoding="utf-8")
        self.assertIn("accepted (agent-checked)", record)
        self.ri("ledger", "add", self.R, "--cand", self.c)
        self.assertIn("L001", self.path("ledger.md").read_text(encoding="utf-8"))
        self.assertIn("| accepted (L001) |", self.path("lanes", "Q01", "record.md").read_text(encoding="utf-8"))
        self.ri("ledger", "add", self.R, "--cand", self.c, code=1)

    def test_lower_rung_logs_rung_accepted(self):
        c2 = self.cand(self.p, "Q01.R3")
        self.review(c2, self.v1, "individual", "PASS")
        self.review(c2, self.v2, "cross", "PASS")
        self.ri("accept", self.R, c2)
        ev = self.state()["events"][-1]
        self.assertEqual(ev["type"], "rung-accepted")
        self.assertIn("lane continues on R2", ev["note"])

    def test_open_major_blocks(self):
        self.review(self.c, self.v1, "individual", "PASS")
        self.review(self.c, self.v2, "cross", "INCONCLUSIVE", "--blocking", "O1 MAJOR: Lemma 3: union bound needs a net")
        out = self.ri("accept", self.R, self.c, code=1)
        self.assertIn(f"{self.v2}.O1 MAJOR is open", out)

    def test_passing_verdict_with_major_objection_still_blocks(self):
        self.review(self.c, self.v1, "individual", "PASS", "--blocking", "O2 MAJOR: citation hypotheses unchecked")
        self.review(self.c, self.v2, "cross", "PASS")
        self.assertIn(f"{self.v1}.O2 MAJOR", self.ri("accept", self.R, self.c, code=1))

    def test_adjudication_rejected_objection_unblocks(self):
        self.review(self.c, self.v1, "individual", "PASS")
        self.review(self.c, self.v2, "cross", "FAIL", "--blocking", "O1 CRITICAL: step 4 sign error")
        oid = f"{self.v2}.O1"
        self.ri("accept", self.R, self.c, code=1)
        self.ri("objection", "resolve", self.R, oid, "--how", "rejected", "--by", self.v2, code=1)  # raiser
        wrong = self.task("verifier", "INDIVIDUAL", lane="Q01")
        self.ri("objection", "resolve", self.R, oid, "--how", "rejected", "--by", wrong, code=1)  # not ADJUDICATE
        adj = self.task("verifier", "ADJUDICATE", lane="Q01", ctx="agent-adj")
        self.ri("objection", "resolve", self.R, oid, "--how", "rejected", "--by", adj, "--note", "sign is correct")
        self.assertIn("agent-checked", self.ri("accept", self.R, self.c))
        ob = self.state()["reviews"][1]["objections"][0]
        self.assertEqual((ob["status"], ob["how"], ob["resolved_by"]), ("resolved", "rejected", adj))

    def test_fixed_objection_does_not_unblock_original(self):
        self.review(self.c, self.v1, "individual", "INCONCLUSIVE", "--blocking", "O1 MAJOR: gap in Lemma 2")
        oid = f"{self.v1}.O1"
        self.ri("objection", "resolve", self.R, oid, "--how", "fixed", "--by", self.c, code=1)  # not a revision
        c2 = self.cand(self.p, "Q01.R1", "--revises", self.c)
        self.ri("objection", "resolve", self.R, oid, "--how", "fixed", "--by", c2)
        self.review(self.c, self.v2, "cross", "PASS")
        self.assertIn("is resolved (fixed)", self.ri("accept", self.R, self.c, code=1))

    def test_withdrawn_only_by_original_reviewer(self):
        self.review(self.c, self.v1, "individual", "INCONCLUSIVE", "--blocking", "O1 MAJOR: unclear step")
        oid = f"{self.v1}.O1"
        self.ri("objection", "resolve", self.R, oid, "--how", "withdrawn", "--by", self.v2, code=1)
        self.ri("objection", "resolve", self.R, oid, "--how", "withdrawn", "--by", self.v1)
        self.review(self.c, self.v2, "cross", "PASS")
        self.ri("accept", self.R, self.c)

    def test_fidelity_weaker_blocks_rung(self):
        self.review(self.c, self.v1, "individual", "PASS", "--fidelity", "WEAKER")
        self.review(self.c, self.v2, "cross", "PASS", "--fidelity", "MATCH")
        self.assertIn("fidelity WEAKER", self.ri("accept", self.R, self.c, code=1))

    def test_missing_fidelity_blocks_lane_result(self):
        self.review(self.c, self.v1, "individual", "PASS", fidelity=None)
        self.review(self.c, self.v2, "cross", "PASS")
        self.assertIn("fidelity not reported", self.ri("accept", self.R, self.c, code=1))

    def test_sanity_fail_is_automatic_critical(self):
        scout = self.task("scout", "SANITY", lane="Q01")
        self.review(self.c, scout, "sanity", "FAIL")
        self.review(self.c, self.v1, "individual", "PASS")
        self.review(self.c, self.v2, "cross", "PASS")
        self.assertIn(f"{scout}.O1 CRITICAL", self.ri("accept", self.R, self.c, code=1))

    def test_gap_draft_needs_salvage_and_is_never_accepted(self):
        c2 = self.cand(self.p, "Q01.R2", "--gap", "Lemma 4 unproved")
        self.ri("task", "set", self.R, self.p, "done")
        self.assertIn(f"{c2}: needs SALVAGE review", self.status())
        sal = self.task("verifier", "SALVAGE", lane="Q01")
        self.review(c2, sal, "individual", "INCONCLUSIVE", "--confirmed", "Lemma 1; Lemma 2", fidelity=None)
        self.review(c2, self.v2, "cross", "PASS")
        self.assertIn("gap declared", self.ri("accept", self.R, c2, code=1))
        self.assertNotIn(f"{c2}: needs SALVAGE", self.status())

    def test_salvage_review_never_counts_as_individual_pass(self):
        sal = self.task("verifier", "INDIVIDUAL", lane="Q01")
        self.review(self.c, sal, "individual", "PASS", "--note", "salvage")
        self.review(self.c, self.v2, "cross", "PASS")
        self.assertIn("needs INDIVIDUAL pass", self.ri("accept", self.R, self.c, code=1))

    def test_deps_must_be_active_ledger_entries(self):
        self.assertIn("L009", self.ri("cand", "add", self.R, "--file", "tasks/T001/draft1.md", "--author", self.p,
                                       "--claims", "Q01.R2", "--deps", "L009", code=1))
        c2 = self.cand(self.p, "Q01.R2", "--deps", "L9", "--allow-pending-deps")
        self.review(c2, self.v1, "individual", "PASS")
        self.review(c2, self.v2, "cross", "PASS")
        self.assertIn("dependency L009 is not a ledger entry", self.ri("accept", self.R, c2, code=1))

    def test_joint_cross_review_covers_several_candidates(self):
        p2 = self.task("prover", "PROVE", lane="Q01")
        c2 = self.cand(p2, "Q01.R2")
        self.review(self.c, self.v2, "cross", "PASS")
        self.review(c2, self.v2, "cross", "FAIL", "--blocking", "O1 CRITICAL: false for n=2")
        self.review(self.c, self.v1, "individual", "PASS")
        self.ri("accept", self.R, self.c)
        self.ri("accept", self.R, c2, code=1)

    def test_inconclusive_without_objections_stays_blocking(self):
        self.review(self.c, self.v1, "individual", "INCONCLUSIVE", "--note", "Lemma 5 unchecked")
        self.review(self.c, self.v2, "cross", "PASS")
        self.assertIn(f"individual review by {self.v1}: INCONCLUSIVE", self.ri("accept", self.R, self.c, code=1))

    def test_objection_id_collision_across_candidates_refused(self):
        p2 = self.task("prover", "PROVE", lane="Q01")
        c2 = self.cand(p2, "Q01.R2")
        self.review(self.c, self.v2, "cross", "INCONCLUSIVE", "--blocking", "[O1 MAJOR, O2 MINOR]")
        out = self.review(c2, self.v2, "cross", "FAIL", "--blocking", "O1 CRITICAL: Claim 2 [QUANT] - order", code=1)
        self.assertIn(f"{self.v2}.O1 is already used by {self.v2} on {self.c}", out)
        self.review(c2, self.v2, "cross", "FAIL", "--blocking", "O3 CRITICAL: Claim 2 [QUANT] - order")
        objs = [o for r in self.state()["reviews"] for o in r["objections"]]
        self.assertEqual([(o["id"], o["severity"], o["text"]) for o in objs],
                         [(f"{self.v2}.O1", "MAJOR", "(see report)"), (f"{self.v2}.O2", "MINOR", "(see report)"),
                          (f"{self.v2}.O3", "CRITICAL", "Claim 2 [QUANT] - order")])
        self.review(self.c, self.v1, "individual", "PASS", "--blocking", "O1 CRITICAL; O1 MAJOR", code=2)
        self.review(self.c, self.v1, "individual", "PASS", "--blocking", "looks wrong", code=2)
        self.assertIn("check OK", self.ri("check", self.R))

    def test_legacy_ambiguous_objection_needs_cand_and_check_reports_it(self):
        p2 = self.task("prover", "PROVE", lane="Q01")
        c2 = self.cand(p2, "Q01.R2")
        self.review(self.c, self.v2, "cross", "INCONCLUSIVE", "--blocking", "O1 MAJOR: a")
        self.review(c2, self.v2, "cross", "INCONCLUSIVE", "--blocking", "O2 MAJOR: b")
        st = self.state()
        st["reviews"][1]["objections"][0]["id"] = f"{self.v2}.O1"  # legacy data: reused number
        self.save(st)
        self.assertIn(f"objection {self.v2}.O1 is used on several candidates", self.ri("check", self.R, code=1))
        out = self.ri("objection", "resolve", self.R, f"{self.v2}.O1", "--how", "withdrawn", "--by", self.v2, code=2)
        self.assertIn("ambiguous", out)
        self.ri("objection", "resolve", self.R, f"{self.v2}.O1", "--how", "withdrawn", "--by", self.v2, "--cand", c2)
        self.assertEqual([o["status"] for r in self.state()["reviews"] for o in r["objections"]], ["open", "resolved"])

    def test_blocking_grammar_uppercase_only_and_brackets_kept(self):
        obs = ri.parse_blocking("T009", "O1 CRITICAL: Lemma 3 [PROB] - union bound over [n] fails for o2 major instances")
        self.assertEqual([(o["id"], o["severity"], o["text"]) for o in obs],
                         [("T009.O1", "CRITICAL", "Lemma 3 [PROB] - union bound over [n] fails for o2 major instances")])
        obs = ri.parse_blocking("T009", "O1 CRITICAL: a [ALG] - x; O2 MAJOR: b [CONST] - y]")
        self.assertEqual([o["text"] for o in obs], ["a [ALG] - x", "b [CONST] - y]"])
        self.assertEqual(ri.parse_blocking("T009", "none"), [])
        with self.assertRaises(ri.RiError):
            ri.parse_blocking("T009", "o1 critical: lowercase is not an objection")

    def test_assumes_union_and_display(self):
        self.review(self.c, self.v1, "individual", "PASS", "--assumes", "n even")
        self.review(self.c, self.v2, "cross", "PASS", "--assumes", "none")
        out = self.ri("accept", self.R, self.c)
        self.assertIn("(assumes: n even)", out)
        self.assertIn("HYPOTHESIS-AUDIT", out)
        st = self.state()
        self.assertEqual(st["candidates"][self.c]["assumes"], ["n even"])
        self.assertIn("assumes: n even", st["events"][-1]["note"])
        self.assertIn("(agent-checked; assumes: n even)", self.path("lanes", "Q01", "record.md").read_text(encoding="utf-8"))
        self.ri("ledger", "add", self.R, "--cand", self.c)
        self.assertTrue(self.state()["ledger"]["L001"]["statement"].endswith("(assumes: n even)"))
        self.assertIn("(assumes: n even)", self.path("ledger.md").read_text(encoding="utf-8"))
        self.assertIn("best accepted R1 (assumes: n even)", self.status())

    def test_transfer_candidate_free_claim_isolated_gate(self):
        lit = self.task("literature-reviewer", "TRANSFER-AUDIT")
        self.write(f"tasks/{lit}/transfer-M1.md", "# Transfer\n## Statement\nS03 Thm 2 survives in M1 by padding.\n")
        out = self.ri("cand", "add", self.R, "--kind", "transfer", "--claims", "transfer:S03 Thm 2@M1",
                      "--file", f"tasks/{lit}/transfer-M1.md", "--author", lit)
        t = out.split()[0]
        c = self.state()["candidates"][t]
        self.assertEqual((c["kind"], c["claims"], c["lane"]), ("transfer", "transfer:S03 Thm 2@M1", None))
        self.ri("accept", self.R, t, code=1)
        iso = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "ISOLATED", "--cand", t).split()[0]
        self.assertIn("transfer verdict", self.assignment(iso))
        self.review(t, iso, "isolated", "PASS")
        self.ri("accept", self.R, t)
        self.assertIn("transfer", self.ri("ledger", "add", self.R, "--cand", t))
        self.assertEqual(self.state()["ledger"]["L001"]["statement"], "S03 Thm 2 survives in M1 by padding.")
        self.ri("cand", "add", self.R, "--kind", "transfer", "--file", f"tasks/{lit}/transfer-M1.md", "--author", lit, code=2)

    def test_quarantine_candidate_root(self):
        self.review(self.c, self.v1, "individual", "PASS")
        self.review(self.c, self.v2, "cross", "PASS")
        self.ri("accept", self.R, self.c)
        self.ri("quarantine", self.R, self.c, "--code", "objection", "--reason", "late counterexample to Lemma 2")
        self.assertEqual(self.state()["candidates"][self.c]["status"], "quarantined")
        self.ri("ledger", "add", self.R, "--cand", self.c, code=1)
        self.ri("quarantine", self.R, "Q01", "--code", "objection", "--reason", "x", code=2)
        self.ri("quarantine", self.R, self.c, "--code", "objection", code=2)  # no reason


class TestExclusions(RiCase):
    def setUp(self):
        super().setUp()
        self.init()
        self.q = self.lane()

    def test_isolated_fragment_rules(self):
        v_src = self.task("verifier", "INDIVIDUAL", lane="Q01", ctx="agent-src")
        src = self.cand(v_src, "Q01.R1")  # artificial: a verifier-authored source draft
        auditor = self.task("ledger-auditor", lane="Q01", ctx="agent-aud")
        frag = self.cand(auditor, None, "--from", src, text="# Lemma 2 (fragment)\nFor all n >= 1 ...\n")
        c = self.state()["candidates"][frag]
        self.assertEqual((c["kind"], c["from"], c["lane"]), ("lemma", src, "Q01"))
        self.assertIn("authored", self.review(frag, v_src, "isolated", "PASS", code=1))
        shared = self.task("verifier", "ISOLATED", ctx="agent-src")
        self.assertIn("shares context", self.review(frag, shared, "isolated", "PASS", code=1))
        self.assertIn("must come from", self.review(frag, auditor, "isolated", "PASS", code=1))
        iso = self.task("verifier", "ISOLATED", ctx="agent-iso")
        self.review(frag, iso, "isolated", "PASS")
        self.ri("accept", self.R, frag)
        self.assertIn("L001 <- " + frag, self.ri("ledger", "add", self.R, "--cand", frag))
        entry = self.state()["ledger"]["L001"]
        self.assertEqual((entry["kind"], entry["model"], entry["statement"]), ("lemma", "M1", "Lemma 2 (fragment)"))
        self.ri("cand", "add", self.R, "--file", f"tasks/{auditor}/draft2.md", "--author", auditor,
                "--kind", "counterexample", "--from", src, "--claims", "Q01.R1", code=2)  # dead ends are lemmas

    def test_counterexample_in_cohort_needs_witness_and_cross(self):
        p = self.task("prover", "DISPROVE", lane="Q01")
        ce = self.cand(p, "Q01.R1", "--kind", "counterexample")
        self.ri("exclude", self.R, "--claim", "Q01.R1", "--cand", ce, code=1)  # not accepted yet
        self.review(ce, self.task("verifier", "INDIVIDUAL", lane="Q01"), "individual", "PASS", "--fidelity", "MATCH")
        self.review(ce, self.task("scout", "WITNESS", lane="Q01"), "witness", "PASS")
        self.assertIn("needs CROSS pass", self.ri("accept", self.R, ce, code=1))
        self.review(ce, self.task("verifier", "CROSS-DRAFT", lane="Q01"), "cross", "PASS")
        out = self.ri("accept", self.R, ce)
        self.assertIn(f"next: ri.py exclude RUN --claim Q01.R1 --cand {ce}", out)
        self.assertEqual(self.state()["events"], [])  # a counterexample is not a rung acceptance
        self.assertIn(f"{ce}: accepted counterexample - exclude --claim Q01.R1", self.status())
        out = self.ri("exclude", self.R, "--claim", "Q01.R1", "--cand", ce)
        self.assertIn("refuted", out)
        st = self.state()
        self.assertEqual((st["events"][-1]["type"], st["events"][-1]["lane"]), ("refuted", "Q01"))
        self.assertEqual((st["ledger"]["L001"]["excludes"], st["ledger"]["L001"]["covers"]), ("Q01.R1", ["Q01.R1"]))
        self.assertIn("Exclusions (refuted rungs)", self.path("ledger.md").read_text(encoding="utf-8"))
        self.ri("exclude", self.R, "--claim", "Q01.R1", "--cand", ce, code=1)  # duplicate
        self.assertIn("refuted", self.status())
        self.assertIn("check OK", self.ri("check", self.R))

    def test_counterexample_cannot_claim_d(self):
        p = self.task("prover", "DISPROVE", lane="Q01")
        out = self.ri("cand", "add", self.R, "--file", self.write(f"tasks/{p}/d.md", "x"), "--author", p,
                      "--claims", "Q01.D", "--kind", "counterexample", code=2)
        self.assertIn("never Qxx.D", out)

    def test_witness_fail_blocks_and_proof_cannot_exclude(self):
        p = self.task("prover", "DISPROVE", lane="Q01")
        ce = self.cand(p, "Q01.R2", "--kind", "counterexample")
        self.review(ce, self.task("verifier", "INDIVIDUAL", lane="Q01"), "individual", "PASS")
        self.review(ce, self.task("scout", "WITNESS", lane="Q01"), "witness", "FAIL")
        self.review(ce, self.task("verifier", "CROSS-DRAFT", lane="Q01"), "cross", "PASS")
        self.ri("accept", self.R, ce, code=1)
        proof = self.accepted("Q01.R3")
        self.assertIn("exclude needs an accepted counterexample",
                      self.ri("exclude", self.R, "--claim", "Q01.R3", "--cand", proof, code=1))

    def test_exclude_validation_rules(self):
        q2 = self.lane("Second question")
        ce = self.accepted_ce("Q01.R2")
        self.assertIn("not in the lane", self.ri("exclude", self.R, "--claim", f"{q2}.R1", "--cand", ce, code=1))
        self.assertIn("excludes exactly", self.ri("exclude", self.R, "--claim", "Q01.R3", "--cand", ce, code=1))
        self.assertIn("excludes exactly", self.ri("exclude", self.R, "--claim", "Q01.R1", "--cand", ce, code=1))
        self.assertIn("never excluded", self.ri("exclude", self.R, "--claim", "Q01.D", "--cand", ce, code=1))
        out = self.ri("exclude", self.R, "--claim", "Q01.R2", "--cand", ce)
        self.assertIn("L001 excludes Q01.R1..R2", out)
        self.assertIn("weaker rungs after R2 stay open", out)
        st = self.state()
        self.assertEqual(st["ledger"]["L001"]["covers"], ["Q01.R1", "Q01.R2"])
        self.assertEqual([e["type"] for e in st["events"]], ["refuted"])
        self.assertIn("ladder nesting", st["events"][-1]["note"])
        self.assertIn("| L001 | Q01.R1..R2 |", self.path("ledger.md").read_text(encoding="utf-8"))
        self.assertIn("Exclusions: Q01.R1..R2 by L001", self.path("lanes", "Q01", "record.md").read_text(encoding="utf-8"))
        ce3 = self.accepted_ce("Q01.R3")
        self.assertIn("refuted already logged (E1)", self.ri("exclude", self.R, "--claim", "Q01.R3", "--cand", ce3))
        self.assertEqual(len([e for e in self.state()["events"] if e["type"] == "refuted"]), 1)
        self.assertIn("check OK", self.ri("check", self.R))
        st = self.state()
        st["ledger"]["L001"]["excludes"], st["ledger"]["L001"]["covers"] = "Q01.R4", None  # forged, invalid
        self.save(st)
        self.assertIn("L001: invalid exclusion", self.ri("check", self.R, code=1))

    def test_d_proof_excludes_the_rung_d_refutes(self):
        p = self.task("prover", "DISPROVE", lane="Q01")
        d = self.cand(p, "Q01.D", "--kind", "impossibility")
        self.review(d, self.task("verifier", "INDIVIDUAL", lane="Q01"), "individual", "PASS")
        self.review(d, self.task("verifier", "CROSS-DRAFT", lane="Q01"), "cross", "PASS")
        out = self.ri("accept", self.R, d)
        self.assertIn(f"next: ri.py exclude RUN --claim Q01.R1 --cand {d}", out)
        self.assertEqual(self.state()["events"], [])  # refuted comes from exclude
        self.ri("ledger", "add", self.R, "--cand", d)
        self.assertIn(f"{d}: accepted proof of Q01.D without an exclusion - exclude --claim Q01.R1", self.status())
        stmt = self.path("lanes", "Q01", "statement.md")
        stmt.write_text(stmt.read_text(encoding="utf-8").replace("D refutes: <R1 | Rj>", "D refutes: R2"), encoding="utf-8")
        self.assertIn("rung D refutes (Q01.R2", self.ri("exclude", self.R, "--claim", "Q01.R1", "--cand", d, code=1))
        self.assertIn("Q01.R1..R2", self.ri("exclude", self.R, "--claim", "Q01.R2", "--cand", d))
        self.assertNotIn("without an exclusion", self.status())
        self.assertEqual(self.state()["events"][-1]["type"], "refuted")

    def test_accept_refuses_contradiction_with_exclusion(self):
        ce = self.accepted_ce("Q01.R2")
        self.ri("exclude", self.R, "--claim", "Q01.R2", "--cand", ce)
        p = self.task("prover", "PROVE", lane="Q01")
        c = self.cand(p, "Q01.R2")
        self.review(c, self.task("verifier", "INDIVIDUAL", lane="Q01"), "individual", "PASS")
        self.review(c, self.task("verifier", "CROSS-DRAFT", lane="Q01"), "cross", "PASS")
        out = self.ri("accept", self.R, c, code=1)
        self.assertIn("contradiction: Q01.R2 is excluded by L001", out)
        self.assertIn("TARGETED review", out)
        self.accepted("Q01.R3")  # a weaker rung stays open
        st = self.state()
        st["candidates"][c]["status"] = "accepted"  # forged, as from a legacy run
        self.save(st)
        self.assertIn(f"Q01.R2 accepted ({c}) and excluded (L001)", self.ri("check", self.R, code=1))
        self.assertIn(f"Q01.R2 accepted ({c}) and excluded (L001): contradiction - quarantine both", self.status())

    def test_exclude_refuses_contradiction_with_accepted_rung(self):
        good = self.accepted("Q01.R2")
        p = self.task("prover", "DISPROVE", lane="Q01")
        ce = self.cand(p, "Q01.R3", "--kind", "counterexample")
        self.review(ce, self.task("verifier", "INDIVIDUAL", lane="Q01"), "individual", "PASS")
        self.review(ce, self.task("scout", "WITNESS", lane="Q01"), "witness", "PASS")
        self.review(ce, self.task("verifier", "CROSS-DRAFT", lane="Q01"), "cross", "PASS")
        out = self.ri("accept", self.R, ce, code=1)  # D3: refuting R3 refutes the accepted R2
        self.assertIn(f"contradiction: Q01.R2 is accepted ({good}) and {ce} refutes it", out)
        self.assertIn("SECOND-INDEPENDENT", out)
        self.assertIn(f"{ce}: passes its gates but Q01.R2 is accepted ({good})", self.status())
        self.assertNotIn(f"{ce}: gates satisfied", self.status())
        self.assertIn(f"{ce} (Q01.R3) passes its gates but", self.ri("check", self.R, code=1))
        st = self.state()
        st["candidates"][ce]["status"] = "accepted"  # forged, as from a legacy run
        self.save(st)
        out = self.ri("exclude", self.R, "--claim", "Q01.R3", "--cand", ce, code=1)
        self.assertIn(f"contradiction: Q01.R2 is accepted ({good})", out)
        self.assertIn(f"Q01.R2 accepted ({good}) and refuted by accepted {ce} (exclusion pending)",
                      self.ri("check", self.R, code=1))
        out = self.status()
        self.assertIn(f"Q01.R2 accepted ({good}) and refuted by accepted {ce} (exclusion pending): contradiction", out)
        self.assertNotIn(f"{ce}: accepted counterexample - exclude", out)
        self.assertIn("Q01: contradiction pending", out)

    def test_proof_and_counterexample_of_one_rung_never_both_accepted(self):
        p1, p2 = self.task("prover", "PROVE", lane="Q01"), self.task("prover", "DISPROVE", lane="Q01")
        pr = self.cand(p1, "Q01.R1")
        ce = self.cand(p2, "Q01.R1", "--kind", "counterexample")
        for c in (pr, ce):
            self.review(c, self.task("verifier", "INDIVIDUAL", lane="Q01"), "individual", "PASS")
        self.review(ce, self.task("scout", "WITNESS", lane="Q01"), "witness", "PASS")
        cross = self.task("verifier", "CROSS-DRAFT", lane="Q01", ctx="agent-cross")
        self.result(cross, "scope: CROSS-DRAFT", f"review {pr}: verdict=PASS; fidelity=MATCH",
                    f"review {ce}: verdict=PASS; fidelity=MATCH")
        out = self.ri("ingest", self.R, cross, "--accept")  # one pass would accept both without D3
        self.assertIn(f"accepted: {pr} accepted", out)
        self.assertIn(f"{ce}: contradiction: Q01.R1 is accepted ({pr}) and {ce} refutes it", out)
        st = self.state()
        self.assertEqual((st["candidates"][pr]["status"], st["candidates"][ce]["status"]), ("accepted", "proposed"))
        self.assertIn(f"{ce} (Q01.R1) passes its gates but", self.ri("check", self.R, code=1))
        self.assertNotIn("q set Q01 --status resolved", self.status())
        # the other order: an accepted proof of D (exclusion not yet recorded) blocks a later proof of R1
        q2 = self.lane("Second")
        pd = self.task("prover", "DISPROVE", lane=q2)
        d = self.cand(pd, f"{q2}.D", "--kind", "impossibility")
        self.review(d, self.task("verifier", "INDIVIDUAL", lane=q2), "individual", "PASS")
        self.review(d, self.task("verifier", "CROSS-DRAFT", lane=q2), "cross", "PASS")
        self.ri("accept", self.R, d)
        pp = self.task("prover", "PROVE", lane=q2)
        r1 = self.cand(pp, f"{q2}.R1")
        self.review(r1, self.task("verifier", "INDIVIDUAL", lane=q2), "individual", "PASS")
        self.review(r1, self.task("verifier", "CROSS-DRAFT", lane=q2), "cross", "PASS")
        out = self.ri("accept", self.R, r1, code=1)
        self.assertIn(f"contradiction: {q2}.R1 is refuted by accepted {d} (exclusion not yet recorded)", out)

    def test_quarantine_is_transitive(self):
        c1 = self.accepted("Q01.R3")
        self.ri("ledger", "add", self.R, "--cand", c1)
        c2 = self.accepted("Q01.R2", "--deps", "L001")
        self.ri("ledger", "add", self.R, "--cand", c2)
        c3 = self.accepted("Q01.R1", "--deps", "L002")
        out = self.ri("quarantine", self.R, "L001", "--code", "objection", "--reason", "Lemma 1 misapplied")
        st = self.state()
        self.assertEqual({k: e["status"] for k, e in st["ledger"].items()},
                         {"L001": "quarantined", "L002": "quarantined"})
        for c in (c1, c2, c3):
            self.assertEqual(st["candidates"][c]["status"], "quarantined", c)
        self.assertEqual(st["events"][-1]["type"], "model-change")
        self.assertIn("quarantined", out)
        self.assertIn("## Quarantined", self.path("ledger.md").read_text(encoding="utf-8"))
        self.assertIn("already quarantined", self.ri("quarantine", self.R, "L002", "--code", "objection", "--reason", "again"))
        p = self.task("prover", "PROVE", lane="Q01")
        self.ri("cand", "add", self.R, "--file", "candidates/C001.md", "--author", p, "--claims", "Q01.R1",
                "--deps", "L002", code=1)
        self.ri("check", self.R)
        self.assertIn("QUARANTINED", self.status())


class TestRecordAndLedger(RiCase):
    def setUp(self):
        super().setUp()
        self.init()
        self.q = self.lane()

    def test_record_groups_by_direction_target(self):
        p1 = self.task("prover", "PROVE", lane="Q01")
        p2 = self.task("prover", "DISPROVE", lane="Q01")
        p3 = self.task("prover", "PROVE", lane="Q01")
        a = self.cand(p1, "Q01.R2", "--method", "potential function", "--direction", "PROVE Q01.R1",
                      text="# Draft\n## Theorem\nR2 holds.\n\n## Obstacle to the assigned target\nLemma 4 loses a factor 2 at k = 1.\n")
        b = self.cand(p2, "Q01.R1", "--kind", "counterexample", "--method", "adversary family", "--direction", "DISPROVE Q01.D")
        c = self.cand(p3, "Q01.R2", "--method", "LP duality")  # legacy: no direction
        v = self.task("verifier", "INDIVIDUAL", lane="Q01")
        self.review(a, v, "individual", "FAIL", "--blocking", "O1 CRITICAL: Lemma 3: inequality reversed",
                    "--confirmed", "Lemma 1; Lemma 2", "--report", f"tasks/{p1}/draft1.md")
        record = self.path("lanes", "Q01", "record.md").read_text(encoding="utf-8")
        i1, i2, i_d = (record.index(f"## Target Q01.{r}") for r in ("R1", "R2", "D"))
        self.assertLess(i1, i2)
        self.assertLess(i2, i_d)
        self.assertIn("| Cand | Rd | Prover | Claimed | Method | Outcome | Failing step | Decisive objection(s) |", record)
        row_a = next(x for x in record.splitlines() if x.startswith(f"| {a} "))
        self.assertIn(f"| {a} | 1 | {p1} | Q01.R2 | potential function | failed | obstacle: Lemma 4 loses a factor 2 at k = 1. |", row_a)
        self.assertLess(record.index(f"| {a} "), i2)  # filed under its target R1, not its claim R2
        self.assertGreater(record.index(f"| {b} "), i_d)
        self.assertIn("Q01.R1 (counterexample)", record)
        self.assertGreater(record.index(f"| {c} "), i2)
        self.assertIn(f"{v}.O1 CRITICAL", record)
        self.assertIn(f"- {a} Lemma 1 ({v})", record)
        self.ri("record", self.R, "Q01")

    def test_record_accepted_line_fragments_and_confirmed_links(self):
        p = self.task("prover", "PROVE", lane="Q01")
        src = self.cand(p, "Q01.R1", "--direction", "PROVE Q01.R1")
        v = self.task("verifier", "INDIVIDUAL", lane="Q01")
        self.review(src, v, "individual", "FAIL", "--blocking", "O1 CRITICAL: Claim 5 [ALG] - false at n = 3",
                    "--confirmed", "Lemma 2")
        aud = self.task("ledger-auditor", lane="Q01")
        frag = self.cand(aud, "Q01.R1", "--from", src, "--step", "Lemma 2",
                         text="# Fragment frag-1\n## Statement\nFor all n >= 2, f(n) <= 2n.\n## Proof\n...\n")
        dead = self.cand(aud, None, "--from", src, "--step", "Claim 5",
                         text="# Fragment frag-2\n## Statement\nDead end: Claim 5 fails: n = 3 gives 7 > 6.\n")
        for f in (frag, dead):
            self.review(f, self.task("verifier", "ISOLATED"), "isolated", "PASS")
            self.ri("accept", self.R, f)
            self.ri("ledger", "add", self.R, "--cand", f)
        ok = self.accepted("Q01.R3")
        record = self.path("lanes", "Q01", "record.md").read_text(encoding="utf-8")
        accepted = next(x for x in record.splitlines() if x.startswith("Accepted:"))
        self.assertEqual(accepted, f"Accepted: Q01.R3 by {ok} (agent-checked)")
        frags = record.split("## Ledger fragments\n")[1].split("## Confirmed steps")[0]
        self.assertIn(f"- L001 lemma ({frag}, from {src} Lemma 2): accepted (L001) | For all n >= 2, f(n) <= 2n.", frags)
        self.assertIn(f"- L002 dead end ({dead}, from {src} Claim 5)", frags)
        self.assertIn(f"- {src} Lemma 2 ({v}) -> {frag} -> L001", record)
        self.assertNotIn(f"| {frag} ", record)  # fragments are not attempts

    def test_record_parses_canonical_objection_form(self):
        p = self.task("prover", "PROVE", lane="Q01")
        a = self.cand(p, "Q01.R1", "--method", "primal-dual")
        v = self.task("verifier", "INDIVIDUAL", lane="Q01")
        self.review(a, v, "individual", "INCONCLUSIVE",
                    "--blocking", "O1 MAJOR: Claim 4.2 [CONST] - constant depends on n")
        record = self.path("lanes", "Q01", "record.md").read_text(encoding="utf-8")
        self.assertIn("| inconclusive | Claim 4.2 |", record)
        self.assertIn(f"{v}.O1 MAJOR [CONST] Claim 4.2 constant depends on n (no report)", record)

    def test_split_objection_forms(self):
        self.assertEqual(ri.split_objection("Lemma 3 [PROB] - union bound"), ("Lemma 3", "PROB", "union bound"))
        self.assertEqual(ri.split_objection("Lemma 3: inequality reversed"), ("Lemma 3", "", "inequality reversed"))
        self.assertEqual(ri.split_objection("eq. (7) - sign error"), ("eq. (7)", "", "sign error"))
        self.assertEqual(ri.split_objection("no location given"), ("", "", "no location given"))

    def test_ledger_default_statement_from_theorem_section(self):
        c = self.accepted("Q01.R2")
        self.ri("ledger", "add", self.R, "--cand", c)
        self.assertEqual(self.state()["ledger"]["L001"]["statement"], f"Theorem {self.n}")  # no section: first line
        p = self.task("prover", "PROVE", lane="Q01")
        c2 = self.cand(p, "Q01.R1", text="# Draft: Q01.R1 (PROVE Q01.R1)\nModel: M1.\n\n## Theorem\nFor every n >= 2\n"
                                         "the ratio is at least c.\nRung: Q01.R1\nDepends on: none\n\n## Lemma 1\nx\n")
        self.review(c2, self.task("verifier", "INDIVIDUAL", lane="Q01"), "individual", "PASS")
        self.review(c2, self.task("verifier", "CROSS-DRAFT", lane="Q01"), "cross", "PASS")
        self.ri("accept", self.R, c2)
        self.ri("ledger", "add", self.R, "--cand", c2)
        self.assertEqual(self.state()["ledger"]["L002"]["statement"], "For every n >= 2 the ratio is at least c.")
        self.ri("ledger", "add", self.R, "--cand", c2, code=1)


class TestIngest(RiCase):
    def setUp(self):
        super().setUp()
        self.init()
        self.q = self.lane()

    def prover_done(self, claims="Q01.R2", direction="PROVE Q01.R1", kind="proof", extra=(), theorem="R2 holds for all n.",
                    gaps="none"):
        p = self.ri("task", "new", self.R, "--role", "prover", "--direction", direction, "--start").split()[0]
        self.write(f"tasks/{p}/draft.md", f"# Draft\n## Theorem\n{theorem}\nRung: {claims}\n\n"
                                          "## Obstacle to the assigned target\nStep 4 fails.\n")
        self.write(f"tasks/{p}/notes.md", "side observations")
        self.result(p, f"direction: {direction}", f"claims: {claims}", f"kind: {kind}", "method: potential function",
                    f"gaps: {gaps}", "depends_on: []", "rebuttals: none", "side_observations: none", *extra)
        return p

    def test_ingest_prover_result(self):
        p = self.prover_done()
        out = self.ri("ingest", self.R, p)
        self.assertIn(f"{p} prover: done - test result", out)
        self.assertIn("C001 frozen  Q01.R2 (proof)  direction PROVE Q01.R1", out)
        st = self.state()
        c = st["candidates"]["C001"]
        self.assertEqual((c["claims"], c["direction"], c["method"], c["gap"], c["author"], c["round"]),
                         ("Q01.R2", "PROVE Q01.R1", "potential function", None, p, 1))
        self.assertEqual((st["tasks"][p]["status"], st["tasks"][p]["notes"]), ("done", f"tasks/{p}/notes.md"))
        self.assertIn("## Target Q01.R1", self.path("lanes", "Q01", "record.md").read_text(encoding="utf-8"))
        out = self.ri("ingest", self.R, p)
        self.assertIn("already ingested", out)
        self.assertEqual(len(self.state()["candidates"]), 1)

    def test_ingest_prover_claims_none_and_repair_rebuttals(self):
        p = self.prover_done(claims="none", gaps="Lemma 4 unproved")
        self.ri("ingest", self.R, p)
        c = self.state()["candidates"]["C001"]
        self.assertEqual((c["claims"], c["gap"]), ("Q01.R1", "Lemma 4 unproved"))
        v = self.task("verifier", "SALVAGE", lane="Q01")
        self.review("C001", v, "individual", "INCONCLUSIVE", "--blocking", "O2 MAJOR: Lemma 3 [ALG] - x", fidelity=None)
        r = self.ri("task", "new", self.R, "--role", "prover", "--direction", "REPAIR C001", "--start").split()[0]
        self.write(f"tasks/{r}/draft.md", f"# Draft\n## Theorem\nX.\n## Rebuttals\n{v}.O2: fine.\n")
        self.result(r, "direction: REPAIR C001", "claims: Q01.R1", "kind: proof", "method: fix", "gaps: none",
                    f"depends_on: [L009]", f"rebuttals: [{v}.O2]")
        out = self.ri("ingest", self.R, r)
        self.assertIn(f"dispatch ADJUDICATE for {v}.O2", out)
        self.assertIn("pending deps L009", out)
        c2 = self.state()["candidates"]["C002"]
        self.assertEqual((c2["revises"], c2["direction"], c2["rebuttals"], c2["deps"]),
                         ("C001", "REPAIR C001", [f"{v}.O2"], ["L009"]))

    def test_ingest_verifier_line_format(self):
        p1, p2 = self.prover_done(), self.prover_done(claims="Q01.R1")
        self.ri("ingest", self.R, p1, p2)
        x = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "CROSS-DRAFT", "--cand", "C001,C002", "--start").split()[0]
        self.write(f"tasks/{x}/report.md", "full report")
        self.result(x, "scope: CROSS-DRAFT",
                    "review C001: verdict=PASS; fidelity=MATCH; assumes=n even; k known",
                    "confirmed C001: Lemma 2; Claim 3.1",
                    "too_easy C001: none",
                    "review C002: verdict=FAIL; fidelity=MATCH; assumes=none",
                    "blocking C002: O1 CRITICAL: Lemma 3 [PROB] - union bound over [n] for an infinite family",
                    "blocking C002: O3 MAJOR: Claim 4.2 [CONST] - constant depends on n",
                    "confirmed C002: Lemma 1",
                    "too_easy C002: c-inf",
                    "ranking: C001 complete; C002 strategy-broken",
                    "shared_failing_step: C001 Lemma 3 ~ C002 Lemma 3")
        out = self.ri("ingest", self.R, x)
        self.assertIn("review recorded: C001 cross PASS fidelity MATCH (assumes: n even; k known)", out)
        self.assertIn(f"C002 cross FAIL fidelity MATCH by {x}; objections {x}.O1 CRITICAL, {x}.O3 MAJOR", out)
        self.assertIn("too_easy C002: c-inf -> event --type too-easy --lane Q01", out)
        self.assertIn("shared_failing_step: C001 Lemma 3 ~ C002 Lemma 3 -> event --type stall --lane Q01", out)
        revs = self.state()["reviews"]
        self.assertEqual([(r["cand"], r["scope"], r["verdict"], r["fidelity"], r["assumes"], r["report"]) for r in revs],
                         [("C001", "cross", "PASS", "MATCH", "n even; k known", f"tasks/{x}/report.md"),
                          ("C002", "cross", "FAIL", "MATCH", None, f"tasks/{x}/report.md")])
        self.assertEqual(revs[0]["confirmed"], ["Lemma 2", "Claim 3.1"])
        self.assertEqual(revs[1]["objections"][0]["text"], "Lemma 3 [PROB] - union bound over [n] for an infinite family")
        st = self.state()
        self.assertEqual(st["tasks"][x]["ranking"], "C001 complete; C002 strategy-broken")
        self.assertEqual(st["events"], [])  # ingest suggests events; the orchestrator logs them
        out = self.status()
        self.assertIn(f"Q01: {x} reports a shared failing step", out)
        self.assertIn("C002: too_easy c-inf reported by", out)
        self.ri("event", self.R, "--type", "stall", "--lane", "Q01", "--note", "shared failing step")
        self.ri("event", self.R, "--type", "too-easy", "--lane", "Q01", "--note", f"C002: c-inf ({x})")
        out = self.status()
        self.assertNotIn("reports a shared failing step", out)
        self.assertNotIn("too_easy c-inf reported", out)

    def test_ingest_accept_records_and_ledgers(self):
        p = self.prover_done()
        self.ri("ingest", self.R, p)
        i = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "INDIVIDUAL", "--cand", "C001", "--start").split()[0]
        s = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "SECOND-INDEPENDENT", "--cand", "C001", "--start").split()[0]
        self.result(i, "scope: INDIVIDUAL", "review C001: verdict=PASS_WITH_MINOR; fidelity=MATCH(assumes: n even)",
                    "blocking C001: O1 MINOR: Lemma 2 [BOUNDARY] - n = 1 case")
        self.result(s, "scope: SECOND-INDEPENDENT", "review C001: verdict=PASS; fidelity=MATCH; assumes=none")
        out = self.ri("ingest", self.R, i, s, "--accept")
        self.assertIn("accepted: C001 accepted (agent-checked) (assumes: n even); event E1 rung-accepted Q01", out)
        self.assertIn("ledger: L001 <- C001", out)
        st = self.state()
        self.assertEqual(st["reviews"][1]["note"], "single-draft")
        self.assertEqual(st["ledger"]["L001"]["statement"], "R2 holds for all n. (assumes: n even)")
        self.assertIn("events pending: rung-accepted Q01 (E1)", self.status())  # an open assumption goes to RENEW
        self.assertIn("check OK", self.ri("check", self.R))

    def test_ingest_scout_sanity_and_witness(self):
        p = self.prover_done()
        ce_p = self.prover_done(claims="Q01.R1", direction="DISPROVE Q01.D", kind="counterexample")
        self.ri("ingest", self.R, p, ce_p)
        sa = self.ri("task", "new", self.R, "--role", "scout", "--mode", "SANITY", "--cand", "C001", "--start").split()[0]
        wi = self.ri("task", "new", self.R, "--role", "scout", "--mode", "WITNESS", "--cand", "C002", "--start").split()[0]
        self.result(sa, "mode: SANITY", "check C001: outcome=contradicts; exact=yes",
                    "blocking C001: O1 CRITICAL: n = 3, k = 1 [SANITY] - ratio 0.61 < 0.63")
        self.result(wi, "mode: WITNESS", "checked: C002", "outcome: witness-valid", "exact: no")
        self.ri("ingest", self.R, sa, wi)
        revs = {r["cand"]: r for r in self.state()["reviews"]}
        self.assertEqual((revs["C001"]["scope"], revs["C001"]["verdict"]), ("sanity", "FAIL"))
        self.assertEqual([(o["id"], o["severity"]) for o in revs["C001"]["objections"]], [(f"{sa}.O1", "CRITICAL")])
        self.assertEqual((revs["C002"]["scope"], revs["C002"]["verdict"], revs["C002"]["note"]),
                         ("witness", "INCONCLUSIVE", "exact: no"))
        an = self.ri("task", "new", self.R, "--role", "scout", "--mode", "EXPLORE", "--title", "ANCHOR S01",
                     "--extra", "S01 baseline", "--start").split()[0]
        self.result(an, "mode: EXPLORE", "checked: anchor S01", "outcome: table-ready", "exact: yes", "anchor: trend")
        out = self.ri("ingest", self.R, an)
        self.assertIn("anchor: trend", out)
        self.assertEqual(self.state()["tasks"][an]["status"], "done")
        s2 = self.ri("task", "new", self.R, "--role", "scout", "--mode", "SANITY", "--cand", "C002", "--start").split()[0]
        self.result(s2, "check C002: outcome=witness-invalid; exact=yes")
        self.ri("ingest", self.R, s2)
        r = self.state()["reviews"][-1]
        self.assertEqual((r["scope"], r["verdict"], r["objections"][0]["severity"]), ("witness", "FAIL", "CRITICAL"))

    def test_ingest_adjudicate_rejected_unblocks(self):
        p = self.prover_done()
        self.ri("ingest", self.R, p)
        v = self.task("verifier", "INDIVIDUAL", lane="Q01")
        self.review("C001", v, "individual", "FAIL", "--blocking", "O2 CRITICAL: Lemma 3 [ALG] - sign")
        adj = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "ADJUDICATE", "--objection", f"{v}.O2", "--start").split()[0]
        self.result(adj, "scope: ADJUDICATE", f"ruling {v}.O2: REJECTED", "blocking C001: O1 MINOR: Lemma 3 [ALG] - typo")
        out = self.ri("ingest", self.R, adj)
        self.assertIn(f"review recorded: C001 adjudicate PASS by {adj}; objections {adj}.O1 MINOR", out)
        self.assertIn(f"{v}.O2 resolved (rejected by {adj}) on C001", out)
        ob = self.state()["reviews"][0]["objections"][0]
        self.assertEqual((ob["status"], ob["how"], ob["resolved_by"]), ("resolved", "rejected", adj))

    def test_ingest_problems_go_to_manual(self):
        p1, p2 = self.prover_done(), self.prover_done(claims="Q01.R1")
        self.ri("ingest", self.R, p1, p2)
        x = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "CROSS-DRAFT", "--cand", "C001,C002", "--start").split()[0]
        self.result(x, "scope: CROSS-DRAFT", "review C001: verdict=FAIL; fidelity=MATCH",
                    "blocking C001: O1 CRITICAL: a [ALG] - b", "review C002: verdict=FAIL; fidelity=MATCH",
                    "blocking C002: O1 CRITICAL: c [ALG] - d", "review C009: verdict=PASS; fidelity=MATCH")
        out = self.ri("ingest", self.R, x)
        self.assertIn("manual (handle by hand):", out)
        self.assertIn(f"{x} C002: review add refused: objection {x}.O1 is already used", out)
        self.assertIn(f"{x}: unknown candidate C009", out)
        self.assertEqual([r["cand"] for r in self.state()["reviews"]], ["C001"])
        nodraft = self.ri("task", "new", self.R, "--role", "prover", "--direction", "PROVE Q01.R1", "--start").split()[0]
        self.result(nodraft, "direction: PROVE Q01.R1", "claims: Q01.R1", "kind: proof")
        self.assertIn(f"{nodraft}: no draft.md to freeze; task set blocked", self.ri("ingest", self.R, nodraft))
        self.assertEqual(self.state()["tasks"][nodraft]["status"], "blocked")
        lost = self.ri("task", "new", self.R, "--role", "scout", "--extra", "x", "--start").split()[0]
        self.assertIn(f"{lost}: no tasks/{lost}/result.md", self.ri("ingest", self.R, lost))
        self.write(f"tasks/{lost}/result.md", "---\nsummary: no status here\n---\n")
        self.assertIn("has no status", self.ri("ingest", self.R, lost))
        self.write(f"tasks/{lost}/result.md", "---\nstatus: blocked\nartifacts: [table.csv]\n---\n")
        self.assertIn("artifacts: [table.csv]", self.ri("ingest", self.R, lost))
        self.assertEqual(self.state()["tasks"][lost]["status"], "blocked")
        self.assertIn("check OK", self.ri("check", self.R))

    def test_queued_task_with_result_or_outputs_is_reconciled_not_dispatched(self):
        t = self.task("scout")
        self.write(f"tasks/{t}/table.csv", "1,2\n")
        self.assertIn(f"{t}: queued but has outputs - possibly dispatched: reconcile", self.status())
        self.write(f"tasks/{t}/result.md", "---\nstatus: completed\n---\n")
        self.assertIn(f"{t}: result.md present - ingest RUN {t}", self.status())


class TestIntake(RiCase):
    def setUp(self):
        super().setUp()
        self.init()
        self.tmpd = Path(self.tmp.name)

    def zip_of(self, name, members):
        p = self.tmpd / name
        with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
            for n, data in members:
                z.writestr(n, data)
        return p

    def test_intake_zip_checks_types_and_nested_archives(self):
        deep = io.BytesIO()
        with zipfile.ZipFile(deep, "w") as z:
            z.writestr("y.txt", "deep")
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w") as z:
            z.writestr("x.csv", "1,2\n")
            z.writestr("deep.zip", deep.getvalue())
        arc = self.zip_of("bundle.zip", [
            ("bundle/README.md", "my notes: does 1 bit help?"), ("bundle/notes-on-X.txt", "X idea"),
            ("bundle/2301.12345.txt", "paper text"), ("bundle/papers/p1.pdf", b"%PDF-1.4"),
            ("bundle/code/sim.py", "print(1)"), ("bundle/CON.txt", "reserved"), ("bundle/a:b.tex", "\\section{}"),
            ("bundle/inner.zip", inner.getvalue()), ("../evil.txt", "escape"), ("bundle/../../evil2.txt", "escape"),
        ])
        out = self.ri("intake", self.R, "--archive", arc)
        self.assertIn("rejected: ../evil.txt: '..' path component", out)
        self.assertIn("rejected: bundle/../../evil2.txt: '..' path component", out)
        self.assertIn("renamed: bundle/CON.txt -> sources/raw/bundle/_CON.txt", out)
        self.assertIn("renamed: bundle/a:b.tex -> sources/raw/bundle/a_b.tex", out)
        self.assertFalse(Path(self.R).parent.joinpath("evil.txt").exists())
        self.assertFalse(self.path("evil.txt").exists())
        idx = self.path("sources", "index.md").read_text(encoding="utf-8")
        rows = {r.split("|")[2].strip(): [x.strip() for x in r.split("|")[1:-1]] for r in idx.splitlines()
                if re.match(r"\| S\d+ ", r)}
        self.assertEqual(rows["bundle/README.md"][3], "user-notes")
        self.assertEqual(rows["bundle/notes-on-X.txt"][3], "user-notes")
        self.assertEqual(rows["bundle/2301.12345.txt"][3], "text")  # top-level .txt, not named like notes
        self.assertEqual(rows["bundle/papers/p1.pdf"][3], "paper-pdf")
        self.assertEqual(rows["bundle/code/sim.py"][3], "code")
        self.assertEqual(rows["bundle/a:b.tex"][3], "tex")
        self.assertEqual(rows["bundle/inner.zip"][5], "extracted to sources/raw/bundle/inner/")
        self.assertEqual(rows["bundle/inner.zip:x.csv"][2], "sources/raw/bundle/inner/x.csv")
        self.assertEqual(rows["bundle/inner.zip:x.csv"][3], "data")
        self.assertEqual(rows["bundle/inner.zip:deep.zip"][5], "not extracted (nested deeper than one level)")
        self.assertFalse(self.path("sources", "raw", "bundle", "inner", "deep").exists())
        self.assertEqual(sorted(r[0] for r in rows.values()), [f"S{i:02d}" for i in range(1, 11)])
        self.assertEqual(self.path("sources", "raw", "bundle", "README.md").read_text(encoding="utf-8"),
                         "my notes: does 1 bit help?")
        self.assertIn("user-notes (read in full", out)
        arc2 = self.zip_of("more.zip", [("new.pdf", b"%PDF")])
        self.ri("intake", self.R, "--archive", arc2)
        self.assertIn("| S11 | new.pdf | sources/raw/new.pdf | paper-pdf |",
                      self.path("sources", "index.md").read_text(encoding="utf-8"))
        self.assertEqual(self.state()["counters"]["S"], 11)
        self.assertIn("check OK", self.ri("check", self.R))

    def test_intake_tar_rejects_links_and_absolute_paths(self):
        p = self.tmpd / "b.tar.gz"
        with tarfile.open(p, "w:gz") as tf:
            for name, data in (("ok/a.md", b"hello"), ("/etc/abs.txt", b"x")):
                ti = tarfile.TarInfo(name)
                ti.size = len(data)
                tf.addfile(ti, io.BytesIO(data))
            link = tarfile.TarInfo("ok/link")
            link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
            tf.addfile(link)
            dev = tarfile.TarInfo("ok/dev")
            dev.type = tarfile.CHRTYPE
            tf.addfile(dev)
        out = self.ri("intake", self.R, "--archive", p)
        self.assertIn("rejected: ok/link: symbolic or hard link", out)
        self.assertIn("rejected: ok/dev: device or special file", out)
        self.assertIn("absolute path", out)
        self.assertTrue(self.path("sources", "raw", "ok", "a.md").is_file())
        self.assertFalse(self.path("sources", "raw", "ok", "link").exists())

    def test_intake_caps_size_and_ratio(self):
        arc = self.zip_of("big.zip", [("a.bin", os.urandom(700_000)), ("b.bin", os.urandom(700_000))])
        out = self.ri("intake", self.R, "--archive", arc, "--max-mb", "1", code=1)
        self.assertIn("over the 1 MB cap", out)
        self.assertEqual(list(self.path("sources", "raw").iterdir()), [])
        bomb = self.zip_of("bomb.zip", [("zeros.bin", b"\0" * (3 << 20)), ("ok.txt", "fine")])
        out = self.ri("intake", self.R, "--archive", bomb)
        self.assertIn("rejected: zeros.bin: compression ratio above 200:1", out)
        self.assertTrue(self.path("sources", "raw", "ok.txt").is_file())
        self.ri("intake", self.R, "--archive", self.write("not-an-archive.txt", "plain"), code=2)


class TestStatusHoldsEvents(RiCase):
    def setUp(self):
        super().setUp()
        self.init()
        self.q = self.lane()

    def failed_round(self, tag="PROB"):
        p = self.task("prover", "PROVE", lane="Q01")
        c = self.cand(p, "Q01.R1")
        self.ri("task", "set", self.R, p, "done")
        v = self.task("verifier", "INDIVIDUAL", lane="Q01")
        self.review(c, v, "individual", "FAIL", "--blocking", f"O1 CRITICAL: Lemma 3 [{tag}] - fails")
        x = self.task("verifier", "SECOND-INDEPENDENT", lane="Q01")
        self.review(c, x, "cross", "FAIL", "--blocking", f"O1 CRITICAL: Lemma 3 [{tag}] - fails")
        self.ri("task", "set", self.R, v, x, "done")
        return c

    def test_status_suggests_mechanical_actions(self):
        notes = self.path("checkpoint.md").read_text(encoding="utf-8") + "\nMY NOTE: keep this\n"
        self.path("checkpoint.md").write_text(notes, encoding="utf-8")
        p1 = self.task("prover", "PROVE", lane="Q01", ctx="a1")
        p2 = self.task("prover", "PROVE", lane="Q01", ctx="a2")
        c1 = self.cand(p1, "Q01.R1")
        out = self.status()
        self.assertIn(f"{c1}: needs INDIVIDUAL review", out)
        self.assertIn("CROSS-DRAFT waits for cohort Q01 r1", out)
        self.ri("task", "set", self.R, p1, p2, "done")
        c2 = self.cand(p2, "Q01.R2")
        self.assertIn(f"{c1}, {c2}: needs CROSS-DRAFT (cohort Q01 r1 complete", self.status())
        cross = self.task("verifier", "CROSS-DRAFT", lane="Q01", fill=False)
        out = self.status()
        self.assertNotIn("needs CROSS-DRAFT", out)
        self.assertIn(f"{cross}: queued verifier - fill the Assignment, then task set {cross} running", out)
        self.ri("task", "set", self.R, cross, "running", "--context", "vx", "--force-empty")
        self.path("tasks", cross, "result.md").write_text("---\ntask: x\n---\n", encoding="utf-8")
        self.assertIn(f"{cross}: result.md present - ingest RUN {cross}", self.status())
        self.review(c1, cross, "cross", "PASS")
        self.review(c2, cross, "cross", "PASS")
        self.ri("task", "set", self.R, cross, "done")
        ind = self.task("verifier", "INDIVIDUAL", lane="Q01", ctx="v1", title=f"INDIVIDUAL {c1}")
        self.assertNotIn(f"{c1}: needs INDIVIDUAL", self.status())  # in flight (named in title)
        self.review(c1, ind, "individual", "PASS")
        self.ri("task", "set", self.R, ind, "done")
        self.assertIn(f"{c1}: gates satisfied - accept", self.status())
        self.ri("accept", self.R, c1)
        self.selected()
        out = self.status()
        self.assertIn("events pending: top-accepted Q01 (E1) -> dispatch investigator RENEW", out)
        self.assertIn(f"Q01: R1 accepted ({c1})", out)
        self.assertIn(f"{c1}: accepted - ledger add", out)
        cp = self.path("checkpoint.md").read_text(encoding="utf-8")
        block = cp.split(ri.ST_BEGIN)[1].split(ri.ST_END)[0]
        self.assertIn("SUGGESTED NEXT ACTIONS", block)
        self.assertLessEqual(len(block.strip().splitlines()), ri.STATUS_LINES)
        self.assertIn("MY NOTE: keep this", cp)
        self.assertEqual(cp.count(ri.ST_BEGIN), 1)

    def test_status_single_draft_round_close_and_advisor_due(self):
        p = self.task("prover", "PROVE", lane="Q01")
        c = self.cand(p, "Q01.R2")
        self.ri("task", "set", self.R, p, "done")
        self.assertIn(f"{c}: needs SECOND-INDEPENDENT review (single-draft cohort Q01 r1)", self.status())
        v1 = self.task("verifier", "INDIVIDUAL", lane="Q01")
        v2 = self.task("verifier", "SECOND-INDEPENDENT", lane="Q01")
        self.review(c, v1, "individual", "FAIL", "--blocking", "O1 CRITICAL: bound false", "--confirmed", "Lemma 1")
        self.review(c, v2, "cross", "PASS", "--note", "single-draft")
        self.ri("task", "set", self.R, v1, v2, "done")
        out = self.status()
        self.assertIn(f"Q01 r1: blocking objections on {c} - route per I8", out)
        self.assertIn("Q01 r1 closed: ledger auditor on confirmed steps (task new --role ledger-auditor --lane Q01 "
                      "--round 1); plan round 2 (round Q01 --open)", out)
        self.assertIn("process advisor due (reviews since the last advisor task): Q01 r1", out)
        self.ri("round", self.R, "Q01", "--open")
        out = self.status()
        self.assertIn("process advisor due (reviews since the last advisor task): Q01 r1", out)  # not starved
        self.assertIn("Q01 r2: write plan.md slots (allocation rules); BRIEF waits for r1 close work: ledger auditor, process advisor", out)
        self.assertNotIn(f"  {c} Q01.R2", out)  # LANES: only the current round and incomplete gates
        adv = self.task("process-advisor")
        self.assertNotIn("process advisor due", self.status())
        self.ri("task", "set", self.R, adv, "done")
        self.assertNotIn("process advisor due", self.status())

    def test_i8_reminders_grouped_per_lane_round(self):
        for _ in range(2):
            p = self.task("prover", "PROVE", lane="Q01")
            c = self.cand(p, "Q01.R1")
            self.review(c, self.task("verifier", "INDIVIDUAL", lane="Q01"), "individual", "FAIL",
                        "--blocking", "O1 CRITICAL: Lemma 3 [PROB] - same step")
        out = self.status()
        self.assertIn("Q01 r1: blocking objections on C001, C002 - route per I8", out)
        self.assertNotIn("same failing step?", out)  # E7: no stall guess from step labels
        self.assertEqual(out.count("route per I8"), 1)

    def test_status_stays_useful_after_many_failed_rounds(self):
        for _ in range(5):
            self.failed_round()
            self.failed_round()
            self.ri("round", self.R, "Q01", "--open")
        self.ri("event", self.R, "--type", "stall", "--lane", "Q01", "--note", "no progress")
        brief = self.status("--brief")
        self.assertLessEqual(len(brief.splitlines()), ri.BRIEF_LINES)
        nxt = brief.split("next:\n", 1)[1].splitlines()
        self.assertIn("Q01 HELD by E1 (stall) until RENEW", nxt[0])
        self.assertIn("E1 stall Q01: dispatch literature-reviewer TARGETED on the stuck step", nxt[1])
        self.assertEqual(brief.count("route per I8"), 1)
        self.assertIn("Q01 r1-r4: 8 older blocked drafts", brief)
        self.assertNotIn("plan round", brief)

    def test_no_progress_for_two_rounds_suggests_stall(self):
        self.failed_round()
        self.ri("round", self.R, "Q01", "--open")
        self.failed_round()
        self.ri("round", self.R, "Q01", "--open")
        self.assertNotIn("no progress", self.status())  # round 1 brought a new tag
        self.failed_round()
        self.ri("round", self.R, "Q01", "--open")
        self.assertIn("Q01: no progress in rounds 2 and 3 (no new accepted rung, ledger entry or objection tag) - "
                      "event --type stall --lane Q01", self.status())
        self.ri("event", self.R, "--type", "stall", "--lane", "Q01", "--note", "no progress")
        self.assertNotIn("no progress in rounds", self.status())

    def test_new_objection_tag_counts_as_progress(self):
        self.failed_round("PROB")
        self.ri("round", self.R, "Q01", "--open")
        self.failed_round("PROB")
        self.ri("round", self.R, "Q01", "--open")
        self.failed_round("CONST")
        self.ri("round", self.R, "Q01", "--open")
        self.assertNotIn("no progress", self.status())

    def test_holds_block_round_open_until_handled(self):
        self.selected()
        out = self.ri("event", self.R, "--type", "stall", "--lane", "Q01", "--note", "Lemma 3")
        self.assertIn("Q01 HELD until RENEW", out)
        self.assertEqual(self.state()["questions"]["Q01"]["held_by"], ["E1"])
        self.assertIn("already pending", self.ri("event", self.R, "--type", "stall", "--lane", "Q01"))
        self.assertEqual(len(self.state()["events"]), 1)
        out = self.status()
        self.assertIn("Q01 HELD by E1 (stall) until RENEW (no new round)", out)
        self.assertIn("E1 stall Q01: dispatch literature-reviewer TARGETED on the stuck step", out)
        self.assertNotIn("dispatch investigator RENEW", out)
        tg = self.task("literature-reviewer", "TARGETED", lane="Q01")
        self.assertIn(f"E1 stall Q01: RENEW waits for {tg}", self.status())
        self.ri("task", "set", self.R, tg, "done")
        self.assertIn("events pending: stall Q01 (E1) -> dispatch investigator RENEW", self.status())
        self.assertIn("HELD(E1 (stall))", out)
        self.assertNotIn("plan round", out)
        self.assertNotIn("dispatch one summarizer", out)
        self.assertIn("HELD by E1 (stall)", self.ri("round", self.R, "Q01", "--open", code=1))
        self.assertIn("held: Q01 by E1 (stall)", self.status("--brief"))
        inv = self.task("investigator", "RENEW")
        out = self.ri("event", self.R, "--handled", "E1", "--by", inv)
        self.assertIn("holds released on Q01", out)
        self.assertEqual(self.state()["questions"]["Q01"]["held_by"], [])
        self.ri("round", self.R, "Q01", "--open")
        self.ri("event", self.R, "--type", "literature-hit", "--lane", "Q01")
        self.assertEqual(self.ri("round", self.R, "Q01", "--open", "--override-hold").strip(), "3")
        self.ri("event", self.R, "--handled", "E7", "--by", inv, code=2)
        self.ri("event", self.R, "--type", "bogus", code=2)
        self.ri("event", self.R, "--type", "milestone", "--note-file", self.write("n.txt", "headline $H1$"))
        self.assertEqual(self.state()["events"][-1]["note"], "headline $H1$")

    def test_lane_budget_due_again_after_renewal(self):
        self.ri("init", str(Path(self.tmp.name, "r2")), "--objective", "x", "--lane-budget", "2")
        self.R = str(Path(self.tmp.name, "r2"))
        self.lane()
        self.failed_round()
        self.ri("round", self.R, "Q01", "--open")
        self.failed_round()
        self.assertIn("lane budget reached: event --type lane-budget --lane Q01", self.status())
        self.assertIn("lane-budget event is due", self.ri("round", self.R, "Q01", "--open", "--override-hold"))
        self.ri("event", self.R, "--type", "lane-budget", "--lane", "Q01")
        self.ri("round", self.R, "Q01", "--open", code=1)
        inv = self.task("investigator", "RENEW")
        self.ri("event", self.R, "--handled", "E1", "--by", inv)
        self.assertEqual(self.state()["questions"]["Q01"]["budget_base"], 3)
        self.assertNotIn("lane-budget event is due", self.ri("round", self.R, "Q01", "--open"))
        self.assertIn("budget 1 of 2", self.path("lanes", "Q01", "round-04", "plan.md").read_text(encoding="utf-8"))

    def test_q_set_slots_plausibility_and_plan_header(self):
        self.ri("q", "set", self.R, "Q01", "--slots", "4", "--plausibility", "Mixed", "--model", "m2",
                "--title", "Does X help (v2)?", "--rung", "R1")
        q = self.state()["questions"]["Q01"]
        self.assertEqual((q["slots"], q["plausibility"], q["model"], q["title"], q["rung"]),
                         (4, "mixed", "M2", "Does X help (v2)?", "R1"))
        self.ri("round", self.R, "Q01", "--open")
        self.assertEqual(self.path("lanes", "Q01", "round-02", "plan.md").read_text(encoding="utf-8"),
                         "# Q01 round 02 — N = 4; rung R1; plausibility mixed; budget 2 of 8\n")
        self.assertIn("Q01 [CORE] N=4 mixed round 2", self.status())
        self.ri("q", "set", self.R, "Q01", "--slots", "0", code=2)
        self.ri("q", "set", self.R, "Q01", "--plausibility", "certain", code=2)
        self.ri("q", "set", self.R, "Q01", code=2)

    def test_queue_low_waits_for_select_and_uses_k(self):
        R2 = str(Path(self.tmp.name, "r2"))
        self.ri("init", R2, "--objective", "x", "--k", "8")
        self.R = R2
        self.lane()
        out = self.status()
        self.assertNotIn("queue low", out)  # before the first SELECT
        self.assertIn("opening (program.md sec. 2)", out)
        sel = self.task("investigator", "SELECT")
        self.ri("task", "set", self.R, sel, "done")
        out = self.status()
        self.assertIn("queue low (0 ready + 0 vetting < 3 free lanes)", out)
        self.assertNotIn("opening (program.md", out)

    def test_too_easy_suggests_skeptic_gates_not_renew(self):
        self.selected()
        self.ri("event", self.R, "--type", "too-easy", "--lane", "Q01", "--note", "C001: c-inf (T009)")
        out = self.status()
        self.assertIn("E1 too-easy Q01: dispatch skeptic MODEL-GATE + CLAIM-GATE (two tasks) first", out)
        self.assertNotIn("dispatch investigator RENEW", out)
        self.assertNotIn("too-easy", ri.RENEW_TYPES)
        gates = [self.task("skeptic", m) for m in ("MODEL-GATE", "CLAIM-GATE")]
        self.assertIn(f"E1 too-easy Q01: RENEW waits for {gates[0]}, {gates[1]}", self.status())
        self.ri("task", "set", self.R, *gates, "done")
        self.assertIn("events pending: too-easy Q01 (E1) -> dispatch investigator RENEW", self.status())

    def test_status_brief_and_priority_order(self):
        for _ in range(12):
            self.task("scout", fill=True)
        p = self.task("prover", "PROVE", lane="Q01", ctx="a1")
        self.cand(p, "Q01.R1")
        w = self.task("writer", ctx="w1")
        self.write(f"tasks/{w}/result.md", "---\nstatus: completed\n---\n")
        out = self.status("--brief").splitlines()
        self.assertLessEqual(len(out), ri.BRIEF_LINES)
        self.assertTrue(out[0].startswith("ri status"))
        self.assertTrue(out[1].startswith("live: "))
        acts = self.status().split("SUGGESTED NEXT ACTIONS:")[1]
        self.assertLess(acts.index(f"{w}: result.md present"), acts.index("C001: needs INDIVIDUAL review"))
        block = self.path("checkpoint.md").read_text(encoding="utf-8").split(ri.ST_BEGIN)[1]
        self.assertIn("counts:", block)  # the checkpoint keeps the full block
        self.ri("status", self.R, "--brief", "--full", code=2)


class TestIsolationAndCli(RiCase):
    def test_l1_isolation_gives_self_checked_label(self):
        self.init("--isolation", "L1")
        self.lane()
        p = self.task("prover", "PROVE", lane="Q01", ctx="root")
        c = self.cand(p)
        self.review(c, self.task("verifier", "INDIVIDUAL", lane="Q01", ctx="root"), "individual", "PASS")
        self.review(c, self.task("verifier", "CROSS-DRAFT", lane="Q01", ctx="root"), "cross", "PASS")
        self.assertIn("self-checked", self.ri("accept", self.R, c))
        self.ri("ledger", "add", self.R, "--cand", c)
        self.assertEqual(self.state()["ledger"]["L001"]["label"], "self-checked")

    def test_one_l1_review_downgrades_label(self):
        self.init()
        self.lane()
        p = self.task("prover", "PROVE", lane="Q01")
        c = self.cand(p)
        v1 = self.task("verifier", "INDIVIDUAL", lane="Q01")
        self.ri("task", "set", self.R, v1, "running", "--isolation", "L1")
        self.review(c, v1, "individual", "PASS")
        self.review(c, self.task("verifier", "CROSS-DRAFT", lane="Q01"), "cross", "PASS")
        self.ri("accept", self.R, c)
        self.assertEqual(self.state()["candidates"][c]["label"], "self-checked")

    def test_check_clean_then_tampered_and_log(self):
        self.init()
        self.lane()
        self.accepted("Q01.R2")
        self.assertIn("check OK", self.ri("check", self.R))
        seqs = [json.loads(x)["seq"] for x in self.path("log.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(seqs, list(range(1, self.state()["seq"] + 1)))
        self.assertEqual(list(Path(self.R).rglob("*.tmp")), [])
        self.path("candidates", "C001.md").write_text("tampered\n", encoding="utf-8")
        self.assertIn("C001: candidates/C001.md does not match its frozen sha256", self.ri("check", self.R, code=1))
        with open(self.path("log.jsonl"), "a", encoding="utf-8") as f:
            f.write('{"seq": 1, "cmd": "forged"}\n')
        self.assertIn("not strictly increasing", self.ri("check", self.R, code=1))

    def test_check_detects_ungated_acceptance(self):
        self.init()
        self.lane()
        p = self.task("prover", "PROVE", lane="Q01")
        c = self.cand(p, "Q01.R1")
        st = self.state()
        st["candidates"][c]["status"] = "accepted"
        self.save(st)
        self.assertIn(f"{c}: accepted but gate fails", self.ri("check", self.R, code=1))

    def test_load_bearing_entry_needs_second_isolated(self):
        self.init()
        self.lane()
        p = self.task("prover", "PROVE", lane="Q01")
        src = self.cand(p, "Q01.R2")
        aud = self.task("ledger-auditor", lane="Q01")
        frag = self.cand(aud, None, "--from", src)
        self.review(frag, self.task("verifier", "ISOLATED"), "isolated", "PASS")
        self.ri("accept", self.R, frag)
        self.ri("ledger", "add", self.R, "--cand", frag)
        self.accepted("Q01.R1", "--deps", "L001")
        self.assertIn(f"L001: load-bearing - dispatch a second ISOLATED review of {frag}", self.status())
        self.assertIn("load-bearing", self.path("ledger.md").read_text(encoding="utf-8"))

    def test_manuscript_needs_paper_review(self):
        self.init()
        self.lane()
        w = self.task("writer")
        m = self.cand(w, None, "--kind", "manuscript")
        self.ri("accept", self.R, m, code=1)
        self.review(m, self.task("verifier", "PAPER"), "paper", "PASS_WITH_MINOR")
        self.assertIn("agent-checked", self.ri("accept", self.R, m))

    def test_unparseable_instructions_warn(self):
        self.init()
        self.lane()
        self.path("instructions.md").write_text("# Standing instructions\nRevision 2\n\n| rule | applies |\n",
                                                encoding="utf-8")
        self.assertIn("no parseable rules", self.ri("task", "new", self.R, "--role", "prover", "--lane", "Q01"))

    def test_opening_and_focused_hints(self):
        self.init()
        self.assertIn("opening (program.md sec. 2)", self.status())
        R2 = str(Path(self.tmp.name, "f"))
        self.ri("init", R2, "--objective", "claim", "--mode", "focused")
        self.assertIn("focused (SKILL.md sec. 5)", self.ri("status", R2))

    def test_note_file_and_reason_file(self):
        self.init()
        self.lane()
        Path(self.tmp.name, "n.txt").write_text("parked: needs `X` and $Y$", encoding="utf-8")
        self.ri("q", "set", self.R, "Q01", "--note-file", Path(self.tmp.name, "n.txt"))
        self.assertEqual(self.state()["questions"]["Q01"]["note"], "parked: needs `X` and $Y$")
        self.ri("q", "set", self.R, "Q01", "--note", "a", "--note-file", Path(self.tmp.name, "n.txt"), code=2)
        self.ri("stop", self.R, "--reason-file", Path(self.tmp.name, "n.txt"))
        self.assertIn("parked: needs `X` and $Y$", self.path("STOP").read_text(encoding="utf-8"))

    def test_cli_subprocess_exit_codes_and_help(self):
        env = dict(os.environ, RI_SKILL_DIR=str(self.skill))
        run = lambda *a: subprocess.run([sys.executable, "-B", str(SCRIPT), *with_isolation(a)],
                                        capture_output=True, text=True, env=env)
        self.assertEqual(run("init", self.R, "--objective", "x").returncode, 0)
        self.assertEqual(run("status", self.R).returncode, 0)
        self.assertEqual(run("accept", self.R, "C001").returncode, 2)
        self.assertEqual(run("init", self.R, "--objective", "x").returncode, 1)
        helped = run("--help")
        self.assertEqual(helped.returncode, 0)
        for name in ("init", "intake", "status", "task new", "task set", "ingest", "cand add", "review add",
                     "objection resolve", "accept", "ledger add", "exclude", "quarantine", "record", "event",
                     "stop", "pause", "resume", "check"):
            self.assertIn(name, helped.stdout)




class TestV611Additions(RiCase):
    def test_init_requires_isolation(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            got = ri.main(["init", self.R, "--objective", "x"])
        self.assertEqual(got, 2)

    def test_ingest_files_advisor_instructions(self):
        self.init()
        tid = self.ri("task", "new", self.R, "--role", "process-advisor", "--start").split()[0]
        d = self.path("tasks", tid)
        (d / "advisor-log.md").write_text("patterns\n", encoding="utf-8")
        (d / "instructions.md").write_text(
            "# Standing instructions\nrevision: 1\n\n## SI01\napplies: prover\nreview-safe: yes\n"
            "text: State what every constant depends on.\nreason: CONST objections.\nsince: 1\n", encoding="utf-8")
        (d / "result.md").write_text(
            f"---\ntask: {tid}\nrole: process-advisor\nstatus: completed\nsummary: one rule\n"
            "artifacts: [advisor-log.md, instructions.md]\nrevision: 1\n---\nok\n", encoding="utf-8")
        out = self.ri("ingest", self.R, tid)
        self.assertIn("filed", out)
        self.assertIn("SI01", self.path("instructions.md").read_text(encoding="utf-8"))
        p = self.ri("task", "new", self.R, "--role", "prover", "--extra", "Prove it.").split()[0]
        packet = self.path("tasks", p, "packet.md").read_text(encoding="utf-8")
        self.assertIn("SI01: State what every constant depends on.", packet)
        self.assertNotIn("CONST objections", packet)


class TestV61ReviewFixes(RiCase):
    """Fixes from the v6.1 consistency review (CLI walk-through and cross-file check)."""

    def setUp(self):
        super().setUp()
        self.init()
        self.q = self.lane()

    def ce_with_two_gates(self, claims="Q01.R2"):
        p = self.task("prover", "DISPROVE", lane="Q01")
        ce = self.cand(p, claims, "--kind", "counterexample")
        self.review(ce, self.task("verifier", "INDIVIDUAL", lane="Q01"), "individual", "PASS")
        self.review(ce, self.task("verifier", "SECOND-INDEPENDENT", lane="Q01"), "cross", "PASS")
        return ce

    def test_blocked_witness_task_waives_the_witness_gate(self):
        ce = self.ce_with_two_gates()
        self.assertIn("needs WITNESS pass", self.ri("accept", self.R, ce, code=1))
        w = self.ri("task", "new", self.R, "--role", "scout", "--mode", "WITNESS", "--cand", ce, "--start").split()[0]
        self.result(w, "mode: WITNESS", f"checked: {ce}", status="blocked")
        self.ri("ingest", self.R, w)
        self.assertEqual(self.state()["tasks"][w]["status"], "blocked")
        self.assertIn(f"{ce} accepted", self.ri("accept", self.R, ce))

    def test_no_code_run_gates_counterexamples_without_witness(self):
        self.R = str(Path(self.tmp.name) / "run2")
        self.assertIn("no code execution", self.ri("init", self.R, "--objective", "x", "--no-code"))
        self.assertIs(self.state()["code"], False)
        self.lane()
        ce = self.ce_with_two_gates()
        self.assertIn(f"{ce}: gates satisfied", self.status())
        self.assertIn(f"{ce} accepted", self.ri("accept", self.R, ce))

    def test_paper_default_names_trace_and_renew_names_targeted_reports(self):
        acc = self.accepted("Q01.R2")
        w = self.task("writer")
        m = self.cand(w, None, "--kind", "manuscript")
        a = self.assignment(self.ri("task", "new", self.R, "--role", "verifier", "--mode", "PAPER",
                                    "--cand", f"{m},{acc}").split()[0])
        self.assertLess(a.index(f"- tasks/{w}/trace.md: only its '## Expansions' table in phase 1"),
                        a.index("Phase 2 only"))
        self.assertLess(a.index("Phase 2 only"), a.index(f"- tasks/{w}/trace.md (the rest)"))
        lit = self.task("literature-reviewer", "TARGETED", lane="Q01")
        self.ri("task", "set", self.R, lit, "done")
        ren = self.ri("task", "new", self.R, "--role", "investigator", "--mode", "RENEW").split()[0]
        self.assertIn(f"- tasks/{lit}/targeted.md (literature-reviewer TARGETED Q01)", self.assignment(ren))
        p = self.task("prover", "PROVE", lane="Q01")
        g = self.cand(p, "Q01.R1", "--gap", "Lemma 4")
        sv = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "SALVAGE", "--cand", g).split()[0]
        self.assertIn("skip the declared gaps and the assembly", self.assignment(sv))

    def test_ledger_add_statement_file_keeps_dollar_signs_and_backticks(self):
        c = self.accepted("Q01.R2")
        f = Path(self.tmp.name, "stmt.txt")
        f.write_text("For all $k$-server instances, `x` holds.\n", encoding="utf-8")
        self.ri("ledger", "add", self.R, "--cand", c, "--statement-file", str(f))
        self.assertEqual(self.state()["ledger"]["L001"]["statement"], "For all $k$-server instances, `x` holds.")

    def test_late_draft_gets_second_independent_not_a_new_cross_draft(self):
        p1, p2 = self.task("prover", "PROVE", lane="Q01"), self.task("prover", "PROVE", lane="Q01")
        c1, c2 = self.cand(p1, "Q01.R1"), self.cand(p2, "Q01.R2")
        x = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "CROSS-DRAFT", "--cand", f"{c1},{c2}",
                    "--start").split()[0]
        self.result(x, "scope: CROSS-DRAFT", f"review {c1}: verdict=PASS; fidelity=MATCH",
                    f"review {c2}: verdict=PASS; fidelity=MATCH")
        self.ri("ingest", self.R, x)
        late = self.cand(p1, "Q01.R3")  # e.g. re-filed for a weaker rung (verification.md sec. 4)
        out = self.status("--full")
        self.assertIn(f"{late}: needs SECOND-INDEPENDENT review (late draft; cohort Q01 r1 already cross-reviewed "
                      f"by {x})", out)
        self.assertNotIn("needs CROSS-DRAFT", out)

    def test_adjudicate_blocking_line_on_the_rebuttal_draft_is_recorded(self):
        p = self.task("prover", "PROVE", lane="Q01")
        c = self.cand(p, "Q01.R1")
        v = self.task("verifier", "INDIVIDUAL", lane="Q01")
        self.review(c, v, "individual", "FAIL", "--blocking", "O2 CRITICAL: Lemma 3 [ALG] - sign")
        rep = self.cand(p, "Q01.R1", "--revises", c, text=f"# Draft\n## Theorem\nX.\n## Rebuttals\n{v}.O2: fine.\n")
        adj = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "ADJUDICATE", "--objection", f"{v}.O2",
                      "--start").split()[0]
        self.result(adj, "scope: ADJUDICATE", f"ruling {v}.O2: UPHELD",
                    f"blocking {rep}: O4 CRITICAL: Rebuttals [ALG] - the sign is still wrong")
        out = self.ri("ingest", self.R, adj)
        self.assertIn(f"review recorded: {c} adjudicate FAIL by {adj}", out)
        self.assertIn(f"review recorded: {rep} adjudicate FAIL by {adj}; objections {adj}.O4 CRITICAL", out)
        self.assertIn((rep, f"{adj}.O4"), [(r["cand"], o["id"]) for r in self.state()["reviews"] for o in r["objections"]])

    def test_bom_result_and_claim_keys_are_read(self):
        sk = self.ri("task", "new", self.R, "--role", "skeptic", "--mode", "CLAIM-GATE", "--extra", "Gate Q01.R1.",
                     "--start").split()[0]
        text = f"---\ntask: {sk}\nrole: skeptic\nstatus: completed\nsummary: gate\nQ01.R1: {{verdict: QUALIFY}}\n---\n"
        self.path("tasks", sk, "result.md").write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))  # PowerShell 5.1 BOM
        out = self.ri("ingest", self.R, sk)
        self.assertIn(f"{sk} skeptic CLAIM-GATE: done", out)
        self.assertIn("Q01.R1: QUALIFY -> copy the qualifier verbatim", out)

    def test_cancelled_task_is_listed_for_reconciliation_after_a_stop(self):
        t = self.task("summarizer", lane="Q01")
        self.ri("task", "set", self.R, t, "running")
        self.ri("stop", self.R, "--reason", "user said stop")
        self.ri("task", "set", self.R, t, "cancelled")
        self.assertNotIn(f"{t}: cancelled", self.status("--brief"))  # under STOP nothing is dispatched
        self.ri("resume", self.R, "--stop", "--reason", "resume the stopped run")
        self.assertIn(f"{t}: cancelled summarizer - reconcile", self.status("--brief"))
        self.ri("task", "new", self.R, "--redo", t, "--start")
        self.assertNotIn(f"{t}: cancelled", self.status())

    def test_ingest_accept_of_a_d_proof_says_its_ledger_entry_exists(self):
        p = self.task("prover", "DISPROVE", lane="Q01")
        d = self.cand(p, "Q01.D", "--kind", "impossibility")
        self.review(d, self.task("verifier", "INDIVIDUAL", lane="Q01"), "individual", "PASS")
        x = self.task("verifier", "CROSS-DRAFT", lane="Q01", ctx="agent-x")
        self.result(x, "scope: CROSS-DRAFT", f"review {d}: verdict=PASS; fidelity=MATCH")
        out = self.ri("ingest", self.R, x, "--accept")
        self.assertIn(f"next: ri.py exclude RUN --claim Q01.R1 --cand {d}", out)
        self.assertIn("its ledger entry is already added", out)
        self.assertNotIn("optionally ledger add", out)

    def test_special_case_draft_off_the_ladder_gets_the_manual_route(self):
        p = self.ri("task", "new", self.R, "--role", "prover", "--lane", "Q01", "--direction",
                    "SPECIAL-CASE n = 2, k = 1", "--start").split()[0]
        self.write(f"tasks/{p}/draft.md", "# Draft\n## Theorem\nThe case n = 2, k = 1 holds.\n")
        self.result(p, "direction: SPECIAL-CASE n = 2, k = 1", "claims: none", "kind: proof", "gaps: none")
        self.assertIn("--kind lemma --direction", self.ri("ingest", self.R, p))
        self.ri("cand", "add", self.R, "--lane", "Q01", "--kind", "lemma", "--direction", "SPECIAL-CASE n = 2, k = 1",
                "--file", f"tasks/{p}/draft.md", "--author", p)
        c = self.state()["candidates"]["C001"]
        self.assertEqual((c["kind"], c["lane"], c["direction"]), ("lemma", "Q01", "SPECIAL-CASE n = 2, k = 1"))


class TestV62RunFixes(RiCase):
    """Fixes from the first end-to-end runs on real research topics (v6.2)."""

    def setUp(self):
        super().setUp()
        self.init()
        self.q = self.lane()

    def failed_round(self):
        p = self.task("prover", "PROVE", lane="Q01")
        c = self.cand(p, "Q01.R2")
        v = self.task("verifier", "INDIVIDUAL", lane="Q01")
        self.review(c, v, "individual", "FAIL", "--blocking", "O1 CRITICAL: Lemma 3 [PROB] - fails")
        x = self.task("verifier", "SECOND-INDEPENDENT", lane="Q01")
        self.review(c, x, "cross", "FAIL", "--blocking", "O1 CRITICAL: Lemma 3 [PROB] - fails")
        self.ri("task", "set", self.R, p, v, x, "done")
        return c

    def focused(self, rung):
        self.R = str(Path(self.tmp.name, "f"))
        self.ri("init", self.R, "--objective", "prove only this claim", "--mode", "focused", "--after", "stop",
                "--stop-quote", "prove only this claim")  # v6.3 endings
        self.ri("q", "add", self.R, "--title", "claim", "--model", "M1")
        self.ri("q", "set", self.R, "Q01", "--status", "active", "--rung", rung)

    def accept_with_assumption(self, claims):
        p = self.task("prover", "PROVE", lane="Q01")
        c = self.cand(p, claims)
        self.review(c, self.task("verifier", "INDIVIDUAL", lane="Q01"), "individual", "PASS", "--assumes", "n even")
        self.review(c, self.task("verifier", "CROSS-DRAFT", lane="Q01"), "cross", "PASS")
        self.ri("accept", self.R, c)
        return c

    def test_q1_review_file_is_review_md(self):
        p = self.task("prover", "PROVE", lane="Q01")
        c = self.cand(p, "Q01.R1")
        a = self.assignment(self.ri("task", "new", self.R, "--role", "verifier", "--mode", "INDIVIDUAL", "--cand", c).split()[0])
        self.assertIn("Return: review.md and result.md", a)
        self.assertTrue(a.endswith("Stop condition: review.md and result.md written for every listed candidate."))
        self.assertNotIn("report.md", a)
        self.r1()
        qg = self.ri("task", "new", self.R, "--role", "skeptic", "--mode", "QUESTION-GATE", "--question", "Q01").split()[0]
        self.assertIn("Return: gate.md and result.md", self.assignment(qg))  # the skeptic prompt's file name
        self.assertNotIn("report.md", " ".join(ri.STOP_DEFAULT.values()))
        v1, v2 = self.task("verifier", "INDIVIDUAL", lane="Q01"), self.task("verifier", "SECOND-INDEPENDENT", lane="Q01")
        self.write(f"tasks/{v1}/review.md", "r")
        self.write(f"tasks/{v2}/report.md", "r")  # the pre-6.2 name still works
        self.review(c, v1, "individual", "PASS")
        self.review(c, v2, "cross", "PASS")
        self.assertEqual([r["report"] for r in self.state()["reviews"]], [f"tasks/{v1}/review.md", f"tasks/{v2}/report.md"])
        c2 = self.cand(p, "Q01.R2")
        x = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "INDIVIDUAL", "--cand", c2, "--start").split()[0]
        self.write(f"tasks/{x}/review.md", "default name")
        self.write(f"tasks/{x}/second-look.md", "listed first")
        self.result(x, "scope: INDIVIDUAL", f"review {c2}: verdict=PASS; fidelity=MATCH",
                    "artifacts: [result.md, second-look.md, review.md]")
        y = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "SECOND-INDEPENDENT", "--cand", c2,
                    "--start").split()[0]
        self.write(f"tasks/{y}/report.md", "legacy name")
        self.result(y, "scope: SECOND-INDEPENDENT", f"review {c2}: verdict=PASS; fidelity=MATCH", "artifacts: [missing.md]")
        s = self.ri("task", "new", self.R, "--role", "scout", "--mode", "SANITY", "--cand", c2, "--start").split()[0]
        self.result(s, "mode: SANITY", f"check {c2}: outcome=consistent; exact=yes")
        self.ri("ingest", self.R, x, y, s)
        self.assertEqual([r["report"] for r in self.state()["reviews"][2:]],
                         [f"tasks/{x}/second-look.md", f"tasks/{y}/report.md", f"tasks/{s}/result.md"])
        self.assertIn("check OK", self.ri("check", self.R))

    def test_q2_never_include_matches_exact_paths_only(self):
        p = self.task("prover", "PROVE", lane="Q01")
        c = self.cand(p, "Q01.R1")
        ok = "Also read frontier/advice-notes.md, tasks/T005/advice-notes.md and scout/old-record.md."
        self.ri("task", "new", self.R, "--role", "verifier", "--mode", "INDIVIDUAL", "--cand", c, "--extra", ok)
        for bad in ("See tasks/T005/review.md.", "See tasks\\T005\\notes.md.", "See lanes/Q01/record.md.",
                    "Open 'record.md' first.", "notes.md has the idea.", "Card: questions/Q01.md",
                    f"See {self.R}/tasks/{p}/result.md", "Old: tasks/T005/report.md"):
            out = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "INDIVIDUAL", "--cand", c,
                          "--extra", bad, code=1)
            self.assertIn("never-include", out, bad)
        self.ri("task", "new", self.R, "--role", "summarizer", "--direction", "PROVE Q01.R1",
                "--extra", "See frontier/subquestions/Q01.md and old-questions/Q01.md.")
        self.ri("task", "new", self.R, "--role", "summarizer", "--direction", "PROVE Q01.R1",
                "--extra", "Read questions/Q01.md too.", code=1)

    def test_q3_per_lane_budget(self):
        self.assertIn("budget 2", self.ri("q", "set", self.R, "Q01", "--budget", "2"))
        self.assertEqual(self.state()["questions"]["Q01"]["budget"], 2)
        self.ri("q", "set", self.R, "Q01", "--budget", "0", code=2)
        self.failed_round()
        out = self.status()
        self.assertIn("(budget 1/2)", out)
        self.assertNotIn("lane budget reached", out)
        self.ri("round", self.R, "Q01", "--open")
        self.assertIn("budget 2 of 2", self.path("lanes", "Q01", "round-02", "plan.md").read_text(encoding="utf-8"))
        self.failed_round()
        self.assertIn("lane budget reached: event --type lane-budget --lane Q01", self.status())
        self.assertIn("passes the lane budget (2 rounds since the last renewal)", self.ri("round", self.R, "Q01", "--open"))

    def test_q4_focused_opening_hint_stops_once_the_lane_moves(self):
        R2 = str(Path(self.tmp.name, "f"))
        self.ri("init", R2, "--objective", "claim", "--mode", "focused")
        self.ri("q", "add", R2, "--title", "claim")
        self.ri("q", "set", R2, "Q01", "--status", "vetting")
        self.assertIn("focused (SKILL.md sec. 5)", self.ri("status", R2))
        self.ri("q", "set", R2, "Q01", "--status", "parked")
        self.assertNotIn("focused (SKILL.md sec. 5)", self.ri("status", R2))
        self.ri("q", "set", R2, "Q01", "--status", "active")
        self.ri("round", R2, "Q01", "--open")
        self.ri("q", "set", R2, "Q01", "--status", "vetting")
        self.assertNotIn("focused (SKILL.md sec. 5)", self.ri("status", R2))

    def test_q4_focused_target_rung_accepted_consolidates_instead_of_renew(self):
        self.focused("R2")
        self.write("lanes/Q01/statement.md", "Goal. R1 (optional), R2 (target rung), R3 (fallback).\nD refutes: R2\n")
        self.ri("round", self.R, "Q01", "--open")
        self.accept_with_assumption("Q01.R3")  # a fallback with an open assumption still goes to RENEW
        self.assertIn("events pending: rung-accepted Q01 (E1) -> dispatch investigator RENEW", self.status())
        self.ri("event", self.R, "--handled", "E1", "--by", self.task("investigator", "RENEW"))
        c2 = self.accept_with_assumption("Q01.R2")  # the target rung
        out = self.status()
        self.assertNotIn("dispatch investigator RENEW", out)
        self.assertIn(f"Q01 focused, R2 accepted ({c2}; target R2): no RENEW for E2 rung-accepted; consolidate Q01.R2 "
                      f"({c2}): copy {c2} to reports/Q01-R2-proof-{c2}.md now (proof-lane.md sec. 6); writer --cand "
                      f"{c2} (no comparator) with a skeptic CLAIM-GATE in parallel -> verifier PAPER, after at most 2 "
                      "more rounds on the optional stronger rungs; then event --handled E2 --by <comparator or writer "
                      "task>", out)
        cmp_ = self.task("comparator")
        self.ri("event", self.R, "--handled", "E2", "--by", cmp_)
        self.assertEqual(self.state()["events"][1]["handled_by"], cmp_)
        c1 = self.accepted("Q01.R1")
        out = self.status()
        self.assertNotIn("dispatch investigator RENEW", out)
        self.assertIn(f"Q01 focused, R1 accepted ({c1}; target R2): no RENEW for E3 top-accepted; consolidate "
                      f"Q01.R1 ({c1}): copy {c1} to reports/Q01-R1-proof-{c1}.md now (proof-lane.md sec. 6); writer "
                      f"--cand {c1} (no comparator) with a skeptic CLAIM-GATE in parallel -> verifier PAPER; then "
                      "event --handled E3 --by", out)
        self.ri("q", "set", self.R, "Q01", "--status", "resolved")
        self.assertIn("Q01 focused, resolved: no RENEW for E3 top-accepted", self.status())
        st = self.state()
        st["questions"]["Q01"].update(status="active", rung="R3")
        self.path("lanes", "Q01", "statement.md").write_text("no D line\n", encoding="utf-8")
        self.assertIn("target R3", ri.focused_end(self.R, st, "Q01"))  # without the line: the lane's rung

    def test_q4_focused_refuted_target_gets_a_reading_renew_first(self):
        self.focused("R1")
        self.ri("round", self.R, "Q01", "--open")
        ce = self.accepted_ce("Q01.R1")
        self.ri("exclude", self.R, "--claim", "Q01.R1", "--cand", ce)
        out = self.status()
        self.assertIn("events pending: refuted Q01 (E1) -> dispatch investigator RENEW (batch; focused: limited, "
                      "READING first for a refutation, program.md sec. 3)", out)
        self.assertNotIn("Q01 focused, target R1 excluded", out)  # consolidation only after READING (K-READING)
        self.assertIn("E1 refuted Q01", out)
        self.assertIn("-> first: focused: one limited RENEW applies READING first", out)

    def test_q4_focused_lane_budget_consolidates_instead_of_renew(self):
        self.focused("R1")
        self.ri("q", "set", self.R, "Q01", "--budget", "1")
        self.ri("round", self.R, "Q01", "--open")
        self.ri("event", self.R, "--type", "lane-budget", "--lane", "Q01")
        out = self.status()
        self.assertNotIn("dispatch investigator RENEW", out)
        self.assertIn("Q01 HELD by E1 (lane-budget) until consolidation (no new round)", out)
        self.assertIn("Q01 focused, lane budget reached: no RENEW for E1 lane-budget; no accepted rung: a failure "
                      "report from the record; then event --handled E1 --by <the task that writes it>", out)
        c = self.accept_with_assumption("Q01.R2")  # a fallback rung after the budget: still consolidation
        self.assertIn(f"Q01 focused, lane budget reached: no RENEW for E1 lane-budget; consolidate Q01.R2 ({c}): "
                      f"copy {c} to reports/Q01-R2-proof-{c}.md now (proof-lane.md sec. 6); writer --cand {c} (no "
                      "comparator) with a skeptic CLAIM-GATE in parallel -> verifier PAPER; then event --handled E1 "
                      "--by <comparator or writer task>", self.status())
        self.ri("q", "set", self.R, "Q01", "--status", "parked")
        self.ri("init", str(Path(self.tmp.name, "p")), "--objective", "x")  # program mode keeps RENEW
        self.R = str(Path(self.tmp.name, "p"))
        self.ri("q", "add", self.R, "--title", "t")
        self.ri("q", "set", self.R, "Q01", "--status", "active")
        self.ri("event", self.R, "--type", "lane-budget", "--lane", "Q01")
        self.selected()
        out = self.status()
        self.assertIn("Q01 HELD by E1 (lane-budget) until RENEW (no new round)", out)
        self.assertIn("dispatch investigator RENEW", out)

    def test_q5_advisor_due_skips_ended_lanes_and_reads_the_last_analysis(self):
        self.failed_round()
        due = "process advisor due (reviews since the last advisor task): Q01 r1"
        self.assertIn(due, self.status())
        for s in ("parked", "resolved", "refuted", "killed"):
            self.ri("q", "set", self.R, "Q01", "--status", s)
            self.assertNotIn("process advisor due", self.status(), s)
        self.ri("q", "set", self.R, "Q01", "--status", "active")
        self.assertIn(due, self.status())
        adv1 = self.task("process-advisor")
        self.write(f"tasks/{adv1}/advisor-log.md", "patterns")
        self.ri("task", "set", self.R, adv1, "done")
        self.assertNotIn("process advisor due", self.status())
        self.ri("round", self.R, "Q01", "--open")
        self.failed_round()
        self.assertIn("process advisor due (reviews since the last advisor task): Q01 r2", self.status())
        adv2 = self.task("process-advisor")
        self.write(f"tasks/{adv2}/advisor-log.md", "half")
        self.ri("task", "set", self.R, adv2, "cancelled")
        self.assertIn("process advisor due (reviews since the last advisor task): Q01 r2", self.status())
        adv3 = self.task("process-advisor")
        self.ri("task", "set", self.R, adv3, "done")  # done, but no advisor-log.md
        a = self.assignment(self.ri("task", "new", self.R, "--role", "process-advisor").split()[0])
        self.assertIn(f"- tasks/{adv1}/advisor-log.md (your previous advisor log)", a)
        self.assertIn(f"since advisor task {adv1}", a)
        self.assertNotIn(adv2, a)
        self.assertNotIn(adv3, a)
        self.accepted("Q01.R1")  # the round that ends the lane
        st = self.state()
        for t in st["tasks"].values():
            t["status"] = "done" if t["status"] in ri.LIVE else t["status"]
        self.assertTrue(ri.lane_over(st, "Q01"))
        self.assertEqual(ri.advisor_due(st), [])

    def test_q6_return_line_only_when_missing(self):
        w = self.ri("task", "new", self.R, "--role", "writer", "--extra", "Write the paper from C001.").split()[0]
        self.assertEqual(self.assignment(w).splitlines()[-3:],
                         [ri.RETURN_DEFAULT, ri.time_line("writer"), f"Stop condition: {ri.STOP_DEFAULT['writer']}."])
        w2 = self.ri("task", "new", self.R, "--role", "writer", "--extra", "Write it.",
                     "--extra", "Return: manuscript.md only.").split()[0]
        self.assertNotIn(ri.RETURN_DEFAULT, self.assignment(w2))
        c = self.cand(self.task("prover", "PROVE", lane="Q01"), "Q01.R1")
        v = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "INDIVIDUAL", "--cand", c).split()[0]
        self.assertEqual(sum(x.startswith("Return") for x in self.assignment(v).splitlines()), 1)

    def test_q7_one_isolated_task_covers_several_candidates(self):
        src = self.cand(self.task("prover", "PROVE", lane="Q01"), "Q01.R2")
        aud = self.task("ledger-auditor", lane="Q01")
        f1 = self.cand(aud, None, "--from", src, text="# Lemma A (fragment)\nFor all n >= 1, A.\n")
        f2 = self.cand(aud, None, "--from", src, text="# Lemma B (fragment)\nFor all n >= 1, B.\n")
        tr = self.cand(self.task("literature-reviewer", "TRANSFER-AUDIT"), "transfer:S03 Thm 2@M1", "--kind", "transfer")
        iso = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "ISOLATED", "--cand", f"{f1},{f2},{tr}",
                      "--start").split()[0]
        a = self.assignment(iso)
        for needle in (f"- candidates/{f1}.md (fragment)", f"- candidates/{f2}.md (fragment)",
                       f"- candidates/{tr}.md (transfer)", "for each transfer", "one `review Cxxx:` line per candidate"):
            self.assertIn(needle, a)
        self.assertNotIn(src, a)
        self.write(f"tasks/{iso}/review.md", "three blocks")
        self.result(iso, "scope: ISOLATED", f"review {f1}: verdict=PASS", f"review {f2}: verdict=FAIL",
                    f"blocking {f2}: O1 CRITICAL: Lemma B [HYP] - needs n even",
                    f"review {tr}: verdict=PASS; fidelity=MATCH", "artifacts: [review.md]")
        out = self.ri("ingest", self.R, iso, "--accept")
        rep = f"tasks/{iso}/review.md"
        self.assertEqual([(r["cand"], r["scope"], r["verdict"], r["report"]) for r in self.state()["reviews"]],
                         [(f1, "isolated", "PASS", rep), (f2, "isolated", "FAIL", rep), (tr, "isolated", "PASS", rep)])
        self.assertIn(f"accepted: {f1} accepted", out)
        self.assertIn(f"accepted: {tr} accepted", out)
        self.assertNotIn(f"accepted: {f2}", out)


class TestV62ProgramRunFixes(RiCase):
    """Fixes from a 40-task program-mode run (v6.2 final)."""

    REFUSED = ("report.md", "analysis.md", "summary.md", "findings.md")  # names a host's subagents may not write

    def setUp(self):
        super().setUp()
        self.init()
        self.q = self.lane()

    def test_p1_default_outputs_avoid_host_refused_names(self):
        p = self.task("prover", "PROVE", lane="Q01")
        c = self.cand(p, "Q01.R1")
        self.review(c, self.task("verifier", "INDIVIDUAL", lane="Q01"), "individual", "PASS", "--confirmed", "Lemma 1")
        self.r1()
        tids = [self.ri("task", "new", self.R, *args).split()[0] for args in (
            ("--role", "verifier", "--mode", "CROSS-DRAFT", "--cand", c),
            ("--role", "summarizer", "--direction", "PROVE Q01.R1"),
            ("--role", "prover", "--direction", "PROVE Q01.R1"),
            ("--role", "scout", "--mode", "SANITY", "--cand", c),
            ("--role", "ledger-auditor", "--lane", "Q01", "--round", "1"),
            ("--role", "process-advisor"),
            ("--role", "investigator", "--mode", "RENEW"),
            ("--role", "skeptic", "--mode", "QUESTION-GATE", "--question", "Q01"))]
        texts = list(ri.STOP_DEFAULT.values()) + [ri.RETURN_DEFAULT] + [self.assignment(t) for t in tids]
        for text in texts:
            for name in self.REFUSED:
                self.assertNotIn(name, text)
        self.assertIn("Return: advisor-log.md, result.md", self.assignment(tids[5]))
        self.assertTrue(ri.STOP_DEFAULT["process-advisor"].startswith("advisor-log.md and result.md"))
        old = self.task("process-advisor")
        self.write(f"tasks/{old}/analysis.md", "pre-6.2 log")  # the legacy name is still read
        self.ri("task", "set", self.R, old, "done")
        a = self.assignment(self.ri("task", "new", self.R, "--role", "process-advisor").split()[0])
        self.assertIn(f"- tasks/{old}/analysis.md (your previous advisor log)", a)
        new = self.task("process-advisor")
        self.write(f"tasks/{new}/advisor-log.md", "log")
        self.ri("task", "set", self.R, new, "done")
        a = self.assignment(self.ri("task", "new", self.R, "--role", "process-advisor").split()[0])
        self.assertIn(f"- tasks/{new}/advisor-log.md (your previous advisor log)", a)
        self.assertNotIn(f"tasks/{old}/", a)

    def test_p2_extended_length_form(self):
        short = Path(self.tmp.name, "a.md")
        self.assertEqual(ri.xp(short), short)
        deep = self.tmp.name.replace("\\", "/") + "/" + "/".join(["d" * 50] * 5) + "/a.md"
        got = str(ri.xp(deep))
        if os.name == "nt":
            self.assertTrue(got.startswith("\\\\?\\"))
            self.assertEqual(got[4:], os.path.abspath(deep))
            self.assertNotIn("/", got)
            self.assertEqual(str(ri.xp(got)), got)
            self.assertTrue(str(ri.xp("//server/share/" + "d" * 250)).startswith("\\\\?\\UNC\\server\\share\\"))
        else:
            self.assertEqual(got, deep)

    def test_p2_run_directory_beyond_260_characters(self):
        run = Path(self.tmp.name)
        while len(str(run)) < 270:
            run = run / ("deep-" + "x" * 40)
        run = run / "run"
        try:
            ri.xp(run.parent).mkdir(parents=True)
        except OSError as e:
            self.skipTest(f"the OS refuses long paths even in the extended-length form: {e}")
        self.R = str(run)
        out = self.ri("init", self.R, "--objective", "a deep run")
        self.assertIn(f"initialised {self.R}", out)
        self.lane()
        c = self.accepted("Q01.R2")  # packets, cand add copy, reviews, accept, record.md, ledger.md
        self.ri("ledger", "add", self.R, "--cand", c)
        out = self.ri("task", "new", self.R, "--role", "prover", "--direction", "PROVE Q01.R1", "--start")
        p = out.split()[0]
        self.assertIn(os.path.join(self.R, "tasks", p, "packet.md"), out)  # printed in the normal form
        self.write(f"tasks/{p}/draft.md", "# Draft\n## Theorem\nR1 holds.\n")
        self.write(f"tasks/{p}/notes.md", "side notes")
        self.result(p, "direction: PROVE Q01.R1", "claims: Q01.R1", "kind: proof", "gaps: none")
        self.assertIn("C002 frozen  Q01.R1", self.ri("ingest", self.R, p))
        self.assertEqual(self.state()["candidates"]["C002"]["path"], "candidates/C002.md")
        arc = Path(self.tmp.name, "b.zip")
        with zipfile.ZipFile(arc, "w") as z:
            z.writestr("bundle/README.md", "my idea")
            z.writestr("bundle/papers/" + "long-name-" * 6 + ".pdf", b"%PDF")
        out = self.ri("intake", self.R, "--archive", arc)
        self.assertIn("2 files into sources/raw/", out)
        self.assertIn("rejected 0", out)
        self.assertTrue(ri.xp(self.path("sources", "raw", "bundle", "README.md")).is_file())
        self.ri("pause", self.R, "--reason", "hold")
        self.assertIn("PAUSE YES", self.status())
        self.ri("resume", self.R)
        out = self.status("--full")
        self.assertIn("PAUSE no", out)
        self.assertNotIn("\\\\?\\", out)
        self.assertIn("check OK", self.ri("check", self.R))
        self.assertFalse(ri.xp(self.path(".ri.lock")).exists())
        for name in ("lanes/Q01/record.md", "ledger.md", "checkpoint.md", f"tasks/{p}/packet.md"):
            self.assertGreater(len(os.path.join(self.R, name)), 260)
            self.assertTrue(ri.xp(self.path(*name.split("/"))).is_file(), name)

    def test_p2_intake_budget_rejects_only_absurd_lengths(self):
        arc = Path(self.tmp.name, "long.zip")
        absurd = "bundle/" + "/".join(["d" * 200] * 5) + "/f.txt"  # over 1000 characters
        with zipfile.ZipFile(arc, "w") as z:
            z.writestr(absurd, "deep")
            z.writestr("bundle/" + "n" * 300 + ".md", "a name over the 255-character limit")
            z.writestr("bundle/" + "/".join(["m" * 60] * 3) + "/ok.md", "kept as is")
        out = self.ri("intake", self.R, "--archive", arc)
        self.assertIn("rejected 0", out)
        self.assertIn(f"renamed: {absurd} -> sources/raw/S01-f.txt", out)
        self.assertIn("-> sources/raw/S02-" + "n" * 57 + ".md", out)
        self.assertTrue(ri.xp(self.path("sources", "raw", "bundle", *(["m" * 60] * 3), "ok.md")).is_file())
        with mock.patch.object(ri, "PATH_BUDGET", len(os.path.join(self.R, "sources", "raw")) + 5):
            out = self.ri("intake", self.R, "--archive", arc)
        self.assertIn("path too long even when shortened", out)

    def test_p2_relative_run_becomes_absolute(self):
        cwd = os.getcwd()
        os.chdir(self.tmp.name)
        try:
            self.ri("init", os.path.join("rel", "run"), "--objective", "x")
            out = self.ri("task", "new", os.path.join("rel", "run"), "--role", "scout", "--extra", "x")
            os.chdir(os.path.join("rel", "run"))
            self.ri("q", "add", ".", "--title", "from inside the run")
            self.assertIn("check OK", self.ri("check", "."))
        finally:
            os.chdir(cwd)
        full = os.path.join(os.path.abspath(self.tmp.name), "rel", "run")
        self.assertIn(os.path.join(full, "tasks", "T001", "packet.md"), out)
        self.assertIn(f"run_dir:    {full}", Path(full, "contract.md").read_text(encoding="utf-8"))
        self.assertIn(f"Run: {full}", Path(full, "tasks", "T001", "packet.md").read_text(encoding="utf-8"))
        self.assertEqual(json.loads(Path(full, "state.json").read_text(encoding="utf-8"))["counters"]["Q"], 1)

    def test_p3_intake_types_user_notes_by_name(self):
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w") as z:
            z.writestr("x.txt", "inside")
        arc = Path(self.tmp.name, "mix.zip")
        names = {"README.md": "user-notes", "notes-on-X.txt": "user-notes", "Plan.md": "user-notes",
                 "my_notes.md": "user-notes", "TODO.txt": "user-notes", "direction.md": "user-notes",
                 "QUESTIONS.txt": "user-notes", "brief.md": "user-notes", "ideas.md": "user-notes",
                 "field-notes.pdf": "user-notes", "transcript.md": "user-notes", "summary-of-lit.txt": "text",
                 "2301.12345.txt": "text", "notes-on-paper.md": "text", "plan.py": "code",
                 "planar-graphs.pdf": "paper-pdf", "ideal-lattices.pdf": "paper-pdf", "plans.md": "user-notes",
                 "sub/notes.md": "notes", "sub/plan.md": "notes", "notes.zip": "archive", "notes.zip:x.txt": "notes"}
        with zipfile.ZipFile(arc, "w") as z:
            for n in names:
                if ":" not in n:
                    z.writestr(n, inner.getvalue() if n.endswith(".zip") else "text")
        out = self.ri("intake", self.R, "--archive", arc)
        idx = self.path("sources", "index.md").read_text(encoding="utf-8")
        got = {r.split("|")[2].strip(): r.split("|")[4].strip() for r in idx.splitlines() if re.match(r"\| S\d+ ", r)}
        self.assertEqual(got, names)
        line = next(x for x in out.splitlines() if x.startswith("user-notes (read in full"))
        self.assertIn("sources/raw/README.md", line)
        self.assertIn("sources/raw/transcript.md", line)  # v6.3 (K28): a transcript states intent
        self.assertNotIn("summary-of-lit.txt", line)
        self.assertNotIn("sub/", line)

    def test_p4_live_sanity_check_holds_acceptance(self):
        p = self.task("prover", "PROVE", lane="Q01")
        c = self.cand(p, "Q01.R1")
        s = self.ri("task", "new", self.R, "--role", "scout", "--mode", "SANITY", "--cand", c, "--start").split()[0]
        w = self.ri("task", "new", self.R, "--role", "scout", "--mode", "WITNESS", "--cand", c).split()[0]  # queued
        self.review(c, self.task("verifier", "INDIVIDUAL", lane="Q01"), "individual", "PASS")
        x = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "CROSS-DRAFT", "--cand", c, "--start").split()[0]
        self.result(x, "scope: CROSS-DRAFT", f"review {c}: verdict=PASS; fidelity=MATCH")
        out = self.ri("ingest", self.R, x, "--accept")
        self.assertNotIn(f"accepted: {c}", out)
        self.assertEqual(self.state()["candidates"][c]["status"], "proposed")
        out = self.ri("accept", self.R, c, code=1)
        self.assertIn(f"sanity check {s} still running", out)
        self.assertIn(f"witness check {w} still running", out)
        self.ri("task", "set", self.R, w, "cancelled")
        self.assertIn(f"{c}: reviews pass but sanity check {s} still running - accept after it returns", self.status())
        self.result(s, "mode: SANITY", f"check {c}: outcome=consistent; exact=yes")
        self.assertIn(f"accepted: {c} accepted", self.ri("ingest", self.R, s, "--accept"))
        self.ri("task", "new", self.R, "--role", "scout", "--mode", "SANITY", "--cand", c)  # after acceptance: no hold
        self.assertNotIn("gate now fails", self.status())
        self.assertIn("check OK", self.ri("check", self.R))

    def test_p5_light_question_gate(self):
        self.r1()
        qg = self.ri("task", "new", self.R, "--role", "skeptic", "--mode", "QUESTION-GATE", "--question", "Q01",
                     "--light").split()[0]
        a = self.assignment(qg)
        self.assertEqual(a.count("Light gate: run checks 1-3b only."), 1)
        self.assertLess(a.index("Light gate"), a.index("Return: gate.md"))
        self.assertTrue(self.state()["tasks"][qg]["light"])
        full = self.ri("task", "new", self.R, "--role", "skeptic", "--mode", "QUESTION-GATE", "--question", "Q01").split()[0]
        self.assertNotIn("Light gate", self.assignment(full))
        redo = self.ri("task", "new", self.R, "--redo", qg).split()[0]
        self.assertEqual(self.assignment(redo).count("Light gate"), 1)
        for bad in (("--role", "skeptic", "--mode", "CLAIM-GATE"), ("--role", "skeptic"),
                    ("--role", "verifier", "--mode", "INDIVIDUAL")):
            self.assertIn("--light is only for a skeptic QUESTION-GATE, or a MODEL-GATE with --question",
                          self.ri("task", "new", self.R, *bad, "--light", "--extra", "x", code=2))
        self.assertEqual(self.state()["counters"]["T"], 3)

    def test_p6_handled_by_any_task_and_the_milestone_leaves_status(self):
        self.ri("event", self.R, "--type", "milestone", "--note", "H1 complete")
        self.ri("event", self.R, "--type", "queue-low")
        self.ri("event", self.R, "--type", "milestone", "--note", "the user asked")
        out = self.status("--full")
        self.assertIn("E1 milestone", out)
        self.assertIn("E3 milestone", out)
        cmp_, wr, sel = self.task("comparator"), self.task("writer"), self.task("investigator", "SELECT")
        self.assertIn(f"handled by {cmp_}: E1", self.ri("event", self.R, "--handled", "E1", "--by", cmp_))
        self.ri("event", self.R, "--handled", "E3", "--by", wr)
        self.ri("event", self.R, "--handled", "E2", "--by", sel)
        out = self.status("--full")
        self.assertNotIn("E1 milestone", out)
        self.assertNotIn("E3 milestone", out)
        self.assertNotIn("(E1)", out)
        self.assertIn("events pending 0", out)
        self.assertEqual([e["handled_by"] for e in self.state()["events"]], [cmp_, sel, wr])
        self.assertIn("the task that handled the events", self.ri("event", self.R, "--handled", "E1", code=2))
        self.ri("event", self.R, "--handled", "E1", "--by", "T099", code=2)
        self.assertIn("the task that handled the events", " ".join(self.ri("event", self.R, "-h").split()))
        self.assertIn("check OK", self.ri("check", self.R))


if __name__ == "__main__":
    unittest.main()
