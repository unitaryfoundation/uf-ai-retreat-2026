"""v6.3 review fixes: behaviours that the integration review found missing or wrong (scripts/ri.py).

Run:  python -B -m unittest discover -s tests -v     (from the skill directory)
"""
import unittest
from pathlib import Path

from test_ri import RiCase, ri

ARGUMENT = "## Statement\nR1 verbatim.\n\n## Object\nThe instance m = n = 1.\n\n## Proof\nSecret steps.\n"


class ReviewCase(RiCase):
    def focused(self, title="claim as stated"):
        self.ri("init", self.R, "--objective", "prove only this claim", "--mode", "focused", "--after", "stop",
                "--stop-quote", "prove only this claim")  # v6.3 endings
        self.ri("q", "add", self.R, "--title", title, "--model", "M1")
        self.r1("Q01")

    def gate(self, question="Q01", mode="QUESTION-GATE", light=True):
        args = ["task", "new", self.R, "--role", "skeptic", "--mode", mode, "--question", question]
        return self.ri(*args, *(["--light"] if light else []), "--start").split()[0]

    def gate_result(self, tid, *items, files=None, mode="QUESTION-GATE"):
        for name, text in (files or {}).items():
            self.write(f"tasks/{tid}/{name}", text)
        self.result(tid, f"mode: {mode}", *items)
        return self.ri("ingest", self.R, tid)

    def fast_start(self):
        """Focused fast start: the light gate is dispatched, then the lane opens and round 1 is briefed."""
        sk = self.gate()
        self.ri("q", "set", self.R, "Q01", "--status", "active", "--slots", "2", "--rung", "R1")
        self.ri("round", self.R, "Q01", "--open")
        s = self.task("summarizer", lane="Q01", extra=("--direction", "PROVE Q01.R1"))
        self.ri("task", "set", self.R, s, "done")
        return sk

    def refuted_by_reading_renew(self):
        """Focused Q01 refuted; the READING RENEW kept the refutation (no READING successor)."""
        self.ri("q", "set", self.R, "Q01", "--status", "active")
        self.ri("round", self.R, "Q01", "--open")
        ce = self.accepted_ce("Q01.R1")
        self.ri("exclude", self.R, "--claim", "Q01.R1", "--cand", ce)
        self.ri("q", "set", self.R, "Q01", "--status", "refuted")
        inv = self.task("investigator", "RENEW")
        self.ri("task", "set", self.R, *self.state()["tasks"], "done")
        self.ri("event", self.R, "--handled", "E1", "--by", inv)
        return inv


class TestReviewIngest(ReviewCase):
    def setUp(self):
        super().setUp()
        self.init()

    def test_ingest_brief_keeps_model_gate_and_literature_hints(self):
        self.write("frontier/model.md", "# Model cards\n## M0 baseline (S01)\n## M1 = M0 + X\n")
        sk = self.task("skeptic", "MODEL-GATE", title="M1")
        lit = self.task("literature-reviewer", "TARGETED")
        self.write(f"tasks/{sk}/degenerate-M1.md", "## Statement\nTrivial in M1.\n")
        self.result(sk, "mode: MODEL-GATE", "M1: {verdict: DEGENERATE, corrections: c(0) = 1/2}")
        self.result(lit, "mode: TARGETED", "found: settles (S05 Thm 3 answers Q02)", "follow_ups: [TARGETED y]")
        out = self.ri("ingest", self.R, sk, lit, "--brief")
        for line in (f"{sk} skeptic MODEL-GATE: done", "M1 DEGENERATE: apply-verdicts MODEL",
                     "task new --role verifier --mode ISOLATED --cand C001 --start; report now",
                     "M1 corrections: copy verbatim", f"{lit} literature-reviewer TARGETED: done",
                     "literature-hit: event --type literature-hit", "outer work: TARGETED y"):
            self.assertIn(line, out)
        self.assertNotIn("C001 frozen", out)
        self.assertNotIn("found: settles", out)


class TestReviewReading(ReviewCase):
    """K-READING follow-ups: the kept refutation is delivered; context events go to the live question."""

    def setUp(self):
        super().setUp()
        self.focused()

    def test_kept_refutation_gets_a_delivery_line_until_a_writer_exists(self):
        inv = self.refuted_by_reading_renew()
        line = (f"Q01 focused, refuted: READING ({inv}) kept the refutation; the target is refuted: a refutation "
                "report from the record (its witness)")
        out = self.status()
        self.assertIn(line, out)
        self.assertIn("progress.md: '(nothing established yet)' while C", out)
        self.assertNotIn("nothing runnable", out)
        w = self.task("writer", extra=("--cand", "C001"))
        self.ri("task", "set", self.R, w, "done")
        out = self.status()
        self.assertNotIn(line, out)
        acts = out.split("SUGGESTED NEXT ACTIONS:\n")[1].splitlines()
        self.assertEqual(acts[0], "  - nothing runnable: the target is refuted: a refutation report from the record "
                                  "(its witness) -> verifier PAPER")  # before the progress.md lint lines
        self.assertTrue(acts[1].startswith("  - progress.md: "))

    def test_no_delivery_line_after_a_reading_successor(self):
        self.refuted_by_reading_renew()
        self.ri("q", "add", self.R, "--title", "natural reading", "--parent", "Q01", "--operator", "READING")
        self.ri("q", "set", self.R, "Q02", "--status", "active")
        self.ri("round", self.R, "Q02", "--open")
        self.ri("event", self.R, "--type", "literature-hit", "--note", "S04 Thm 2 is related")  # no --lane: context
        out = self.status()
        self.assertNotIn("Q01 focused", out)
        self.assertIn("E2 literature-hit (no hold): context:", out)
        self.assertIn("E2 literature-hit: S04 Thm 2 is related -> first: context:", out)
        self.assertEqual(ri.focused_question(self.state()), "Q02")
        self.ri("q", "set", self.R, "Q02", "--status", "refuted")
        self.assertEqual(ri.focused_question(self.state()), "Q02")  # the last READING re-target


class TestReviewFastStart(ReviewCase):
    """The fast start's light gate: round 1's provers wait for it, and a non-ADVANCE stops them (program.md sec. 6.1,
    SKILL.md sec. 5 focused step 2)."""

    def setUp(self):
        super().setUp()
        self.focused()

    def test_provers_wait_for_the_light_gate_and_a_reformulate_stops_them(self):
        sk = self.fast_start()
        out = self.status()
        self.assertIn(f"Q01 r1: briefings done - provers wait for the light gate {sk} (program.md sec. 6.1)", out)
        self.assertNotIn("dispatch the provers", out)
        out = self.gate_result(sk, "Q01: {verdict: REFORMULATE}   # two readings in gate.md")
        self.assertIn("Q01: REFORMULATE -> event E1 question-verdict Q01 (no hold; one limited RENEW writes the next "
                      "version (once the lane is active, a successor question; SKILL.md sec. 5 focused step 2)); no "
                      "provers in this round", out)
        out = self.status()
        self.assertIn(f"Q01 r1: no provers - its light gate {sk} returned REFORMULATE: route it", out)
        self.assertIn("events pending: question-verdict Q01 (E1) -> dispatch investigator RENEW (batch; focused: "
                      "limited)", out)
        self.assertIn("E1 question-verdict Q01: REFORMULATE (T001) -> first: no hold; one limited RENEW", out)
        inv = self.task("investigator", "RENEW")
        self.ri("q", "add", self.R, "--title", "natural reading", "--parent", "Q01", "--operator", "READING")
        self.assertIn("its successor Q02 is registered: q set Q01 --status parked --note-file <file>", self.status())
        self.ri("event", self.R, "--handled", "E1", "--by", inv)
        self.ri("q", "set", self.R, "Q01", "--status", "parked")
        self.assertIn("Q02 (READING of Q01): fast start (program.md sec. 3, 6.1) - lanes/Q02/statement.md is the "
                      "RENEW's; light QUESTION-GATE (--question Q02 --light); q set Q02 --status active", self.status())

    def test_advance_releases_the_provers_and_keeps_the_lane_active(self):
        sk = self.fast_start()
        out = self.gate_result(sk, "Q01: {verdict: ADVANCE, plausibility: mixed}")
        self.assertIn("Q01: ADVANCE (plausibility mixed) -> q set RUN Q01 --plausibility mixed (the lane is open: round "
                      "1's provers may go, program.md sec. 6.1;", out)
        self.assertNotIn("--status ready", out)
        self.gate()  # a later light gate (on MODEL's statement) acts at the next round boundary
        self.assertIn("Q01 r1: briefings done - dispatch the provers", self.status())
        self.ri("q", "add", self.R, "--title", "not yet open")
        self.r1("Q02")
        out = self.gate_result(self.gate("Q02"), "Q02: {verdict: ADVANCE, plausibility: mixed}")
        self.assertIn("Q02: ADVANCE (plausibility mixed) -> q set RUN Q02 --plausibility mixed; --status ready once", out)

    def test_light_gate_kill_false_on_the_claim_gates_the_witness_then_reading(self):
        sk = self.fast_start()
        out = self.gate_result(sk, "Q01: {verdict: KILL(FALSE)}", files={"witness-Q01.md": ARGUMENT})
        self.assertIn(f"Q01: KILL(FALSE) -> no provers; do not kill Q01: gate the witness (verification.md sec. 8): "
                      f"cand add RUN --lane Q01 --claims Q01.R1 --kind counterexample --file tasks/{sk}/<witness file> "
                      f"--author {sk}, then INDIVIDUAL, SECOND-INDEPENDENT and WITNESS", out)
        self.assertNotIn("--status killed", out)
        self.assertEqual(self.state()["events"], [])
        self.assertIn(f"Q01 r1: no provers - its light gate {sk} returned KILL(FALSE)", self.status())
        ce = self.ri("cand", "add", self.R, "--lane", "Q01", "--claims", "Q01.R1", "--kind", "counterexample", "--file",
                     f"tasks/{sk}/witness-Q01.md", "--author", sk).split()[0]
        self.review(ce, self.task("verifier", "INDIVIDUAL"), "individual", "PASS")
        self.review(ce, self.task("scout", "WITNESS"), "witness", "PASS")
        self.assertIn("needs CROSS pass", self.ri("accept", self.R, ce, code=1))  # every counterexample: I3
        self.assertIn(f"{ce}: needs SECOND-INDEPENDENT review (single-draft cohort Q01 r1)", self.status())
        self.review(ce, self.task("verifier", "SECOND-INDEPENDENT"), "cross", "PASS")
        self.ri("accept", self.R, ce)
        self.ri("exclude", self.R, "--claim", "Q01.R1", "--cand", ce)
        self.assertIn("dispatch investigator RENEW (batch; focused: limited, READING first for a refutation",
                      self.status())

    def test_other_light_gate_kill_on_the_claim_logs_a_question_verdict(self):
        sk = self.fast_start()
        out = self.gate_result(sk, "Q01: {verdict: KILL(ILL-POSED)}")
        self.assertIn("Q01: KILL(ILL-POSED) -> event E1 question-verdict Q01 (no hold; one limited RENEW", out)
        self.assertNotIn("dead end", out)
        self.assertEqual(self.state()["questions"]["Q01"]["status"], "active")
        out = self.ri("event", self.R, "--type", "literature-hit", "--note", "S05 is related")
        self.assertIn("E2 literature-hit  (first: context: its note goes to the lane's next summarizers", out)
        R2 = str(Path(self.tmp.name, "p"))  # program mode: a KILL stays a dead end
        self.ri("init", R2, "--objective", "x")
        self.R = R2
        self.ri("q", "add", self.R, "--title", "seed")
        self.r1("Q01")
        out = self.gate_result(self.gate(), "Q01: {verdict: KILL(ILL-POSED)}")
        self.assertIn("-> q set RUN Q01 --status killed --note-file <file>  (\"ILL-POSED: <evidence>\"; a dead end)", out)
        self.assertIn("E1 question-verdict  (first: no hold; RENEW (before the first SELECT",
                      self.ri("event", self.R, "--type", "question-verdict"))

    def test_reading_successor_is_the_users_claim(self):
        self.ri("q", "add", self.R, "--title", "natural reading", "--parent", "Q01", "--operator", "READING")
        self.ri("q", "add", self.R, "--title", "weaker", "--parent", "Q01", "--operator", "DESCEND")
        for q in ("Q02", "Q03"):
            self.r1(q)
        st = self.state()
        self.assertEqual([ri.is_user_claim(st, q) for q in ("Q01", "Q02", "Q03")], [True, True, False])
        out = self.gate_result(self.gate("Q02,Q03"), "Q02: {verdict: KILL(IMPLIED)}", "Q03: {verdict: KILL(IMPLIED)}",
                               files={"implied-Q02.md": ARGUMENT})
        c = self.state()["candidates"]["C001"]
        self.assertEqual((c["claims"], c["for"]), ("Q02.R1", "Q02"))
        self.assertEqual([(e["type"], e["lane"]) for e in self.state()["events"]], [("question-verdict", "Q03")])
        self.assertIn("next: round RUN Q02 --open --gate-only", out)


class TestReviewOpening(ReviewCase):
    """Program opening: the seed fast start's foothold lane, the batched seed gate, events named in MODEL's packet."""

    def setUp(self):
        super().setUp()
        self.init()
        for t in ("seed claim a", "seed claim b", "selected later"):
            self.ri("q", "add", self.R, "--title", t)
        for q in ("Q01", "Q02", "Q03"):
            self.r1(q)

    def test_seed_light_gate_advance_opens_the_foothold_then_the_seed_gate(self):
        self.assertIn("next opening step: the first wave: SURVEY per family + LANDSCAPE + scout ANCHOR + one light "
                      "QUESTION-GATE on the primary claim seeds (program.md sec. 2 step 2)", self.status())
        sk = self.gate("Q01,Q02")
        out = self.gate_result(sk, "Q01: {verdict: REFORMULATE}", "Q02: {verdict: ADVANCE, plausibility: supported}")
        line = ("foothold: open Q02 now (its light gate's ADVANCE; SKILL.md sec. 5 step 4): q set RUN Q02 --status "
                "active --slots 2 --rung R1 (no --model); round RUN Q02 --open; briefings, then provers")
        self.assertIn(f"  next: {line}", out)
        out = self.status()
        self.assertIn(f"  - {line}", out)
        self.assertIn(f"next opening step: {line}", out)
        model = self.task("investigator", "MODEL")
        self.assertIn("Pending events (apply them: step 8 for seed verdicts; list them in events_handled):\n"
                      f"- E1 question-verdict Q01: REFORMULATE ({sk})\nInputs (open by path):", self.assignment(model))
        self.ri("q", "set", self.R, "Q02", "--status", "active", "--slots", "2", "--rung", "R1")
        self.ri("round", self.R, "Q02", "--open")
        out = self.status()
        self.assertNotIn("foothold: open", out)
        self.assertIn("Q02 r1: write plan.md slots", out)  # its gate's ADVANCE came before the lane opened
        mg = self.task("skeptic", "MODEL-GATE")
        self.task("prover", "PROVE", lane="Q02")
        self.assertNotIn("seed gate (program.md", self.status())  # the MODEL-GATE is still out
        self.write(f"tasks/{model}/new/Q02-statement.md", "Goal. R1 verbatim.\nR2: weaker.\n")  # the foothold's
        self.ri("task", "set", self.R, model, mg, "done")
        out = self.status()
        self.assertIn("seed gate (program.md sec. 2 step 4b): one batched full QUESTION-GATE --question Q01,Q02,Q03", out)
        self.assertIn(f"Q02: tasks/{model}/new/Q02-statement.md ({model}) is not installed - its next QUESTION-GATE "
                      "names it (at opening, the batched seed gate", out)
        g = self.gate("Q01,Q02,Q03", light=False)
        self.assertNotIn("seed gate (program.md", self.status())
        a = self.assignment(g)
        self.assertIn(f"- tasks/{model}/new/Q02-statement.md (the new version to gate", a)
        self.assertIn("- lanes/Q01/statement.md\n", a)

    def test_ready_questions_before_the_first_select(self):
        self.ri("q", "set", self.R, "Q03", "--status", "ready")
        self.assertIn("ready questions Q03: open Q03 as the foothold lane (SKILL.md sec. 5 step 6)", self.status())
        self.ri("q", "set", self.R, "Q01", "--status", "active")
        self.assertIn("ready questions Q03: wait for SELECT's lanes_to_open (foothold Q01 already open)", self.status())
        self.selected()
        self.assertIn("ready questions Q03: open lanes per the investigator's portfolio", self.status())


class TestReviewStatements(ReviewCase):
    """A fast-start MODEL's new statement: gated, then installed at a round boundary; 'Stronger (after R1)' items."""

    def setUp(self):
        super().setUp()
        self.focused()

    def test_new_statement_is_gated_then_installed(self):
        sk = self.fast_start()
        self.gate_result(sk, "Q01: {verdict: ADVANCE, plausibility: mixed}")
        model = self.task("investigator", "MODEL", title="focused fast start")
        self.write(f"tasks/{model}/new/Q01-statement.md", "Goal. R1 verbatim.\nR2: weaker.\n")
        self.ri("task", "set", self.R, model, "done")
        new = f"tasks/{model}/new/Q01-statement.md"
        self.assertIn(f"Q01: {new} ({model}) is not installed - light-gate it (task new --role skeptic --mode "
                      "QUESTION-GATE --question Q01 --light: its packet names it)", self.status())
        g = self.gate()
        a = self.assignment(g)
        self.assertIn(f"- {new} (the new version to gate; lanes/Q01/statement.md is the one in force)", a)
        self.assertNotIn("- lanes/Q01/statement.md\n", a)
        self.gate_result(g, "Q01: {verdict: ADVANCE, plausibility: mixed}")
        out = self.status()
        self.assertIn(f"Q01: install {new} as lanes/Q01/statement.md at the next round boundary (gate {g} passed)", out)
        self.assertIn("Q01 r1: briefings done - dispatch the provers", out)
        self.write("lanes/Q01/statement.md", "Goal. R1 verbatim.\nR2: weaker.\n")
        self.assertNotIn(new, self.status())
        self.assertIn("- lanes/Q01/statement.md\n", self.assignment(self.gate()))

    def test_rejected_statement_is_not_pending_and_a_briefed_round_without_provers_is_noted(self):
        sk = self.fast_start()
        self.gate_result(sk, "Q01: {verdict: DEMOTE}")
        inv = self.task("investigator", "RENEW")
        self.write(f"tasks/{inv}/new/Q01-statement.md", "Goal. R1.\nR2: stepping stone.\n")
        self.ri("task", "set", self.R, inv, "done")
        self.assertIn("is not installed - light-gate it", self.status())
        self.gate_result(self.gate(), "Q01: {verdict: REFORMULATE}")
        self.assertNotIn("is not installed", self.status())
        self.assertIsNone(ri.pending_statement(self.R, self.state(), "Q01"))
        out = self.ri("round", self.R, "Q01", "--open")
        self.assertIn("note: round 1 of Q01 had briefings but no provers; it still counts toward the lane budget", out)

    def test_stronger_items_come_before_consolidation(self):
        self.ri("q", "set", self.R, "Q01", "--status", "active", "--rung", "R1")
        self.ri("round", self.R, "Q01", "--open")
        self.write("lanes/Q01/statement.md", "Goal. Prove or disprove: R1.\nStronger (after R1):\n- R1 for every n\n")
        c = self.accepted("Q01.R1")
        out = self.status()
        self.assertIn(f"-> verifier PAPER, after the 'Stronger (after R1)' items run as a new question (q add, R1 = the "
                      "first item; light-gate it; q set --budget <rounds used + 2>; SKILL.md sec. 5 focused step 4); "
                      "then event --handled E1", out)
        self.ri("q", "add", self.R, "--title", "stronger")
        self.assertIn(f"consolidate Q01.R1 ({c}): copy", self.status())
        self.assertIn("-> verifier PAPER, after Q02 (the stronger items) ends; then event --handled E1", self.status())
        self.ri("q", "set", self.R, "Q02", "--status", "parked")
        self.assertIn("-> verifier PAPER; then event --handled E1", self.status())
        self.write("lanes/Q01/statement.md", "Goal. R1.\nStronger (after R1): none\n")
        st = self.state()
        self.assertFalse(ri.stronger_items(self.R, st, "Q01"))


class TestReviewEvents(ReviewCase):
    def test_unknown_task_under_stop_is_left_alone(self):
        self.init()
        t = self.task("scout", "EXPLORE", ctx="s1")
        self.ri("task", "set", self.R, t, "unknown")
        self.assertIn(f"{t}: status unknown - worker alive -> wait; else task new --redo {t} --start", self.status())
        self.ri("stop", self.R, "--reason", "enough")
        out = self.status()
        self.assertIn(f"{t}: status unknown - leave it; reconcile after the STOP or PAUSE is lifted", out)
        self.assertNotIn("--redo", out)

    def test_reacceptance_after_quarantine_logs_a_new_event(self):
        self.focused()
        self.ri("q", "set", self.R, "Q01", "--status", "active")
        self.ri("round", self.R, "Q01", "--open")
        c1 = self.accepted("Q01.R1")
        w = self.task("writer", extra=("--cand", c1))
        self.ri("event", self.R, "--handled", "E1", "--by", w)
        self.ri("quarantine", self.R, c1, "--code", "objection", "--reason", "late objection")  # E2 model-change
        self.ri("event", self.R, "--handled", "E2", "--by", self.task("investigator", "RENEW"))
        self.ri("round", self.R, "Q01", "--open")
        c2 = self.accepted("Q01.R1")
        evs = [(e["id"], e["type"], e.get("cands")) for e in self.state()["events"]]
        self.assertEqual(evs, [("E1", "top-accepted", [c1]), ("E2", "model-change", None),
                               ("E3", "top-accepted", [c2])])
        self.assertIn(f"no RENEW for E3 top-accepted; consolidate Q01.R1 ({c2})", self.status())
        c3 = self.accepted("Q01.R1")  # c2 still stands: one event
        self.assertEqual(self.state()["events"][-1]["cands"], [c2, c3])
        self.assertEqual(ri.event_cands({"note": "C001 accepted for Q01.R1; also C004 accepted"}), ["C001", "C004"])


if __name__ == "__main__":
    unittest.main()
