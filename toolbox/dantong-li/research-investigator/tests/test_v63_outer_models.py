"""Tests for the v6.3 ri.py changes of plan packages D (lazy outer work), E (MODEL-GATE handling) and
N (process triggers). Same fixture as test_ri.py (RiCase); run with the rest of the suite:

    python -B -m unittest discover -s tests
"""
import unittest
from pathlib import Path

from test_ri import RiCase, ri

TRANSFER = "claims: transfer:S03 Thm 2@M2\n\n## Statement\nS03 Thm 2 survives in M2.\n\n## Argument\nStep by step.\n"


class TestV63OuterBudget(RiCase):
    """Package D: transfer rows name their model and citer; the opening budget is warned about."""

    def setUp(self):
        super().setUp()
        self.init()

    def audit_file(self, text=TRANSFER):
        t = self.task("literature-reviewer", "TRANSFER-AUDIT", title="S03 Thm 2")
        return t, self.write(f"tasks/{t}/transfer-M2.md", text)

    def test_transfer_cand_reads_claims_line_and_records_model(self):
        self.ri("q", "add", self.R, "--title", "Does X help in M2?", "--model", "M2")
        t, f = self.audit_file()
        out = self.ri("cand", "add", self.R, "--kind", "transfer", "--file", f, "--author", t, "--for", "q1")
        c = out.split()[0]
        cand = self.state()["candidates"][c]
        self.assertEqual((cand["claims"], cand["model"], cand["for"], cand["lane"]),
                         ("transfer:S03 Thm 2@M2", "M2", "Q01", None))
        v = self.task("verifier", "ISOLATED")
        self.review(c, v, "isolated", "PASS")
        self.ri("accept", self.R, c)
        self.ri("ledger", "add", self.R, "--cand", c)
        self.assertEqual(self.state()["ledger"]["L001"]["model"], "M2")  # K80: the claim's model, not a lane's
        self.assertIn("| L001 | transfer | S03 Thm 2 survives in M2. | M2 |",
                      self.path("ledger.md").read_text(encoding="utf-8"))
        # --claims wins over the file's line; an edge has no @Mx
        c2 = self.ri("cand", "add", self.R, "--kind", "transfer", "--file", f, "--author", t, "--for", "Q01",
                     "--claims", "transfer:edge M0⪯M2").split()[0]
        self.assertEqual(self.state()["candidates"][c2]["claims"], "transfer:edge M0⪯M2")
        self.assertNotIn("model", self.state()["candidates"][c2])
        _, md = self.audit_file("# Transfer\n**claims:** `transfer:S04 Lemma 1@m3`\n## Statement\nx\n")
        c3 = self.ri("cand", "add", self.R, "--kind", "transfer", "--file", md, "--author", t, "--for", "Q01").split()[0]
        self.assertEqual((self.state()["candidates"][c3]["claims"], self.state()["candidates"][c3]["model"]),
                         ("transfer:S04 Lemma 1@m3", "M3"))
        # neither --claims nor a claims: line is a usage error; so is a malformed or unknown citer
        _, bare = self.audit_file("## Statement\nno claims line\n")
        self.assertIn("first 'claims:' line", self.ri("cand", "add", self.R, "--kind", "transfer", "--file", bare,
                                                       "--author", t, code=2))
        self.ri("cand", "add", self.R, "--kind", "transfer", "--file", f, "--author", t, "--for", "X9", code=2)
        self.ri("cand", "add", self.R, "--kind", "transfer", "--file", f, "--author", t, "--for", "Q09", code=2)

    def test_transfer_without_for_prints_lazy_gating_note(self):
        t, f = self.audit_file()
        note = "note: name the citer (--for Qxx|Hn|Cxxx): transfer rows are gated only when cited (program.md §5.4)"
        self.assertIn(note, self.ri("cand", "add", self.R, "--kind", "transfer", "--file", f, "--author", t))
        out = self.ri("cand", "add", self.R, "--kind", "transfer", "--file", f, "--author", t, "--for", "h1")
        self.assertNotIn("name the citer", out)
        self.assertEqual(self.state()["candidates"]["C002"]["for"], "H1")
        p = self.task("prover", "PROVE")
        self.ri("q", "add", self.R, "--title", "t")
        self.ri("q", "set", self.R, "Q01", "--status", "active")
        c = self.cand(p, "Q01.R1")
        self.assertNotIn("name the citer", self.ri("cand", "add", self.R, "--kind", "transfer", "--file", f,
                                                   "--author", t, "--for", c))
        self.assertNotIn("name the citer", self.ri("cand", "add", self.R, "--file", f"tasks/{p}/draft1.md",
                                                   "--author", p, "--claims", "Q01.R2"))  # not a transfer row

    def test_opening_budget_warns_above_four_audits_and_two_scouts(self):
        for _ in range(4):
            self.task("literature-reviewer", "TRANSFER-AUDIT")
        self.task("scout", "EXPLORE", title="ANCHOR S01")
        self.task("scout", "EXPLORE", title="anchor S02")
        for _ in range(2):
            self.task("scout", "EXPLORE", title="cell N1 n<=6")
        out = self.status()
        self.assertIn("opening (program.md sec. 2)", out)
        self.assertNotIn("opening budget:", out)  # the warning; the opening hint names the budget too
        self.task("literature-reviewer", "TRANSFER-AUDIT")
        self.task("scout", "EXPLORE", title="cell N2")
        out = self.status()
        self.assertIn("opening budget: 5 TRANSFER-AUDITs before the first SELECT (cap 4; investigator.md MODEL)", out)
        self.assertIn("opening budget: 3 scout EXPLOREs (not ANCHOR) before the first SELECT (cap 2; "
                      "investigator.md MODEL)", out)
        sel = self.task("investigator", "SELECT")
        self.assertIn("opening budget", self.status())  # SELECT still running
        self.ri("task", "set", self.R, sel, "done")
        self.assertNotIn("opening budget:", self.status())
        R2 = str(Path(self.tmp.name, "f"))  # focused mode has no opening budget warning
        self.R = R2
        self.ri("init", R2, "--objective", "claim", "--mode", "focused")
        for _ in range(5):
            self.task("literature-reviewer", "TRANSFER-AUDIT")
        self.assertNotIn("opening budget:", self.status())


class TestV63ModelGate(RiCase):
    """Package E: PATCH files filed verbatim as new model IDs; DEGENERATE and corrections hints."""

    MODEL_MD = "# Model cards\n## M0 baseline (S01)\n## M1 = M0 + X\n## M2 = M0 + X (variant: strong)\n"

    def setUp(self):
        super().setUp()
        self.init()
        self.write("frontier/model.md", self.MODEL_MD)

    def gate(self, *items, files=None, title="M1, M2"):
        """A finished skeptic MODEL-GATE with result items and raw-byte task files; returns (task, ingest output)."""
        t = self.task("skeptic", "MODEL-GATE", title=title)
        for name, data in (files or {}).items():
            ri.xp(self.path("tasks", t, name)).write_bytes(data)
        self.result(t, "mode: MODEL-GATE", *items)
        return t, self.ri("ingest", self.R, t)

    def test_patch_filed_verbatim_with_next_model_id(self):
        p1 = "# Patch\r\nCharge X per query; k counts distinct items \xe2\xaa\xaf.\n".encode("latin-1")
        p2 = "\ufeffDefinitions only.\n\n  - Adversary: oblivious.  ".encode("utf-8")
        t, out = self.gate("M1: {verdict: PATCH, corrections: none}", "M02: {verdict: PATCH}",
                           files={"patch-M1.md": p1, "patch-m2.md": p2})
        self.assertIn(f"filed M3 = M1 + patch ({t}): frontier/patches/M3.md; use --model M3 for questions and "
                      "lanes on M1", out)
        self.assertIn(f"filed M4 = M2 + patch ({t})", out)
        for mn, base, src in (("M3", "M1", p1), ("M4", "M2", p2)):
            got = ri.xp(self.path("frontier", "patches", f"{mn}.md")).read_bytes()
            head = f"{mn} = {base} + patch from {t} (verbatim; counts as gated)\n\n".encode("utf-8")
            self.assertEqual(got, head + src)  # byte for byte after the header
            self.assertEqual(self.state()["models"][mn], {"base": base, "task": t, "path": f"frontier/patches/{mn}.md"})
        self.assertNotIn("corrections", out)  # "corrections: none" prints nothing
        # a patch of a filed patch gets the next ID; a PATCH without its file goes to manual
        t2, out = self.gate("M3: {verdict: PATCH}", "M1: {verdict: PATCH}", files={"patch-M3.md": b"tighter\n"})
        self.assertIn(f"filed M5 = M3 + patch ({t2})", out)
        self.assertIn(f"{t2}: M1 PATCH without tasks/{t2}/patch-M1.md", out.split("manual")[1])
        self.assertEqual(sorted(self.state()["models"]), ["M3", "M4", "M5"])
        self.ri("check", self.R)

    def test_lane_on_patched_model_gets_patch_in_worker_packets(self):
        qg0 = self.ri("q", "add", self.R, "--title", "t0", "--model", "M1").split()[0]
        self.write(f"questions/{qg0}.md", f"# {qg0} — t0\nModel: M1\nR1: X helps for every n.\n")
        a = self.assignment(self.ri("task", "new", self.R, "--role", "skeptic", "--mode", "QUESTION-GATE",
                                    "--question", qg0).split()[0])
        self.assertNotIn("frontier/patches", a)
        self.gate("M1: {verdict: PATCH}", files={"patch-M1.md": b"patch one\n"})  # M3
        self.gate("M3: {verdict: PATCH}", files={"patch-M3.md": b"patch two\n"}, title="M3")  # M4 = M3 + patch
        a = self.assignment(self.ri("task", "new", self.R, "--role", "skeptic", "--mode", "QUESTION-GATE",
                                    "--question", qg0).split()[0])
        self.assertEqual(a.count("- frontier/patches/ (filed MODEL-GATE patches, verbatim; each counts as gated)"), 1)
        self.assertLess(a.index("- frontier/patches/"), a.index("Return:"))  # in the Inputs list
        for role, mode in (("skeptic", "MODEL-GATE"), ("investigator", "PROPOSE"), ("investigator", "SELECT"),
                           ("investigator", "MODEL"), ("literature-reviewer", "TRANSFER-AUDIT")):
            self.assertIn("- frontier/patches/ (filed", self.assignment(self.task(role, mode)))
        renew = self.assignment(self.ri("task", "new", self.R, "--role", "investigator", "--mode", "RENEW").split()[0])
        self.assertLess(renew.index("- frontier/patches/ (filed"), renew.index("Return:"))
        self.assertNotIn("frontier/patches", self.assignment(self.task("investigator", "BREADTH")))
        self.ri("q", "set", self.R, qg0, "--status", "active", "--model", "M4")
        self.ri("round", self.R, qg0, "--open")
        m3 = "- frontier/patches/M3.md (patch of M1, verbatim; it amends the statement's model)"
        m4 = "- frontier/patches/M4.md (patch of M3, verbatim; it amends the statement's model)"
        pr = self.ri("task", "new", self.R, "--role", "prover", "--direction", "PROVE Q01.R1").split()[0]
        a = self.assignment(pr)
        self.assertLess(a.index(m3), a.index(m4))  # the base patch first
        self.assertLess(a.index(m4), a.index("Return:"))
        self.assertIn(m4, self.assignment(self.ri("task", "new", self.R, "--role", "summarizer", "--direction",
                                                  "PROVE Q01.R1").split()[0]))
        c = self.cand(pr, "Q01.R1")
        for mode in ("INDIVIDUAL", "ISOLATED"):
            self.assertIn(m4, self.assignment(self.ri("task", "new", self.R, "--role", "verifier", "--mode", mode,
                                                      "--cand", c).split()[0]))
        self.assertIn(m4, self.assignment(self.ri("task", "new", self.R, "--role", "scout", "--mode", "SANITY",
                                                  "--cand", c).split()[0]))
        hand = self.write("assign.txt", "Request: PROVE Q01.R2.\nInputs (open by path):\n- lanes/Q01/statement.md\n")
        h = self.ri("task", "new", self.R, "--role", "prover", "--lane", qg0, "--assignment-file", hand).split()[0]
        self.assertIn(m4, self.assignment(h))  # every worker packet of the lane, hand-written ones too
        redo = self.ri("task", "new", self.R, "--redo", h).split()[0]
        self.assertEqual(self.assignment(redo).count(m4), 1)
        self.assertIn(m4, self.assignment(self.task("ledger-auditor", lane=qg0)))
        adj_c = self.cand(pr, "Q01.R2")
        v = self.task("verifier", "INDIVIDUAL", lane=qg0)
        self.review(adj_c, v, "individual", "FAIL", "--blocking", "O1 CRITICAL: Lemma 1 [ALG] - wrong")
        self.assertIn(m4, self.assignment(self.ri("task", "new", self.R, "--role", "verifier", "--mode", "ADJUDICATE",
                                                  "--objection", f"{v}.O1").split()[0]))
        q2 = self.ri("q", "add", self.R, "--title", "t2", "--model", "M1").split()[0]  # an unpatched model
        self.ri("q", "set", self.R, q2, "--status", "active")
        self.ri("round", self.R, q2, "--open")
        a = self.assignment(self.ri("task", "new", self.R, "--role", "prover", "--direction", "PROVE Q02.R1").split()[0])
        self.assertNotIn("frontier/patches", a)

    def test_degenerate_m1_argument_frozen_as_transfer_candidate(self):
        arg = b"## Statement\nWith k >= 1 the task is trivial in M1.\n## Proof\nEncode the answer in X.\n"
        t, out = self.gate("M1: {verdict: DEGENERATE, corrections: none}", "M2: {verdict: DEGENERATE}",
                           files={"degenerate-M1.md": arg, "degenerate-M2.md": b"also trivial\n"})
        st = self.state()
        self.assertEqual(sorted(st["candidates"]), ["C001"])  # only M1's argument is frozen
        c = st["candidates"]["C001"]
        self.assertEqual((c["kind"], c["claims"], c["author"], c["model"], c["lane"]),
                         ("transfer", f"transfer:degenerate M1 ({t})@M1", t, "M1", None))
        self.assertEqual(ri.xp(self.path("candidates", "C001.md")).read_bytes(), arg)
        self.assertIn("task new --role verifier --mode ISOLATED --cand C001 --start; report now in progress.md §1 "
                      "and How I read your request (K25)", out)
        self.assertIn("candidate (skeptic argument; check pending)", out)
        self.assertEqual(out.count("apply-verdicts MODEL (at most once at opening; program.md §5.2)"), 2)
        self.assertNotIn("name the citer", out)
        v = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "ISOLATED", "--cand", "C001", "--start").split()[0]
        self.review("C001", v, "isolated", "PASS")
        self.ri("accept", self.R, "C001")
        _, out = self.gate("M1: {verdict: DEGENERATE}")  # the argument file is missing
        self.assertIn("M1 DEGENERATE without tasks/", out.split("manual")[1])

    def test_corrections_and_degenerate_hints_printed(self):
        _, out = self.gate("M1: {verdict: SOUND, corrections: c(inf) = 1/2, not 1; k_triv = n}",
                           "M2: {verdict: SOUND, corrections: none}", "M0: SOUND", "too_easy: none")
        self.assertIn("M1 corrections: copy verbatim under M1 in How I read your request (program.md §5.2); the "
                      "next SELECT or RENEW applies them", out)
        self.assertNotIn("M2 corrections", out)
        self.assertNotIn("M0 corrections", out)
        self.assertNotIn("manual", out)
        self.assertIn("too_easy: none", out)  # other fields are still shown
        _, out = self.gate("M2: {verdict: DEGENERATE, corrections: endpoint c(0) is 2}", "M1: {verdict: MAYBE}")
        self.assertIn("M2 DEGENERATE: apply-verdicts MODEL (at most once at opening; program.md §5.2)", out)
        self.assertIn("M2 corrections: copy verbatim under M2", out)
        self.assertIn("M1: unknown MODEL-GATE verdict 'MAYBE'", out.split("manual")[1])
        self.assertEqual(ri.item_fields("{verdict: SOUND, corrections: c(inf) = 1/2, not 1}"),
                         {"verdict": "SOUND", "corrections": "c(inf) = 1/2, not 1"})
        self.assertEqual(ri.item_fields("PATCH"), {"verdict": "PATCH"})


class TestV63Triggers(RiCase):
    """Package N: run-wide process advisor, vetting questions in queue-low, breadth by tasks, BREADTH note."""

    def setUp(self):
        super().setUp()
        self.init()

    def finish(self, n, role="scout", mode="EXPLORE"):
        """n finished tasks with a result.md each; returns their IDs."""
        ids = []
        for _ in range(n):
            t = self.task(role, mode)
            self.result(t)
            self.ri("task", "set", self.R, t, "done")
            ids.append(t)
        return ids

    def selected(self):
        sel = self.task("investigator", "SELECT")
        self.result(sel)
        self.ri("task", "set", self.R, sel, "done")
        return sel

    def test_runwide_advisor_due_after_first_select_and_after_20_tasks(self):
        early = self.finish(2, "literature-reviewer", "SURVEY")
        self.assertNotIn("process advisor due (run-wide", self.status())  # before the first SELECT
        sel = self.selected()
        self.assertIn("process advisor due (run-wide: the first SELECT finished and no advisor has run): task new "
                      "--role process-advisor --title run-wide --start", self.status())
        adv = self.ri("task", "new", self.R, "--role", "process-advisor", "--title", "run-wide", "--start").split()[0]
        a = self.assignment(adv)
        for k in early:
            self.assertIn(f"- tasks/{k}/result.md (literature-reviewer SURVEY)", a)
        self.assertIn(f"- tasks/{sel}/result.md (investigator SELECT)", a)
        self.assertIn("Run-wide: standing instructions only; allocation_advice: none unless a lane round closed.", a)
        self.assertLess(a.index("Run-wide:"), a.index("Return:"))
        self.assertNotIn("process advisor due (run-wide", self.status())  # an advisor is live
        self.ri("task", "set", self.R, adv, "done")
        self.assertNotIn("process advisor due (run-wide", self.status())
        ids = self.finish(19)
        self.assertNotIn("process advisor due (run-wide", self.status())
        ids += self.finish(1)
        self.assertIn(f"process advisor due (run-wide: 20 tasks finished since advisor {adv})", self.status())
        a = self.assignment(self.ri("task", "new", self.R, "--role", "process-advisor", "--title", "run-wide").split()[0])
        self.assertIn(f"- tasks/<T>/result.md for T in {ids[0]}-{ids[-1]} (20 tasks finished since advisor {adv})", a)
        self.assertNotIn(f"tasks/{sel}/result.md", a)
        plain = self.assignment(self.ri("task", "new", self.R, "--role", "process-advisor").split()[0])
        self.assertNotIn("Run-wide", plain)  # a lane-round advisor's packet is unchanged

    def test_runwide_advisor_waits_for_a_due_round_advisor_and_ignores_cancelled_ones(self):
        self.selected()
        gone = self.task("process-advisor", title="run-wide")
        self.ri("task", "set", self.R, gone, "cancelled")
        self.assertIn("run-wide: the first SELECT finished", self.status())
        self.ri("q", "add", self.R, "--title", "t")
        self.ri("q", "set", self.R, "Q01", "--status", "active")
        self.ri("round", self.R, "Q01", "--open")
        p = self.task("prover", "PROVE", lane="Q01")
        c = self.cand(p, "Q01.R1")
        v = self.task("verifier", "INDIVIDUAL", lane="Q01")
        self.review(c, v, "individual", "FAIL", "--blocking", "O1 CRITICAL: Lemma 3 [PROB] - fails")
        x = self.task("verifier", "SECOND-INDEPENDENT", lane="Q01")
        self.review(c, x, "cross", "FAIL", "--blocking", "O1 CRITICAL: Lemma 3 [PROB] - fails")
        self.ri("task", "set", self.R, p, v, x, "done")
        out = self.status()
        self.assertIn("process advisor due (reviews since the last advisor task): Q01 r1", out)
        self.assertNotIn("process advisor due (run-wide", out)

    def test_queue_low_counts_vetting_questions(self):
        R2 = str(Path(self.tmp.name, "r2"))
        self.ri("init", R2, "--objective", "x", "--k", "8")
        self.R = R2
        self.selected()
        for status in ("ready", "vetting"):
            q = self.ri("q", "add", self.R, "--title", status).split()[0]
            self.ri("q", "set", self.R, q, "--status", status)
        self.assertIn("queue low (1 ready + 1 vetting < 4 free lanes): event --type queue-low, then a proposal sweep",
                      self.status())
        for _ in range(2):
            q = self.ri("q", "add", self.R, "--title", "v").split()[0]
            self.ri("q", "set", self.R, q, "--status", "vetting")
        self.assertNotIn("queue low", self.status())  # 1 + 3 vetting fill the 4 free lanes

    def test_breadth_review_due_after_30_tasks_since_first_select(self):
        before = self.task("scout", "EXPLORE")  # created before the SELECT: does not count
        self.finish(31)
        self.assertNotIn("breadth-review", self.status())  # no SELECT yet
        self.selected()
        self.result(before)
        self.ri("task", "set", self.R, before, "done")
        self.finish(29)
        self.assertNotIn("breadth-review", self.status())
        self.finish(1)
        self.assertIn("30 tasks finished since the first SELECT (30+): event --type breadth-review", self.status())
        self.ri("event", self.R, "--type", "breadth-review")
        self.assertNotIn("tasks finished since", self.status())
        self.finish(30)
        self.assertIn("30 tasks finished since the last breadth review (30+): event --type breadth-review",
                      self.status())

    def test_breadth_task_note_without_event(self):
        note = ("note: BREADTH is scheduled by the breadth-review event (program.md §7), before an exhaustion claim, "
                "or on a user request")
        self.assertIn(note, self.ri("task", "new", self.R, "--role", "investigator", "--mode", "BREADTH"))
        e = self.ri("event", self.R, "--type", "breadth-review").split()[0]
        b = self.ri("task", "new", self.R, "--role", "investigator", "--mode", "BREADTH")
        self.assertNotIn("note: BREADTH", b)
        self.ri("event", self.R, "--handled", e, "--by", b.split()[0])
        self.assertIn(note, self.ri("task", "new", self.R, "--role", "investigator", "--mode", "BREADTH"))
        self.assertNotIn("note: BREADTH", self.ri("task", "new", self.R, "--role", "investigator", "--mode", "SELECT"))


if __name__ == "__main__":
    unittest.main()
