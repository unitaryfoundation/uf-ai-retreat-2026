"""v6.3 tests for packages A (a result found at a gate is a result), M (consolidation and focused mode),
the K-READING routing of focused refutations, and the gate-only round budget (scripts/ri.py).

Run:  python -B -m unittest discover -s tests -v     (from the skill directory)
"""
import unittest
from pathlib import Path

from test_ri import RiCase, ri

ARGUMENT = "## Statement\nR1 verbatim.\n\n## Object\nThe protocol P: query x, then answer f(x).\n\n## Proof\nSecret steps.\n"


class SkepticCase(RiCase):
    def gate(self, question="Q01", mode="QUESTION-GATE", light=True, start=True):
        args = ["task", "new", self.R, "--role", "skeptic", "--mode", mode, "--question", question]
        return self.ri(*args, *(["--light"] if light else []), *(["--start"] if start else [])).split()[0]

    def q(self, title="claim", *extra):
        qid = self.ri("q", "add", self.R, "--title", title, *extra).split()[0]
        self.r1(qid)  # a QUESTION-GATE needs an exact R1 (Package B, K14)
        return qid

    def gate_result(self, tid, *items, files=None, mode="QUESTION-GATE"):
        for name, text in (files or {}).items():
            self.write(f"tasks/{tid}/{name}", text)
        self.result(tid, f"mode: {mode}", *items)
        return self.ri("ingest", self.R, tid)


class TestV63GateResults(SkepticCase):
    """Package A: SOLVED, solved: Rj, REFUTE-SKETCH and KILL(IMPLIED) routing (program.md sec. 5.2-5.3)."""

    def setUp(self):
        super().setUp()
        self.init()

    def test_solved_light_gate_freezes_argument_as_skeptic_candidate(self):
        self.q()
        self.ri("q", "set", self.R, "Q01", "--status", "vetting")
        sk = self.gate()
        out = self.gate_result(sk, "Q01: {verdict: SOLVED}   # with solved-Q01.md", files={"solved-Q01.md": ARGUMENT})
        c = self.state()["candidates"]["C001"]
        self.assertEqual((c["claims"], c["author"], c["kind"], c["source"], c["round"], c["for"]),
                         ("Q01.R1", sk, "proof", f"tasks/{sk}/solved-Q01.md", 1, None))
        self.assertEqual(ri.xp(self.path("candidates", "C001.md")).read_text(encoding="utf-8"), ARGUMENT)  # unchanged
        for line in ("next: q set RUN Q01 --status active --slots 2 --plausibility supported",
                     "next: round RUN Q01 --open --gate-only",
                     "next: task new RUN --role verifier --mode INDIVIDUAL --cand C001 --start",
                     "next: task new RUN --role verifier --mode SECOND-INDEPENDENT --cand C001 --start"):
            self.assertIn(line, out)
        self.assertNotIn("--mode SANITY", out)  # no Sanity line names a check
        self.assertEqual(self.state()["questions"]["Q01"]["verdicts"][0]["code"], "SOLVED")
        self.assertEqual(self.state()["events"], [])
        self.ri("q", "set", self.R, "Q01", "--status", "active", "--slots", "2", "--plausibility", "supported")
        self.assertEqual(self.ri("round", self.R, "Q01", "--open", "--gate-only").strip(), "1")
        q = self.state()["questions"]["Q01"]
        self.assertEqual(q["gate_only"], [1])
        self.assertIn("gate-only (no provers", self.path("lanes", "Q01", "round-01", "plan.md").read_text(encoding="utf-8"))
        self.assertIn("check OK", self.ri("check", self.R))

    def test_solved_in_active_fast_start_lane_marks_round_gate_only(self):
        self.q()
        self.ri("q", "set", self.R, "Q01", "--status", "active", "--slots", "2")
        self.ri("round", self.R, "Q01", "--open")
        self.write("lanes/Q01/statement.md", "Goal. R1.\nSanity. f(x) = x on n <= 6.\n")
        summ = self.task("summarizer", lane="Q01")
        self.assertEqual(self.state()["counters"]["lane_rounds"], 1)
        sk = self.gate()
        out = self.gate_result(sk, "Q01: {verdict: SOLVED}", files={"solved-Q01.md": ARGUMENT})
        self.assertIn("Q01 round 1 is now a gate-only round: dispatch no provers in it", out)
        self.assertIn("next: task new RUN --role scout --mode SANITY --cand C001 --start  (Sanity: f(x) = x", out)
        self.assertNotIn("round RUN Q01 --open --gate-only", out)
        st = self.state()
        self.assertEqual(st["questions"]["Q01"]["gate_only"], [1])
        self.assertEqual(st["counters"]["lane_rounds"], 0)  # the breadth trigger counts prover rounds
        self.assertEqual(st["candidates"]["C001"]["round"], 1)
        self.ri("task", "set", self.R, summ, "done")
        out = self.status()
        self.assertNotIn("dispatch the provers", out)
        self.assertIn("(budget 0/8) VERIFY", out)
        self.assertIn("C001: needs SECOND-INDEPENDENT review (gate-only round Q01 r1)", out)
        self.assertEqual(ri.lane_stage(self.state(), "Q01"), "VERIFY")
        v1 = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "INDIVIDUAL", "--cand", "C001",
                     "--start").split()[0]
        self.review("C001", v1, "individual", "FAIL", "--blocking", "O1 CRITICAL: Lemma 2 [PROB] - fails")
        self.assertEqual(ri.lane_stage(self.state(), "Q01"), "VERIFY")  # v1 still live; SECOND-INDEPENDENT missing
        v2 = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "SECOND-INDEPENDENT", "--cand", "C001",
                     "--start").split()[0]
        self.review("C001", v2, "cross", "FAIL", "--blocking", "O1 CRITICAL: Lemma 2 [PROB] - fails")
        self.ri("task", "set", self.R, v1, v2, "done")
        self.assertEqual(ri.lane_stage(self.state(), "Q01"), "CLOSE")
        out = self.status()
        self.assertIn("Q01 r1 closed: gate-only round, R1 not accepted: the lane runs normally from round 2 when the "
                      "lane cap allows (program.md sec. 5.3)", out)
        self.assertNotIn("dispatch the provers", out)
        self.assertNotIn("plan round 2", out)

    def test_solved_lower_rung_field_claims_that_rung(self):
        self.q()
        self.q("second")
        sk = self.gate("Q02")
        out = self.gate_result(sk, "Q02: {verdict: ADVANCE, plausibility: mixed, solved: R3}   # with solved-Q02.md",
                               files={"solved-Q02.md": ARGUMENT})
        st = self.state()
        self.assertEqual(st["candidates"]["C001"]["claims"], "Q02.R3")
        self.assertIn("Q02: ADVANCE (plausibility mixed) -> q set RUN Q02 --plausibility mixed", out)
        self.assertIn("next: task new RUN --role verifier --mode INDIVIDUAL --cand C001 --start", out)
        self.assertNotIn("--gate-only", out)  # a lower rung opens no round
        self.assertNotIn("gate_only", st["questions"]["Q02"])
        self.assertEqual(st["events"], [])

    def test_refute_sketch_freezes_refutation_claiming_d(self):
        self.q()
        sk = self.gate()
        out = self.gate_result(sk, "Q01: {verdict: REFUTE-SKETCH}", files={"refutation-Q1.md": ARGUMENT})
        c = self.state()["candidates"]["C001"]
        self.assertEqual((c["claims"], c["author"], c["source"]), ("Q01.D", sk, f"tasks/{sk}/refutation-Q1.md"))
        self.assertIn("--plausibility doubtful", out)
        self.assertIn("next: round RUN Q01 --open --gate-only", out)
        sk2 = self.gate()
        out = self.gate_result(sk2, "Q01: {verdict: REFUTE-SKETCH}")  # no file
        self.assertIn(f"{sk2}: Q01 REFUTE-SKETCH without tasks/{sk2}/refutation-Q01.md", out)
        self.assertEqual(len(self.state()["candidates"]), 1)

    def test_reformulate_demote_and_implied_log_question_verdict_without_hold(self):
        for t in ("a", "b", "c", "d"):
            self.q(t)
        sk = self.gate("Q01,Q02,Q03,Q04", light=False)
        out = self.gate_result(sk, "Q01: {verdict: REFORMULATE}", "Q02: {verdict: DEMOTE} # stepping stone",
                               "Q03: {verdict: KILL (implied)}", "Q04: {verdict: KILL(KNOWN)}",
                               files={"implied-Q03.md": ARGUMENT})
        st = self.state()
        self.assertEqual([(e["type"], e["lane"], e["note"]) for e in st["events"]],
                         [("question-verdict", "Q01", f"REFORMULATE ({sk})"), ("question-verdict", "Q02", f"DEMOTE ({sk})"),
                          ("question-verdict", "Q03", f"KILL(IMPLIED) ({sk})")])
        self.assertTrue(all(not q.get("held_by") for q in st["questions"].values()))
        self.assertIn("question-verdict", ri.RENEW_TYPES)
        self.assertNotIn("question-verdict", ri.HOLD_TYPES)
        self.assertEqual(st["candidates"], {})  # an unrequested KILL(IMPLIED) argument stays a remark
        self.assertIn('next: q set RUN Q03 --status killed --note-file <file>  ("IMPLIED: follows from <locator>"', out)
        self.assertIn('Q04: KILL(KNOWN) -> q set RUN Q04 --status killed --note-file <file>  ("KNOWN: <evidence>"', out)
        self.assertIn("E1 question-verdict Q01: REFORMULATE", self.status("--full"))

    def test_item_fields_braces_comments_and_bare_verdicts(self):
        self.assertEqual(ri.item_fields("{verdict: KILL(IMPLIED)} # with implied-Q08.md"), {"verdict": "KILL(IMPLIED)"})
        self.assertEqual(ri.item_fields("{verdict: ADVANCE, plausibility: mixed, solved: R3}"),
                         {"verdict": "ADVANCE", "plausibility": "mixed", "solved": "R3"})
        self.assertEqual(ri.item_fields("{verdict: PATCH, corrections: c(0) = 1, not 2; measure: max}"),
                         {"verdict": "PATCH", "corrections": "c(0) = 1, not 2; measure: max"})
        self.assertEqual(ri.item_fields("ADVANCE"), {"verdict": "ADVANCE"})
        self.assertEqual(ri.verdict_code("kill (implied)"), "KILL(IMPLIED)")
        self.q()
        sk = self.gate()
        self.assertIn(f"{sk}: Q01: unknown QUESTION-GATE verdict 'MAYBE'", self.gate_result(sk, "Q01: MAYBE"))
        self.assertNotIn("verdicts", self.state()["questions"]["Q01"])
        sk2 = self.gate()
        self.gate_result(sk2, "Q01: advance")
        self.assertEqual(self.state()["questions"]["Q01"]["verdicts"], [{"task": sk2, "code": "ADVANCE",
                                                                         "seq": self.state()["seq"]}])

    def test_q_set_killed_refused_while_gate_review_live_and_after_r1_accepted(self):
        self.q()
        sk = self.gate()
        self.gate_result(sk, "Q01: {verdict: SOLVED}", files={"solved-Q01.md": ARGUMENT})
        v = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "INDIVIDUAL", "--cand", "C001").split()[0]
        for status in ("killed", "parked"):
            out = self.ri("q", "set", self.R, "Q01", "--status", status, code=1)
            self.assertIn(f"Q01 cannot be set {status}: {v} still reviewing or checking its candidates; route by "
                          "program.md sec. 5.3", out)
        self.assertEqual(self.state()["questions"]["Q01"]["status"], "draft")
        self.review("C001", v, "individual", "FAIL", "--blocking", "O1 CRITICAL: Lemma 1 - false")
        self.ri("task", "set", self.R, v, "done")
        self.ri("q", "set", self.R, "Q01", "--status", "parked")
        self.ri("q", "set", self.R, "Q01", "--status", "killed")
        self.q("other")
        c = self.accepted("Q02.R1")
        for status in ("killed", "parked"):
            self.assertIn(f"its R1 is accepted ({c})", self.ri("q", "set", self.R, "Q02", "--status", status, code=1))
        self.ri("q", "set", self.R, "Q02", "--status", "resolved")

    def test_implied_argument_needs_for_and_gets_no_too_easy_hint(self):
        self.q()
        self.q("citer")
        sk = self.gate()
        self.write(f"tasks/{sk}/implied-Q01.md", ARGUMENT)
        args = ("cand", "add", self.R, "--file", f"tasks/{sk}/implied-Q01.md", "--author", sk, "--claims", "Q01.R1")
        self.assertIn("certified only for a named citer", self.ri(*args, code=1))
        self.assertIn("malformed --for", self.ri(*args, "--for", "X7", code=2))
        self.ri(*args, "--for", "Q09", code=2)  # unknown question
        self.assertIn("for Q02", self.ri(*args, "--for", "q2"))
        c = self.state()["candidates"]["C001"]
        self.assertEqual((c["for"], c["source"]), ("Q02", f"tasks/{sk}/implied-Q01.md"))
        self.assertTrue(ri.is_implied(c))
        v = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "INDIVIDUAL", "--cand", "C001",
                    "--start").split()[0]
        self.result(v, "scope: INDIVIDUAL", "review C001: verdict=PASS; fidelity=MATCH", "too_easy C001: short-proof")
        out = self.ri("ingest", self.R, v)
        self.assertIn("too_easy C001: ignored (a KILL(IMPLIED) certificate is easy by design", out)
        self.assertNotIn("event --type too-easy", out)
        st = self.state()
        self.assertNotIn("too_easy", st["reviews"][-1])
        st["reviews"][-1]["too_easy"] = "short-proof"  # legacy record: the status line skips it too
        self.save(st)
        self.assertNotIn("too_easy short-proof reported", self.status())
        self.assertIn("for H2", self.ri("cand", "add", self.R, "--file", f"tasks/{sk}/implied-Q01.md", "--author", sk,
                                        "--claims", "Q01.R1", "--for", "h2"))

    def test_gate_only_round_not_counted_in_lane_cap(self):
        R2 = str(Path(self.tmp.name, "k4"))
        self.ri("init", R2, "--objective", "x", "--k", "4")  # lane cap max(2, 4 // 2) = 2
        self.R = R2
        self.selected()
        self.lane()
        self.q("gated")
        self.ri("q", "set", self.R, "Q02", "--status", "active")
        self.assertNotIn("queue low", self.status())  # two normal lanes fill the cap
        self.ri("q", "set", self.R, "Q02", "--status", "vetting")
        self.ri("q", "set", self.R, "Q02", "--status", "active")
        self.ri("round", self.R, "Q02", "--open", "--gate-only")
        self.assertEqual(self.state()["counters"]["lane_rounds"], 1)  # only Q01's prover round
        self.assertIn("queue low (0 ready + 0 vetting < 1 free lanes)", self.status())
        self.assertTrue(ri.in_gate_only_round(self.state()["questions"]["Q02"]))
        self.assertNotIn("passes the lane budget", self.ri("round", self.R, "Q01", "--open"))

    def test_object_section_copied_for_sanity_packet(self):
        self.q()
        sk = self.gate()
        self.gate_result(sk, "Q01: {verdict: SOLVED}", files={"solved-Q01.md": ARGUMENT})
        s = self.ri("task", "new", self.R, "--role", "scout", "--mode", "SANITY", "--cand", "C001").split()[0]
        a = self.assignment(s)
        self.assertIn(f"- tasks/{s}/object-C001.md (the claim and the protocol or witness object of C001", a)
        self.assertNotIn("candidates/C001.md", a)
        copy = ri.xp(self.path("tasks", s, "object-C001.md")).read_text(encoding="utf-8")
        self.assertIn("## Statement\nR1 verbatim.", copy)
        self.assertIn("## Object\nThe protocol P", copy)
        self.assertNotIn("## Proof", copy)
        self.assertNotIn("Secret steps", copy)
        p = self.task("prover", "PROVE", lane="Q01")
        c = self.cand(p, "Q01.R1")  # a prover draft without '## Object': the candidate itself, as before
        w = self.ri("task", "new", self.R, "--role", "scout", "--mode", "WITNESS", "--cand", c).split()[0]
        self.assertIn(f"- candidates/{c}.md (read only the claim", self.assignment(w))

    def test_events_before_first_select_route_to_select_not_renew(self):
        self.q()
        sk = self.gate()
        self.gate_result(sk, "Q01: {verdict: REFORMULATE}")
        self.ri("event", self.R, "--type", "milestone", "--note", "user asked")
        out = self.status()
        self.assertIn("events pending: question-verdict Q01 (E1), milestone (E2) - handled by SELECT (opening), or by "
                      "the MODEL whose Assignment names them (a KILL(IMPLIED)'s successors: SELECT); then event --handled",
                      out)
        self.assertNotIn("dispatch investigator RENEW", out)
        self.selected()
        self.assertIn("events pending: question-verdict Q01 (E1), milestone (E2) -> dispatch investigator RENEW",
                      self.status())
        R2 = str(Path(self.tmp.name, "f"))  # focused mode has no SELECT: RENEW as before
        self.ri("init", R2, "--objective", "claim", "--mode", "focused")
        self.ri("event", R2, "--type", "milestone")
        self.assertIn("events pending: milestone (E1) -> dispatch investigator RENEW", self.ri("status", R2))

    def test_renew_without_successor_below_cap_prints_queue_low(self):
        self.selected()
        self.lane()
        msg = "RENEW returned no successor while the portfolio is below the lane cap (1 active + ready + vetting < 2)"
        r = self.ri("task", "new", self.R, "--role", "investigator", "--mode", "RENEW", "--start").split()[0]
        self.result(r, "lanes: continue Q01")
        self.assertIn(msg + ": event --type queue-low", self.ri("ingest", self.R, r))
        r2 = self.ri("task", "new", self.R, "--role", "investigator", "--mode", "RENEW", "--start").split()[0]
        self.write(f"tasks/{r2}/new/N1-card.md", "card")
        self.result(r2, "lanes: continue Q01")
        self.assertNotIn("RENEW returned no successor", self.ri("ingest", self.R, r2))
        self.q("ready one")
        self.ri("q", "set", self.R, "Q02", "--status", "ready")
        r3 = self.ri("task", "new", self.R, "--role", "investigator", "--mode", "RENEW", "--start").split()[0]
        self.result(r3, "lanes: continue Q01")
        self.assertNotIn("RENEW returned no successor", self.ri("ingest", self.R, r3))  # portfolio at the cap
        R2 = str(Path(self.tmp.name, "f"))  # focused RENEW is limited: no successor duty
        self.ri("init", R2, "--objective", "claim", "--mode", "focused")
        self.R = R2
        r4 = self.ri("task", "new", self.R, "--role", "investigator", "--mode", "RENEW", "--start").split()[0]
        self.result(r4, "lanes: none")
        self.assertNotIn("RENEW returned no successor", self.ri("ingest", self.R, r4))

    def test_focused_q01_implied_argument_is_gated_not_killed(self):
        R2 = str(Path(self.tmp.name, "f"))
        self.ri("init", R2, "--objective", "claim", "--mode", "focused")
        self.R = R2
        self.q()
        sk = self.gate()
        out = self.gate_result(sk, "Q01: {verdict: KILL(IMPLIED)}   # locator in gate.md",
                               files={"implied-Q01.md": ARGUMENT})
        c = self.state()["candidates"]["C001"]
        self.assertEqual((c["claims"], c["for"], c["author"]), ("Q01.R1", "Q01", sk))
        self.assertEqual(self.state()["events"], [])
        self.assertNotIn("--status killed", out)
        for line in ("next: q set RUN Q01 --status active --slots 2 --plausibility supported",
                     "next: round RUN Q01 --open --gate-only",
                     "next: task new RUN --role verifier --mode INDIVIDUAL --cand C001 --start",
                     "next: task new RUN --role verifier --mode SECOND-INDEPENDENT --cand C001 --start"):
            self.assertIn(line, out)
        self.q("a second claim")  # only Q01 is the user's claim
        sk2 = self.gate("Q02")
        out = self.gate_result(sk2, "Q02: {verdict: KILL(IMPLIED)}", files={"implied-Q02.md": ARGUMENT})
        self.assertEqual(len(self.state()["candidates"]), 1)
        self.assertEqual(self.state()["events"][-1]["type"], "question-verdict")

    def test_claim_gate_items_print_qualifier_known_and_trivial_hints(self):
        for t in ("a", "b", "c", "d"):
            self.q(t)
        sk = self.ri("task", "new", self.R, "--role", "skeptic", "--mode", "CLAIM-GATE", "--extra", "Gate.",
                     "--start").split()[0]
        out = self.gate_result(sk, "Q01.R1: {verdict: QUALIFY}", "Q02.R1: {verdict: KNOWN}", "q03.r2: {verdict: TRIVIAL}",
                               "Q04.R1: OVERCLAIM", "too_easy: Q01.R1 short-proof", "contradiction: none",
                               mode="CLAIM-GATE")
        self.assertIn("Q01.R1: QUALIFY -> copy the qualifier verbatim into every progress.md section stating the "
                      "result, sec. 1 included, and into the writer's Assignment (program.md sec. 5.2)", out)
        self.assertIn("Q02.R1: KNOWN -> a rediscovery: report it with its locator; event --type literature-hit --lane "
                      "Q02 --note-file <file>", out)
        self.assertIn("Q03.R2: TRIVIAL -> remark; dispatch a skeptic MODEL-GATE for loopholes", out)
        self.assertIn("Q04.R1: OVERCLAIM -> copy the corrected wording verbatim", out)
        self.assertIn("too_easy reported: event --type too-easy", out)
        self.assertIn("contradiction: none", out)
        self.assertEqual(self.state()["events"], [])


class TestV63GateOnlyBudget(RiCase):
    """Gate-only rounds never count toward a lane's round budget (lane-budget events, budget_base)."""

    def setUp(self):
        super().setUp()
        self.init("--lane-budget", "2")
        self.lane()

    def test_gate_only_rounds_do_not_count_toward_the_round_budget(self):
        out = self.ri("round", self.R, "Q01", "--open", "--gate-only")
        self.assertNotIn("passes the lane budget", out)
        self.assertEqual(self.path("lanes", "Q01", "round-02", "plan.md").read_text(encoding="utf-8"),
                         "# Q01 round 02 — N = <not set: q set --slots>; rung <not set>; plausibility <not set>; "
                         "budget 1 of 2; gate-only (no provers: reviews of a skeptic's argument)\n")
        out = self.status()
        self.assertIn("round 2 (budget 1/2) CLOSE", out)
        self.assertNotIn("lane budget reached", out)
        self.assertIn("Q01 r2 closed: gate-only round, R1 not accepted: the lane runs normally from round 3", out)
        self.assertNotIn("passes the lane budget", self.ri("round", self.R, "Q01", "--open"))
        self.assertIn("budget 2 of 2", self.path("lanes", "Q01", "round-03", "plan.md").read_text(encoding="utf-8"))
        st = self.state()
        self.assertEqual(ri.budget_used(st["questions"]["Q01"]), 2)
        self.assertEqual(ri.close_steps(st, "Q01", 3), ["lane budget reached: event --type lane-budget --lane Q01"])
        self.assertIn("passes the lane budget (2 rounds since the last renewal)",
                      self.ri("round", self.R, "Q01", "--open", "--override-hold"))
        self.ri("event", self.R, "--type", "lane-budget", "--lane", "Q01")
        self.ri("event", self.R, "--handled", "E1", "--by", self.task("investigator", "RENEW"))
        self.assertEqual(self.state()["questions"]["Q01"]["budget_base"], 4)
        self.ri("round", self.R, "Q01", "--open", "--gate-only")
        self.assertIn("budget 0 of 2", self.path("lanes", "Q01", "round-05", "plan.md").read_text(encoding="utf-8"))
        self.ri("round", self.R, "Q01", "--open")
        self.assertIn("budget 1 of 2", self.path("lanes", "Q01", "round-06", "plan.md").read_text(encoding="utf-8"))
        self.assertIn("(budget 1/2)", self.status())

    def test_gate_only_round_opens_on_a_held_lane(self):
        self.ri("event", self.R, "--type", "literature-hit", "--lane", "Q01")
        self.ri("round", self.R, "Q01", "--open", code=1)
        out = self.ri("round", self.R, "Q01", "--open", "--gate-only")
        self.assertIn("a gate-only round dispatches no provers, so it opens anyway", out)
        self.assertEqual(self.state()["questions"]["Q01"]["gate_only"], [2])


class TestV63Reading(RiCase):
    """K-READING: a focused refutation first gets one limited RENEW; a READING question's refutation ends it."""

    def setUp(self):
        super().setUp()
        self.ri("init", self.R, "--objective", "claim", "--mode", "focused")
        self.ri("q", "add", self.R, "--title", "claim as stated", "--model", "M1")

    def test_focused_q01_refuted_routes_to_renew_not_consolidation(self):
        self.ri("q", "set", self.R, "Q01", "--status", "active")
        self.ri("round", self.R, "Q01", "--open")
        ce = self.accepted_ce("Q01.R1")
        self.ri("exclude", self.R, "--claim", "Q01.R1", "--cand", ce)
        st = self.state()
        self.assertIsNone(ri.focused_ending(self.R, st, st["events"][0]))
        out = self.status()
        self.assertIn("dispatch investigator RENEW (batch; focused: limited, READING first for a refutation", out)
        self.assertNotIn("no RENEW for E1", out)
        self.ri("event", self.R, "--type", "lane-budget", "--lane", "Q01")  # waits for the same READING RENEW
        out = self.status()
        self.assertIn("Q01 HELD by E2 (lane-budget) until RENEW", out)
        self.assertIn("events pending: refuted Q01 (E1), lane-budget Q01 (E2) -> dispatch investigator RENEW", out)
        inv = self.task("investigator", "RENEW")
        self.ri("event", self.R, "--handled", "E1", "--by", inv)  # READING found no natural reading left
        out = self.status()
        self.assertNotIn("dispatch investigator RENEW", out)
        self.assertIn("Q01 focused, target R1 excluded (L001): no RENEW for E2 lane-budget; the target is refuted: a "
                      "refutation report from the record (its witness)", out)

    def test_reading_child_refuted_consolidates(self):
        self.ri("q", "add", self.R, "--title", "claim, natural reading", "--parent", "Q01", "--operator", "READING")
        self.ri("q", "set", self.R, "Q02", "--status", "active")
        self.ri("round", self.R, "Q02", "--open")
        ce = self.accepted_ce("Q02.R1")
        self.ri("exclude", self.R, "--claim", "Q02.R1", "--cand", ce)
        out = self.status()
        self.assertNotIn("dispatch investigator RENEW", out)
        self.assertIn("Q02 focused, target R1 excluded (L001): no RENEW for E1 refuted; the target is refuted: a "
                      "refutation report from the record (its witness and Q01's literal refutation); then event "
                      "--handled E1 --by <the task that writes it>", out)
        self.assertIn("-> first: focused ending: consolidate or a failure report, no RENEW", out)


class TestV63Consolidation(SkepticCase):
    """Package M: comparator skipped for one candidate, fills-only revisions, length warnings, K64."""

    def setUp(self):
        super().setUp()
        self.init()
        self.lane()

    def test_focused_end_hint_skips_comparator_for_a_single_accepted_candidate(self):
        self.R = str(Path(self.tmp.name, "f"))
        self.ri("init", self.R, "--objective", "claim", "--mode", "focused")
        self.ri("q", "add", self.R, "--title", "claim")
        self.ri("q", "set", self.R, "Q01", "--status", "active")
        self.ri("round", self.R, "Q01", "--open")
        c1 = self.accepted("Q01.R1")
        out = self.status()
        self.assertIn(f"consolidate Q01.R1 ({c1}): copy {c1} to reports/Q01-R1-proof-{c1}.md now (proof-lane.md "
                      f"sec. 6); writer --cand {c1} (no comparator) with a skeptic CLAIM-GATE in parallel -> verifier "
                      "PAPER; then event --handled E1 --by <comparator or writer task>", out)
        self.accepted("Q01.R1")  # two accepted proofs of the best rung: the comparator chooses
        out = self.status()
        self.assertIn(f"consolidate Q01.R1 ({c1}): comparator -> writer -> verifier PAPER, with a CLAIM-GATE beside "
                      "the comparator; then event --handled", out)
        self.assertNotIn("writer --cand", out)

    def manuscript(self, text, *extra):
        w = self.task("writer")
        self.write(f"tasks/{w}/manuscript.md", text)
        out = self.ri("cand", "add", self.R, "--kind", "manuscript", "--claims", "Q01.R1", "--file",
                      f"tasks/{w}/manuscript.md", "--author", w, *extra)
        return out.split()[0], out

    PAPER = "# Paper\n\n## 1. Introduction\nIntro.\n\n## 2. Proof\nStep one.\nStep two.\n\n## 3. Discussion\nEnd.\n"

    def paper_review(self, cid):
        v = self.task("verifier", "PAPER")
        self.write(f"tasks/{v}/review.md", "Phase 1.\nO1 MINOR: Proof - a step is missing.\n"
                                           "FILL O1 in ## 2. Proof\nStep one and a half.\nEND FILL\n"
                                           "FILL O2 in 3. Discussion\nA closing remark.\n\nIn two paragraphs.\nEND FILL\n")
        self.review(cid, v, "paper", "PASS_WITH_MINOR", "--report", f"tasks/{v}/review.md",
                    "--blocking", "O1 MINOR: Proof - a step is missing; O2 MINOR: Discussion - remark")
        return v

    def test_manuscript_revision_with_only_fill_blocks_is_accepted_on_parent_review(self):
        self.assertEqual(ri.parse_fills("FILL O3 in ## A\nx\n\ny\nEND FILL\n"), [("O3", "## A", "x\n\ny")])
        m1, _ = self.manuscript(self.PAPER)
        v = self.paper_review(m1)
        self.ri("accept", self.R, m1)
        text = self.PAPER.replace("Step one.\n", "Step one.\nStep one and a half.\n").replace(
            "End.\n", "End.\n\nA closing remark.\n\nIn two paragraphs.\n")
        m2, out = self.manuscript(text, "--revises", m1)
        self.assertIn(f"[fills only: {v}'s PAPER review of {m1} counts as its PAPER pass]", out)
        self.assertEqual(self.state()["candidates"][m2]["delta_review"], v)
        self.assertIn(f"{m2}: gates satisfied - accept", self.status())
        self.assertIn(f"{m2} accepted", self.ri("accept", self.R, m2))
        self.assertIn("check OK", self.ri("check", self.R))

    def test_manuscript_revision_with_other_changes_needs_delta_paper(self):
        m1, _ = self.manuscript(self.PAPER)
        self.paper_review(m1)
        for text in (self.PAPER.replace("Step one.\n", "Step one.\nStep one and a half.\n").replace("Intro.", "Intro!"),
                     self.PAPER.replace("Intro.\n", "Intro.\nStep one and a half.\n"),  # a fill outside its section
                     self.PAPER.replace("Step one.\n", "Step one.\nStep one and a half.\nStep one and a half.\n"),
                     self.PAPER.replace("Step two.\n", "Step two.\nAn unlisted remark.\n")):
            m, out = self.manuscript(text, "--revises", m1)
            self.assertIn("revision changes more than the fills", out)
            self.assertIn("dispatch a DELTA PAPER review", out)
            self.assertNotIn("delta_review", self.state()["candidates"][m])
            self.assertIn("needs PAPER pass", self.ri("accept", self.R, m, code=1))
        m, out = self.manuscript(self.PAPER, "--revises", self.manuscript(self.PAPER)[0])  # parent without PAPER review
        self.assertNotIn("DELTA", out)

    def test_writer_and_comparator_length_warnings(self):
        c = self.accepted("Q01.R1")
        base = ri.words_in(self.path("candidates", f"{c}.md"))
        w = self.ri("task", "new", self.R, "--role", "writer", "--cand", c, "--extra", "Write.", "--start").split()[0]
        self.write(f"tasks/{w}/manuscript.md", "word " * (base + 1201))
        self.result(w, "gaps_sent_back: none")
        self.assertIn(f"warning: manuscript.md has {base + 1201} words, more than the presented candidates ({base}) "
                      "+ 1,200", self.ri("ingest", self.R, w))
        w2 = self.ri("task", "new", self.R, "--role", "writer", "--cand", c, "--extra", "Write.", "--start").split()[0]
        self.write(f"tasks/{w2}/manuscript.md", "word " * (base + 1200))
        self.result(w2, "gaps_sent_back: none")
        self.assertNotIn("warning", self.ri("ingest", self.R, w2))
        k = self.task("comparator", ctx="cmp1")
        self.write(f"tasks/{k}/selection.md", "word " * 601)
        self.result(k, f"selected: [{c}]")
        self.assertIn("warning: selection.md has 601 words for one selected candidate", self.ri("ingest", self.R, k))
        k2 = self.task("comparator", ctx="cmp2")
        self.write(f"tasks/{k2}/selection.md", "word " * 601)
        self.result(k2, f"selected: [{c}, C099]")
        self.assertNotIn("warning", self.ri("ingest", self.R, k2))

    def test_model_gate_with_question_builds_both_inputs_and_allows_light(self):
        self.r1()
        sk = self.ri("task", "new", self.R, "--role", "skeptic", "--mode", "MODEL-GATE", "--question", "Q01",
                     "--title", "M1", "--light", "--start").split()[0]
        a = self.assignment(sk)
        self.assertIn("Request: MODEL-GATE of M1: one verdict per model.\nRequest: QUESTION-GATE of Q01", a)
        for line in ("- frontier/model.md", "- contract.md (the key difference)", f"- tasks/{sk}/card-Q01.md",
                     "- lanes/Q01/statement.md", "- ledger.md", "Return: gate.md"):
            self.assertIn(line, a)
        self.assertEqual(a.count("Light gate: run QUESTION-GATE checks 1-3b only on Q01; the MODEL-GATE runs in full."), 1)
        self.assertTrue(self.state()["tasks"][sk]["light"])
        redo = self.ri("task", "new", self.R, "--redo", sk).split()[0]
        self.assertEqual(self.assignment(redo).count("Light gate"), 1)
        full = self.ri("task", "new", self.R, "--role", "skeptic", "--mode", "MODEL-GATE", "--question", "Q01",
                       "--start").split()[0]
        self.assertIn("MODEL-GATE of the models in frontier/model.md without a MODEL-GATE line", self.assignment(full))
        self.assertNotIn("Light gate", self.assignment(full))
        self.assertIn("--light is only for a skeptic QUESTION-GATE, or a MODEL-GATE with --question",
                      self.ri("task", "new", self.R, "--role", "skeptic", "--mode", "MODEL-GATE", "--light",
                              "--extra", "x", code=2))
        out = self.gate_result(full, "M1: {verdict: SOUND}", "Q01: {verdict: ADVANCE, plausibility: supported}",
                               mode="MODEL-GATE")
        self.assertIn("M1: SOUND", out)
        self.assertIn("Q01: ADVANCE (plausibility supported) -> q set RUN Q01 --plausibility supported", out)


if __name__ == "__main__":
    unittest.main()
