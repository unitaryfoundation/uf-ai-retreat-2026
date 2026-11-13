"""v6.4: a focused run continues after its delivery as a research program (init --after, ri.py mode, the
continuation opening of program.md sec. 2.1), and TIGHTNESS is class-wide first (scripts/ri.py).

Run:  python -B -m unittest discover -s tests -v     (from the skill directory)
"""
import json
import shutil
import unittest
from pathlib import Path

from test_ri import SCRIPT, RiCase, ri

CONVERT = "mode RUN --to program --reason-file <file> (program.md sec. 3)"
CONT = "continuation from focused delivery (program.md sec. 2.1): "


class ContinuationCase(RiCase):
    def focused(self, *extra, rung="R1"):
        self.R = str(Path(self.tmp.name, "f"))
        self.ri("init", self.R, "--objective", "Prove only this claim", "--mode", "focused", *extra)
        self.ri("q", "add", self.R, "--title", "claim", "--model", "M1")
        self.ri("q", "set", self.R, "Q01", "--status", "active", "--rung", rung)
        self.ri("round", self.R, "Q01", "--open")

    def deliver(self, stronger=False):
        """Q01.R1 accepted, the lane resolved, a manuscript passed PAPER, and E1 handled by the writer."""
        if stronger:
            self.write("lanes/Q01/statement.md", "Goal. Prove or disprove: R1.\nStronger (after R1):\n"
                                                 "- no mechanism in the class beats it\n")
        c = self.accepted("Q01.R1")
        self.ri("ledger", "add", self.R, "--cand", c)
        self.ri("q", "set", self.R, "Q01", "--status", "resolved")
        w = self.task("writer", extra=("--cand", c))
        self.write(f"tasks/{w}/manuscript.md", "# Manuscript\nThe theorem and its proof.\n")
        m = self.ri("cand", "add", self.R, "--lane", "Q01", "--claims", "Q01.R1", "--kind", "manuscript",
                    "--file", f"tasks/{w}/manuscript.md", "--author", w).split()[0]
        pv = self.task("verifier", "PAPER")
        self.review(m, pv, "paper", "PASS")
        self.ri("accept", self.R, m)
        self.ri("event", self.R, "--handled", "E1", "--by", w)
        T = self.state()["tasks"]
        self.ri("task", "set", self.R, *sorted(T), "done")
        return c, m

    def convert(self):
        return self.ri("mode", self.R, "--to", "program", "--reason", "contract: after delivery, continue")

    def actions(self, out):
        return out.split("SUGGESTED NEXT ACTIONS:\n")[1]


class TestInitAfter(ContinuationCase):
    def test_continuation_is_in_scope_and_not_optional(self):
        # A v6.4 parity run scoped the contract to the single inequality, called the continuation optional and
        # ended its turn at a "turn limit" right after delivery.
        self.ri("init", self.R, "--objective", "Show that f >= g.", "--mode", "focused")
        contract = self.path("contract.md").read_text(encoding="utf-8")
        self.assertIn("- In scope: the claim; after its delivery, research questions built on the delivered result",
                      contract)
        stop_run = str(Path(self.tmp.name, "stop"))
        self.ri("init", stop_run, "--objective", "Prove only this claim: f >= g.", "--mode", "focused",
                "--after", "stop", "--stop-quote", "Prove only this claim")
        self.assertIn("- In scope: <models, regimes, problem family>",
                      Path(stop_run, "contract.md").read_text(encoding="utf-8"))
        self.ri("q", "add", self.R, "--title", "claim")
        out = self.ri("mode", self.R, "--to", "program", "--reason", "After delivery: continue")
        self.assertIn("not optional work", out)
        self.assertIn("the run is not finished", out)
        self.assertIn("do not end the turn", out)
        contract = self.path("contract.md").read_text(encoding="utf-8")
        scope = contract.split("## Scope boundaries")[1].split("\n## ")[0]
        self.assertIn("- Continuation (from ", scope)

    def test_init_default_is_continue(self):
        out = self.ri("init", self.R, "--objective", "claim", "--mode", "focused")
        self.assertIn("(mode focused, after delivery: continue, isolation L2", out)
        self.assertEqual(self.state()["after"], "continue")
        contract = self.path("contract.md").read_text(encoding="utf-8")
        self.assertIn("## Mode\nfocused - reason: <why this mode>\nAfter delivery: continue - the default: once the "
                      "claim's result is delivered", contract)
        self.assertEqual(ri.after_delivery(self.state()), "continue")

    def test_init_after_stop(self):
        out = self.ri("init", self.R, "--objective", "prove only this claim", "--mode", "focused", "--after", "stop",
                      "--stop-quote", "prove only this claim")
        self.assertIn("after delivery: stop", out)
        self.assertNotIn("warning", out)
        self.assertEqual(self.state()["after"], "stop")
        self.assertEqual(self.state()["after_quote"], "prove only this claim")
        self.assertIn('After delivery: stop - the user\'s words: "prove only this claim"',
                      self.path("contract.md").read_text(encoding="utf-8"))
        self.assertIn("args", json.loads(self.path("log.jsonl").read_text(encoding="utf-8").splitlines()[0]))

    def test_after_stop_needs_the_users_limiting_words(self):
        # "Show that X" is a request to prove X, not to stop after it (a v6.4 parity run read it as a stop).
        out = self.ri("init", self.R, "--objective", "claim", "--mode", "focused", "--after", "stop", code=2)
        self.assertIn("needs --stop-quote", out)
        self.assertIn("'show that'", out)
        self.assertFalse(self.path("state.json").exists())
        ask = "Show that f(n) >= g(n) for all n >= 1. The paper above is the only reference."
        out = self.ri("init", self.R, "--objective", ask, "--mode", "focused", "--after", "stop",
                      "--stop-quote", "Show that f(n) >= g(n) for all n >= 1", code=2)
        self.assertIn("contains no phrase that limits the run", out)
        out = self.ri("init", self.R, "--objective", ask, "--mode", "focused", "--after", "stop",
                      "--stop-quote", "the paper above is the only reference", code=2)
        self.assertIn("contains no phrase that limits the run", out)
        out = self.ri("init", self.R, "--objective", ask, "--mode", "focused", "--after", "stop",
                      "--stop-quote", ask, code=2)   # 69 characters but not a limiting phrase
        self.assertIn("contains no phrase", out)
        out = self.ri("init", self.R, "--objective", ask, "--mode", "focused", "--after", "stop",
                      "--stop-quote", "prove only this claim", code=2)   # not in the user's words
        self.assertIn("copied from the Objective", out)
        self.assertFalse(self.path("state.json").exists())

    def test_stop_quote_accepts_real_limits(self):
        for ask, quote in (("Prove only this claim: f >= g.", "Prove only this claim"),
                           ("Show f >= g, then stop.", "then stop"),
                           ("Just prove that f >= g and nothing else.", "Just prove"),
                           ("Settle f >= g; no further research please.", "no further research")):
            with self.subTest(quote=quote):
                shutil.rmtree(self.R, ignore_errors=True)
                self.ri("init", self.R, "--objective", ask, "--mode", "focused", "--after", "stop", "--stop-quote", quote)
                self.assertEqual(self.state()["after"], "stop")

    def test_stop_quote_only_with_focused_stop(self):
        out = self.ri("init", self.R, "--objective", "claim", "--mode", "focused", "--stop-quote", "only this", code=2)
        self.assertIn("--stop-quote goes only with --mode focused --after stop", out)
        self.assertFalse(self.path("state.json").exists())

    def test_program_init_has_no_after_line_and_bad_choice_is_a_usage_error(self):
        out = self.ri("init", self.R, "--objective", "explore")
        self.assertNotIn("after delivery", out)
        contract = self.path("contract.md").read_text(encoding="utf-8")
        self.assertIn("## Mode\nprogram - reason: <why this mode>\n\n## Scope boundaries", contract)
        self.ri("init", str(Path(self.tmp.name, "g")), "--objective", "x", "--mode", "focused", "--after", "later",
                code=2)

    def test_run_without_the_key_acts_as_stop(self):
        self.focused()
        st = self.state()
        del st["after"]
        self.save(st)
        self.assertEqual(ri.after_delivery(self.state()), "stop")
        self.write("lanes/Q01/statement.md", "Goal. Prove or disprove: R1.\nStronger (after R1):\n- R1 for every n\n")
        self.accepted("Q01.R1")
        out = self.status()
        self.assertIn("after the 'Stronger (after R1)' items run as a new question (q add, R1 = the first item; "
                      "light-gate it; q set --budget <rounds used + 2>; SKILL.md sec. 5 focused step 4)", out)
        self.assertNotIn("--to program", out)
        self.assertIn("check OK", self.ri("check", self.R))


class TestFocusedEndings(ContinuationCase):
    def test_continue_target_rung_consolidates_at_once(self):
        self.focused(rung="R2")
        self.write("lanes/Q01/statement.md", "Goal. R1 (optional), R2 (target rung), R3 (fallback).\nD refutes: R2\n")
        c2 = self.accepted("Q01.R2")
        out = self.status()
        self.assertIn(f"Q01 focused, R2 accepted ({c2}; target R2): no RENEW for E1 rung-accepted; consolidate Q01.R2 "
                      f"({c2}): copy {c2} to reports/Q01-R2-proof-{c2}.md now (proof-lane.md sec. 6); writer --cand "
                      f"{c2} (no comparator) with a skeptic CLAIM-GATE in parallel -> verifier PAPER, now (no more "
                      "rounds: once in-flight work finishes, q set Q01 --status resolved --rung R2; its stronger rungs "
                      "go to the program); then event --handled E1 --by <comparator or writer task>; after delivery "
                      "(PAPER passed, or the report delivered): say in progress.md sec. 1 that the result is "
                      f"delivered and the run continues as a research program built on it; then {CONVERT}", out)
        self.assertIn(f"Q01: R2 accepted ({c2}; target R2) - no more rounds before the delivery (after delivery: "
                      "continue): let live tasks finish", out)
        for absent in ("2 more rounds", "--budget", "plan round 2"):
            self.assertNotIn(absent, out)

    def test_continue_stronger_items_wait_for_the_program(self):
        self.focused()
        self.write("lanes/Q01/statement.md", "Goal. Prove or disprove: R1.\nStronger (after R1):\n- R1 for every n\n")
        c = self.accepted("Q01.R1")
        out = self.status()
        self.assertIn(f"consolidate Q01.R1 ({c}): copy", out)
        self.assertIn("-> verifier PAPER; the 'Stronger (after R1)' items go to the continuation RENEW by path (no new "
                      "question now); then event --handled E1 --by <comparator or writer task>; after delivery", out)
        self.assertIn(CONVERT, out)
        for absent in ("q add, R1 = the first item", "--budget", "2 more rounds"):
            self.assertNotIn(absent, out)

    def test_stop_keeps_the_v63_hints(self):
        self.focused("--after", "stop", "--stop-quote", "only this claim", rung="R2")
        self.write("lanes/Q01/statement.md", "Goal. R1 (optional), R2 (target rung), R3 (fallback).\nD refutes: R2\n")
        c2 = self.accepted("Q01.R2")
        out = self.status()
        self.assertIn(f"-> verifier PAPER, after at most 2 more rounds on the optional stronger rungs; then event "
                      f"--handled E1 --by <comparator or writer task>", out)
        self.assertNotIn("--to program", out)
        self.assertNotIn("no more rounds before the delivery", out)
        self.assertIn("Q01 r1", out)  # the lane goes on to its stronger rungs
        self.assertIn(c2, out)

    def test_failure_report_names_the_conversion(self):
        self.focused()
        self.ri("q", "set", self.R, "Q01", "--budget", "1")
        self.ri("event", self.R, "--type", "lane-budget", "--lane", "Q01")
        self.assertIn("no accepted rung: a failure report from the record; then event --handled E1 --by <the task "
                      f"that writes it>; after delivery (PAPER passed, or the report delivered)", self.status())
        self.assertIn(CONVERT, self.status())
        w = self.task("writer")
        self.ri("event", self.R, "--handled", "E1", "--by", w)
        self.ri("task", "set", self.R, w, "done")
        self.ri("q", "set", self.R, "Q01", "--status", "parked")
        out = self.status()
        self.assertIn("nothing runnable: a failure report from the record; after delivery", out)
        self.assertIn(CONVERT, out)

    def test_delivered_line_names_the_conversion_only_with_continue(self):
        self.focused()
        _, m = self.deliver()
        out = self.status()
        self.assertIn(f"Q01 delivered ({m} passed PAPER; after delivery: continue): say in progress.md sec. 1 that the "
                      f"result is delivered and the run continues as a research program built on it; then {CONVERT}", out)
        brief = self.status("--brief")
        self.assertIn(f"Q01 delivered ({m} passed PAPER; after delivery: continue): say in", brief)
        self.assertIn("then mode RUN --to program", brief)  # within the brief cut
        self.R = str(Path(self.tmp.name, "s"))
        self.ri("init", self.R, "--objective", "prove only this claim", "--mode", "focused", "--after", "stop",
                      "--stop-quote", "prove only this claim")
        self.ri("q", "add", self.R, "--title", "claim")
        self.ri("q", "set", self.R, "Q01", "--status", "active")
        self.ri("round", self.R, "Q01", "--open")
        _, m = self.deliver()
        out = self.status()
        self.assertIn(f"Q01 delivered ({m} passed PAPER; after delivery: stop): the run ends (program.md sec. 3): "
                      "final progress.md and checkpoint", out)
        for absent in ("--to program", "nothing runnable", "consolidate Q01's strongest"):
            self.assertNotIn(absent, out)


class TestModeCommand(ContinuationCase):
    def test_mode_converts_and_keeps_every_record(self):
        self.focused()
        self.deliver(stronger=True)
        before = self.state()
        self.assertTrue(before["ledger"] and before["questions"] and before["candidates"] and before["events"])
        out = self.convert()
        self.assertIn("mode focused -> program (seq ", out)
        self.assertIn("delivered: Q01", out)
        self.assertIn("continuation opening (program.md sec. 2.1)", out)
        st = self.state()
        self.assertEqual(st["mode"], "program")
        self.assertEqual(st["converted"], {"from": "focused", "seq": st["seq"], "question": "Q01",
                                           "lane_rounds": before["counters"]["lane_rounds"]})
        for key in ("questions", "candidates", "ledger", "events", "tasks", "reviews", "counters", "after"):
            self.assertEqual(st[key], before[key], key)
        self.assertEqual(json.loads(self.path("log.jsonl").read_text(encoding="utf-8").splitlines()[-1])["cmd"], "mode")
        contract = self.path("contract.md").read_text(encoding="utf-8")
        mode = contract.split("## Mode\n")[1].split("\n## ")[0]
        self.assertIn("converted to program mode after the delivery of Q01 (program.md sec. 3): contract: after "
                      "delivery, continue", mode)
        self.assertIn("check OK", self.ri("check", self.R))

    def test_mode_is_refused_under_stop_and_pause(self):
        self.focused()
        self.deliver()
        self.ri("stop", self.R, "--reason", "enough")
        self.assertIn("STOP in force", self.ri("mode", self.R, "--to", "program", "--reason", "x", code=1))
        self.ri("resume", self.R, "--stop", "--reason", "go on")
        self.ri("pause", self.R, "--reason", "hold")
        self.assertIn("PAUSE in force", self.ri("mode", self.R, "--to", "program", "--reason", "x", code=1))
        self.assertEqual(self.state()["mode"], "focused")
        self.ri("resume", self.R)
        self.convert()
        self.assertEqual(self.state()["mode"], "program")

    def test_mode_is_idempotent_and_needs_a_reason(self):
        self.focused()
        self.deliver()
        self.ri("mode", self.R, "--to", "program", code=2)
        self.ri("mode", self.R, "--to", "focused", "--reason", "x", code=2)
        self.convert()
        seq = self.state()["seq"]
        out = self.ri("mode", self.R, "--to", "program")
        self.assertIn("already program mode (converted from focused at seq", out)
        self.assertIn("nothing changed", out)
        self.assertEqual(self.state()["seq"], seq)
        R2 = str(Path(self.tmp.name, "p"))
        self.ri("init", R2, "--objective", "explore")
        self.assertIn("already program mode; nothing changed", self.ri("mode", R2, "--to", "program"))

    def test_mode_notes_a_stop_contract_and_a_live_lane(self):
        self.focused("--after", "stop", "--stop-quote", "only this claim")
        out = self.convert()
        self.assertIn("note: contract.md says 'After delivery: stop' (or the run predates v6.4): convert only on the "
                      "user's words; the reason was appended under contract.md's Mode - make sure it quotes them", out)
        self.assertIn("note: Q01 still active: it runs on as a program lane", out)
        self.assertEqual(self.state()["mode"], "program")


class TestContinuationOpening(ContinuationCase):
    def setUp(self):
        super().setUp()
        self.focused()
        self.deliver(stronger=True)

    def test_status_after_conversion_shows_the_continuation_opening(self):
        st = self.state()
        st["counters"]["lane_rounds"] = 12  # a long focused run: the breadth count restarts at the conversion
        self.save(st)
        self.convert()
        out = self.status()
        self.assertIn("| mode program (from focused, seq ", out)
        self.assertIn(CONT + "investigator RENEW --title continuation on Q01 + LANDSCAPE (none ran; if workers have "
                      "web), then PROPOSE x2-4, then SELECT. The RENEW applies After-ACCEPT (TIGHTNESS first) and "
                      "writes the map grid if missing (MODEL only if the RENEW or a gate asks)", out)
        for absent in ("focused (SKILL.md sec. 5)", "opening (program.md sec. 2)", "Q01 focused", "no prover yet",
                       "foothold", "queue low", "breadth-review", "delivered ("):
            self.assertNotIn(absent, out)
        brief = self.status("--brief")  # status --brief cuts lines at 220 characters: the action comes first
        self.assertIn(CONT + "investigator RENEW --title continuation on Q01 + LANDSCAPE (none ran; if workers have "
                      "web), then PROPOSE x2-4, then SELECT.", brief)

    def test_continuation_without_any_prover_has_no_watchdog(self):
        R2 = str(Path(self.tmp.name, "n"))
        self.R = R2
        self.ri("init", R2, "--objective", "claim", "--mode", "focused")
        self.ri("q", "add", R2, "--title", "claim")
        self.ri("q", "set", R2, "Q01", "--status", "parked", "--note", "failure report delivered")
        self.convert()
        out = self.status()
        self.assertNotIn("no prover yet", out)
        self.assertNotIn("no-prover safeguard", out)
        self.assertIn(CONT + "investigator RENEW --title continuation on Q01 + LANDSCAPE", out)
        self.assertIn("The RENEW applies After-STALL and writes the map grid", out)

    def test_renew_propose_select_then_gates(self):
        self.write("reports/Q01-R1-proof-C001.md", "the accepted proof")
        self.convert()
        r = self.ri("task", "new", self.R, "--role", "investigator", "--mode", "RENEW", "--title", "continuation").split()[0]
        a = self.assignment(r)
        self.assertIn("Request: RENEW on the delivered result Q01 resolved@R1 (C001) (continuation from focused "
                      "delivery, program.md sec. 2.1): apply the After-ACCEPT operators (frontier-method.md sec. 10), "
                      "TIGHTNESS first: the converse for the whole class the result competes in", a)
        self.assertIn("the converse for this specific object is its fallback rung; at most 3 successors", a)
        self.assertIn("(not registered now); SELECT handles pending events.\nIf frontier/map.md has no grid (a focused "
                      "MODEL writes none), write the M1 grid first (investigator.md MODEL step 5, frontier-method.md "
                      "sec. 3) around the delivered result, with its endpoints and transfer rows, and story.md's first "
                      "headline.", a)
        self.assertIn("- questions/Q01.md (the delivered question)\n- lanes/Q01/record.md\n"
                      "- lanes/Q01/statement.md (its 'Stronger (after R1)' items)", a)
        self.assertNotIn("- lanes/Q01/statement.md\n", a)
        self.assertIn("- lanes/Q01/record.md", a)
        self.assertIn("- reports/Q01-R1-proof-C001.md", a)
        land = self.task("literature-reviewer", "LANDSCAPE")
        self.ri("task", "set", self.R, r, land, "running")
        out = self.status()
        self.assertIn(CONT + f"PROPOSE x2-4 once RENEW {r} returns (it writes the map grid), then SELECT", out)
        self.assertNotIn("queue low", out)
        self.write(f"tasks/{r}/new/N1-card.md", "TIGHTNESS card")
        self.write(f"tasks/{r}/renew.md", "renew")
        self.ri("task", "set", self.R, r, "done")
        self.assertIn(CONT + "PROPOSE x2-4 together now (one lens each: OBVIOUS-CONSTRUCTION and ADVERSARY, then "
                      "BARRIER and CURVE/EXTREMES; program.md sec. 5.1), then SELECT", self.status())
        p1 = self.task("investigator", "PROPOSE", title="lens OBVIOUS-CONSTRUCTION")
        p2 = self.task("investigator", "PROPOSE", title="lens ADVERSARY")
        a = self.assignment(p1)  # program.md sec. 2.1: the sweep sees the delivered result and the RENEW's output
        self.assertIn("- lanes/Q01/statement.md\n- reports/Q01-R1-proof-C001.md (delivered)\n- contract.md\n"
                      f"- tasks/{r}/renew.md (the continuation RENEW: successors of the delivered result; propose "
                      "beyond them)", a)
        self.ri("task", "set", self.R, p1, p2, "running")
        self.assertIn(CONT + f"SELECT once {p1}, {p2} return (RENEW {r}'s cards and the sweep's cards.md go to "
                      "it by path)", self.status())
        self.write(f"tasks/{p1}/cards.md", "cards")
        self.ri("task", "set", self.R, p1, p2, "done")
        self.ri("event", self.R, "--type", "literature-hit", "--note", "S04 Thm 2 is related")
        out = self.status()
        self.assertIn(CONT + f"investigator SELECT now (task new --role investigator --mode SELECT --start): RENEW "
                      f"{r}'s successor cards are its first candidates (TIGHTNESS first)", out)
        self.assertIn("events pending: literature-hit (E2) - handled by the continuation SELECT (program.md sec. 2.1; "
                      "the RENEW on the delivered result handles none)", out)
        s = self.ri("task", "new", self.R, "--role", "investigator", "--mode", "SELECT").split()[0]
        a = self.assignment(s)
        self.assertIn("Continuation from focused delivery (program.md sec. 2.1): the RENEW's successors of the "
                      "delivered result are the first candidates, TIGHTNESS first.", a)
        self.assertIn(f"- tasks/{r}/new/ (RENEW {r}: successors of the delivered result; the first candidates)\n"
                      f"- tasks/{r}/renew.md\n- lanes/Q01/statement.md (its 'Stronger (after R1)' items)\n"
                      f"- tasks/{p1}/cards.md (PROPOSE)", a)
        self.assertIn("- E2 literature-hit: S04 Thm 2 is related", a)
        self.ri("task", "set", self.R, s, "running")
        self.assertIn(CONT + f"SELECT {s} running; then register its cards (program.md sec. 4) and QUESTION-GATE them",
                      self.status())
        self.write(f"tasks/{s}/new/N1-card.md", "selected card")
        self.ri("task", "set", self.R, s, "done")
        self.ri("event", self.R, "--handled", "E2", "--by", s)
        out = self.status()
        self.assertIn(CONT + f"register SELECT {s}'s cards now (program.md sec. 4: q add, card and statement), then "
                      "skeptic QUESTION-GATEs on them", out)
        self.assertNotIn("queue low", out)  # the continuation's own next step comes first
        self.ri("q", "add", self.R, "--title", "class-wide converse", "--parent", "Q01", "--operator", "TIGHTNESS")
        self.r1("Q02")
        out = self.status()
        self.assertIn(CONT + f"skeptic QUESTION-GATEs on SELECT {s}'s cards (--question Q02; batching: program.md sec. "
                      "5.2), then open lanes at the ready gate (sec. 6)", out)
        self.assertNotIn("queue low", out)
        g = self.ri("task", "new", self.R, "--role", "skeptic", "--mode", "QUESTION-GATE", "--question", "Q02",
                    "--start").split()[0]
        self.ri("q", "set", self.R, "Q02", "--status", "vetting")
        out = self.status()
        self.assertNotIn("continuation from focused delivery", out)
        self.assertNotIn("opening (program.md sec. 2)", out)
        self.ri("task", "set", self.R, g, "done")
        self.ri("q", "set", self.R, "Q02", "--status", "ready")
        self.assertIn("ready questions Q02: open lanes per the investigator's portfolio", self.status())
        self.ri("q", "set", self.R, "Q02", "--status", "active", "--rung", "R1")
        self.ri("event", self.R, "--type", "stall", "--lane", "Q02")  # later: an ordinary RENEW registers Q03
        r2 = self.task("investigator", "RENEW")
        self.ri("task", "set", self.R, r2, "done")
        self.ri("event", self.R, "--handled", "E3", "--by", r2)
        self.ri("q", "add", self.R, "--title", "successor", "--parent", "Q02", "--operator", "DESCEND")
        self.assertNotIn("continuation from focused delivery", self.status())  # the opening is over for good

    def test_program_hints_after_the_continuation(self):
        self.convert()
        for mode in ("RENEW", "PROPOSE", "SELECT"):
            self.ri("task", "set", self.R, self.task("investigator", mode), "done")
        out = self.status()
        self.assertNotIn("continuation from focused delivery", out)
        self.assertIn("queue low (0 ready + 0 vetting < 2 free lanes): event --type queue-low, then a proposal sweep",
                      out)
        self.ri("event", self.R, "--type", "queue-low")
        self.assertIn("E2 queue-low: proposal sweep with the 2 least-recently used lenses", self.status())
        self.ri("event", self.R, "--type", "top-accepted", "--lane", "Q01", "--note", "test")
        self.assertIn("-> dispatch investigator RENEW (batch), then event --handled", self.status())
        a = self.assignment(self.task("investigator", "RENEW", fill=False))
        self.assertIn("Request: RENEW for events E3: successors", a)  # an ordinary RENEW from now on

    def test_continuation_renew_with_no_card_logs_no_queue_low(self):
        self.convert()
        r = self.ri("task", "new", self.R, "--role", "investigator", "--mode", "RENEW", "--start").split()[0]
        self.result(r, "mode: RENEW", "events_handled: []")
        out = self.ri("ingest", self.R, r)
        self.assertNotIn("RENEW returned no successor", out)

    def test_select_packet_names_a_renew_without_successors(self):
        self.convert()
        r = self.ri("task", "new", self.R, "--role", "investigator", "--mode", "RENEW", "--title", "continuation").split()[0]
        self.ri("task", "set", self.R, r, "done")
        a = self.assignment(self.ri("task", "new", self.R, "--role", "investigator", "--mode", "SELECT").split()[0])
        self.assertIn(f"- (RENEW {r} returned no successor cards)", a)
        self.assertNotIn(f"tasks/{r}/new/", a)

    def test_refuted_delivery_gets_the_after_refute_operators(self):
        self.R = str(Path(self.tmp.name, "r"))
        self.ri("init", self.R, "--objective", "claim", "--mode", "focused")
        self.ri("q", "add", self.R, "--title", "claim")
        self.ri("q", "set", self.R, "Q01", "--status", "refuted")
        self.convert()
        a = self.assignment(self.ri("task", "new", self.R, "--role", "investigator", "--mode", "RENEW").split()[0])
        self.assertIn("RENEW on the delivered result Q01 refuted (continuation from focused delivery, program.md sec. "
                      "2.1): apply the After-REFUTE operators (frontier-method.md sec. 10);", a)
        self.assertNotIn("After-ACCEPT", a)


class TestDeliveredResult(ContinuationCase):
    """What the continuation RENEW is asked to do depends on what was delivered (program.md sec. 2.1)."""

    def renew(self):
        return self.assignment(self.ri("task", "new", self.R, "--role", "investigator", "--mode", "RENEW",
                                       "--title", "continuation").split()[0])

    def test_open_stronger_rungs_are_candidates_beside_tightness(self):
        self.focused(rung="R2")
        self.write("lanes/Q01/statement.md", "R1 (optional stronger), R2 (target rung), R3.\nD refutes: R2\n")
        c = self.accepted("Q01.R2")
        self.ri("q", "set", self.R, "Q01", "--status", "resolved", "--rung", "R2")
        self.convert()
        self.assertIn(f"RENEW on the delivered result Q01 resolved@R2 ({c}) (continuation from focused delivery, "
                      "program.md sec. 2.1): apply the After-ACCEPT operators", self.renew_text())
        self.assertIn("its fallback rung; the stronger rung R1 of lanes/Q01/statement.md is still open: a candidate "
                      "beside TIGHTNESS; at most 3 successors", self.renew_text())

    def renew_text(self):
        if not hasattr(self, "_renew"):
            self._renew = self.renew()
        return self._renew

    def test_fallback_rung_only_gets_after_stall_on_the_open_target(self):
        self.focused()
        self.write("lanes/Q01/statement.md", "R1: the claim.\nR2: a weaker fallback.\nD: the negation of R1. "
                                             "D refutes: R1\n")
        c = self.accepted("Q01.R2")
        self.ri("q", "set", self.R, "Q01", "--status", "parked", "--note", "lane budget; R2 consolidated")
        self.convert()
        self.assertIn("The RENEW applies After-STALL on the open target R1, then After-ACCEPT on R2", self.status())
        self.assertIn(f"RENEW on the delivered result Q01 parked@R2 ({c}) (continuation from focused delivery, program.md "
                      "sec. 2.1): apply the After-STALL operators (frontier-method.md sec. 10) to the open target R1 "
                      "first (the rung R1 of lanes/Q01/statement.md is open), then to the accepted R2 the After-ACCEPT "
                      "operators", self.renew_text())

    def test_reading_successor_with_a_failure_report_is_the_delivered_question(self):
        self.focused()
        self.write("lanes/Q01/statement.md", "R1: literal.\nStronger (after R1):\n- a stronger literal claim\n")
        self.ri("q", "set", self.R, "Q01", "--status", "refuted")
        self.ri("q", "add", self.R, "--title", "natural reading", "--parent", "Q01", "--operator", "READING")
        self.write("lanes/Q02/statement.md", "R1: natural.\nStronger (after R1):\n- none\n")
        self.ri("q", "set", self.R, "Q02", "--status", "active", "--rung", "R1")
        self.ri("q", "set", self.R, "Q02", "--status", "parked", "--note", "failure report delivered")
        self.assertIn("delivered: Q02", self.convert())
        self.assertEqual(self.state()["converted"]["question"], "Q02")
        self.assertIn(CONT + "investigator RENEW --title continuation on Q02 + LANDSCAPE (none ran; if workers have "
                      "web), then PROPOSE x2-4, then SELECT. The RENEW applies After-STALL and writes", self.status())
        a = self.renew_text()
        self.assertIn("RENEW on the delivered result Q02 parked (continuation from focused delivery, program.md sec. "
                      "2.1): apply the After-STALL operators (frontier-method.md sec. 10) to the open target R1 (no "
                      "rung was accepted);", a)
        self.assertIn("- questions/Q02.md (the delivered question)\n- lanes/Q02/statement.md\n", a)
        for absent in ("After-REFUTE", "(parked)", "Stronger (after R1)"):  # a refuted claim's stronger items are false
            self.assertNotIn(absent, a)

    def test_bulleted_none_is_no_stronger_item(self):
        self.focused()
        for text in ("- none", "- (none)", "* None plausible.", "(none)"):
            self.write("lanes/Q01/statement.md", f"R1: x.\nStronger (after R1):\n{text}\n")
            self.assertEqual(ri.stronger_paths(self.R, self.state(), "Q01"), [], text)
        self.write("lanes/Q01/statement.md", "R1: x.\nStronger (after R1):\n- R1 for every n\n")
        self.assertEqual(ri.stronger_paths(self.R, self.state(), "Q01"), ["lanes/Q01/statement.md"])

    def test_safeguard_counts_from_the_conversion(self):
        self.R = str(Path(self.tmp.name, "n"))
        self.ri("init", self.R, "--objective", "claim", "--mode", "focused")
        self.ri("q", "add", self.R, "--title", "claim")
        for i in range(25):  # focused work before the conversion does not count
            self.ri("task", "set", self.R, self.task("scout", "EXPLORE", title=f"focused {i}"), "done")
        self.ri("q", "set", self.R, "Q01", "--status", "refuted")
        self.convert()
        self.assertIsNone(ri.no_prover_safeguard(self.state()))
        for i in range(19):
            self.ri("task", "set", self.R, self.task("scout", "EXPLORE", title=f"cell {i}"), "done")
        self.assertIsNone(ri.no_prover_safeguard(self.state()))
        self.ri("task", "set", self.R, self.task("investigator", "SELECT"), "done")
        self.assertEqual(ri.no_prover_safeguard(self.state()), "20 tasks finished")
        out = self.status()
        self.assertIn("no-prover safeguard (20 tasks finished): the next investigator SELECT or RENEW packet carries "
                      "the safeguard line", out)
        self.assertNotIn("no prover yet", out)  # the watchdog's fresh-opening steps never apply to a converted run
        self.assertIn(ri.SAFEGUARD, self.assignment(self.task("investigator", "RENEW", fill=False)))


class TestRefutationUnderContinue(ContinuationCase):
    """The refutation endings under continue: READING kept the refutation, its report passed PAPER, the conversion."""

    def test_kept_refutation_is_delivered_then_after_refute(self):
        self.focused()
        self.r1("Q01")
        ce = self.accepted_ce("Q01.R1")
        self.ri("exclude", self.R, "--claim", "Q01.R1", "--cand", ce)
        self.ri("q", "set", self.R, "Q01", "--status", "refuted")
        inv = self.task("investigator", "RENEW")
        self.ri("task", "set", self.R, *self.state()["tasks"], "done")
        self.ri("event", self.R, "--handled", "E1", "--by", inv)
        self.assertIn(f"Q01 focused, refuted: READING ({inv}) kept the refutation; the target is refuted: a refutation "
                      "report from the record (its witness); after delivery (PAPER passed, or the report delivered): "
                      f"say in progress.md sec. 1 that the result is delivered and the run continues as a research "
                      f"program built on it; then {CONVERT}", self.status())
        w = self.task("writer", extra=("--cand", ce))
        self.write(f"tasks/{w}/manuscript.md", "# Refutation\nThe witness.\n")
        m = self.ri("cand", "add", self.R, "--lane", "Q01", "--claims", "Q01.D", "--kind", "manuscript",
                    "--file", f"tasks/{w}/manuscript.md", "--author", w).split()[0]
        self.review(m, self.task("verifier", "PAPER"), "paper", "PASS")
        self.ri("accept", self.R, m)
        self.ri("task", "set", self.R, *[k for k, t in self.state()["tasks"].items() if t["status"] == "queued"], "done")
        self.assertIn(f"Q01 delivered ({m} passed PAPER; after delivery: continue): say in progress.md sec. 1",
                      self.status())
        self.assertIn("delivered: Q01", self.convert())
        self.assertIn("The RENEW applies After-REFUTE and writes the map grid", self.status())
        a = self.assignment(self.ri("task", "new", self.R, "--role", "investigator", "--mode", "RENEW").split()[0])
        self.assertIn("RENEW on the delivered result Q01 refuted (continuation from focused delivery, program.md sec. "
                      "2.1): apply the After-REFUTE operators (frontier-method.md sec. 10; READING already ran in "
                      "focused mode: skip it);", a)
        self.assertNotIn("After-ACCEPT", a)


class TestTightnessIsClassWide(RiCase):
    def test_docs_state_the_class_wide_converse_first(self):
        skill = SCRIPT.parent.parent
        fm = (skill / "references" / "frontier-method.md").read_text(encoding="utf-8")
        tight = fm[fm.index("TIGHTNESS (the converse"):][:700]
        for needle in ("whole class", "fallback rung (R2)", "never the only rung"):
            self.assertIn(needle, " ".join(tight.split()))
        program = (skill / "references" / "program.md").read_text(encoding="utf-8")
        self.assertIn("### 2.1 Continuation opening", program)
        self.assertIn("ri.py mode RUN --to program", program)
        self.assertIn("--after", (skill / "references" / "state.md").read_text(encoding="utf-8"))

    def test_fast_start_model_lists_the_class_wide_converse(self):
        self.R = str(Path(self.tmp.name, "f"))
        self.ri("init", self.R, "--objective", "claim", "--mode", "focused")
        self.ri("q", "add", self.R, "--title", "claim")
        t = self.ri("task", "new", self.R, "--role", "investigator", "--mode", "MODEL", "--title",
                    "focused fast start").split()[0]
        self.assertIn("(with the converse for the whole class when one is plausible, frontier-method.md sec. 10 "
                      "TIGHTNESS)", self.assignment(t))


if __name__ == "__main__":
    unittest.main()
