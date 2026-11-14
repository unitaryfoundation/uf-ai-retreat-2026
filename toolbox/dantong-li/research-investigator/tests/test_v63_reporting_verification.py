"""Tests for the v6.3 ri.py packages I, J, K, L and O (plan sections 10-13 and 16).

Run with the whole suite: python -B -m unittest discover -s tests   (from the skill directory)
"""
import hashlib
import os
import time
import unittest
from pathlib import Path

from test_ri import RiCase, ri


class TestV63Hygiene(RiCase):
    """Package I: manual fallback and lean reading (K18, K55)."""

    def setUp(self):
        super().setUp()
        self.init()

    def test_check_warns_on_long_checkpoint_notes_without_failing(self):
        self.status()  # fills the status block, which never counts as notes
        out = self.ri("check", self.R)
        self.assertIn("check OK", out)
        self.assertNotIn("warning", out)
        cp = self.path("checkpoint.md")
        text = cp.read_text(encoding="utf-8") + "".join(f"- note {i}\n" for i in range(70))
        cp.write_text(text, encoding="utf-8")
        out = self.ri("check", self.R)  # exit 0: warnings never fail the check
        self.assertIn("warning: checkpoint.md has 77 non-empty lines outside the status block (at most about 60)", out)
        self.assertIn("check OK", out)
        cp.write_text(text.replace("## Next actions\n", ""), encoding="utf-8")
        self.assertIn("warning: checkpoint.md has no '## Next actions' heading", self.ri("check", self.R))
        with open(self.path("log.jsonl"), "a", encoding="utf-8") as f:  # a finding: the exit code is the findings'
            f.write('{"seq": 1, "cmd": "forged"}\n')
        out = self.ri("check", self.R, code=1)
        self.assertIn("warning: checkpoint.md has no '## Next actions' heading", out)
        self.assertIn("finding(s)", out)

    def test_ingest_brief_prints_only_status_and_left_lines(self):
        self.lane()
        p = self.task("prover", "PROVE", lane="Q01", ctx="p1")
        self.write(f"tasks/{p}/draft.md", "# Theorem\nProof.\n")
        self.result(p, "direction: PROVE Q01.R1", "claims: Q01.R1", "kind: proof", "rebuttals: T009.O1")
        out = self.ri("ingest", self.R, p, "--brief")
        self.assertEqual(out.splitlines()[0], f"{p} prover PROVE: done - test result")
        self.assertIn("dispatch ADJUDICATE for T009.O1", out)
        self.assertNotIn("C001 frozen", out)
        self.assertEqual(len(out.splitlines()), 2)
        self.assertIn("C001", self.state()["candidates"])  # --brief shortens only the printout
        v = self.task("verifier", "INDIVIDUAL", lane="Q01", ctx="v1")
        self.result(v, "scope: INDIVIDUAL", "review C001: verdict=PASS; fidelity=MATCH", "too_easy C001: c-inf")
        gone = self.task("scout", ctx="s1")
        lines = self.ri("ingest", self.R, v, gone, "--brief").splitlines()
        self.assertEqual(lines[0], f"{v} verifier INDIVIDUAL: done - test result")
        self.assertTrue(lines[1].strip().startswith("too_easy C001: c-inf -> event --type too-easy"), lines)
        self.assertEqual(lines[2], "manual (handle by hand):")
        self.assertIn(f"{gone}: no tasks/{gone}/result.md", lines[3])
        self.assertEqual(len(lines), 4)
        self.assertEqual([r["task"] for r in self.state()["reviews"]], [v])


class TestV63Reporting(RiCase):
    """Packages J (K07, K08) and K (K12, K13, K46)."""

    def setUp(self):
        super().setUp()
        self.init()

    def progress(self, body):
        head = self.path("progress.md").read_text(encoding="utf-8").splitlines()[0]
        self.write("progress.md", f"{head}\n# Progress\nState: running.\n\n{body}")

    def test_init_progress_has_no_placeholders(self):
        text = self.path("progress.md").read_text(encoding="utf-8")
        self.assertNotRegex(text, r"<[A-Za-z]")
        self.assertEqual(text.splitlines()[2], "State: initialised; nothing dispatched yet.")
        self.assertIn("## 2. Picture\n(not yet drawn)\n", text)
        out = self.ri("check", self.R, "--progress")
        self.assertIn("check OK", out)
        self.assertNotIn("warning", out)
        self.assertEqual(ri.progress_findings(self.R, self.state()), [])
        old = text.replace("(not yet drawn)", "<per main model: known ACH and IMP bounds against the amount of X\n"
                                              "(from frontier/map.md), with 2-3 sentences on what changed>")
        self.write("progress.md", old)
        self.assertIn("warning: progress.md: template text left: '<per main model", self.ri("check", self.R, "--progress"))
        self.write("progress.md", text)
        m = self.task("investigator", "MODEL")
        self.write(f"tasks/{m}/reading.md", "How I read your request.")
        self.ri("task", "set", self.R, m, "done")
        self.assertEqual(ri.progress_findings(self.R, self.state()), [f"'(not yet drawn)' while {m} returned reading.md"])

    def test_progress_lint_flags_ids_long_sentences_runons_and_unlabelled_claims(self):
        long_ = "This " + "long " * 33 + "sentence."
        self.progress(
            "## 1. What is now known\n"
            "C014 settles the first case.\n"
            "The bound holds for all960 instances. Its sha256 digest is fixed.\n"
            "We proved the lower bound.\n"
            "- The new construction improves the ratio to 3/2 (agent-checked).\n"
            f"- {long_}\n"
            "```\nC999 proved all960\n```\n"
            "## 3. Frontier before/after\n"
            "| c(0) | 2, cited (S03; theorem) | 3/2 | conjecture (audit T012; SURVIVES, ungated) |\n"
            "| " + "wide " * 40 + "| cell |\n"
            "## How I read your request\n"
            "T012 checks the model.\n"
            "## 5. Results with assurance profiles\n"
            "C014 proved this, outside the sections the lint reads.\n")
        found = ri.progress_findings(self.R, self.state())
        expected = ["bare IDs C014 in sec. 1", "run-on all960 in sec. 1", "'proved' without an I5 label",
                    "a 35-word sentence in sec. 1", "bare IDs T012 in 'How I read your request'"]
        self.assertEqual(len(found), len(expected), found)
        for needle, line in zip(expected, found):
            self.assertIn(needle, line)
        out = self.ri("check", self.R, "--progress")
        self.assertEqual(out.count("warning: progress.md: "), 5)
        self.assertIn("check OK", out)

    def test_progress_older_than_last_acceptance_is_flagged(self):
        self.lane()
        p = self.path("progress.md")
        text = p.read_text(encoding="utf-8")
        old = time.time() - 3600
        os.utime(p, (old, old))
        self.assertEqual(ri.progress_findings(self.R, self.state()), [])
        c = self.accepted("Q01.R1")
        found = ri.progress_findings(self.R, self.state())
        self.assertIn(f"'(nothing established yet)' while {c} is accepted", found)
        self.assertIn(f"older than the last acceptance ({c}): rewrite it whole", found)
        self.assertIn(f"progress.md: older than the last acceptance ({c})", self.status())
        self.write("progress.md", text.replace("(nothing established yet)", "The first claim holds (agent-checked)."))
        self.assertEqual(ri.progress_findings(self.R, self.state()), [])

    def test_status_shows_at_most_three_progress_lint_lines(self):
        self.progress("## 1. What is now known\n" + "".join(f"C01{i} is open.\n" for i in range(5)))
        acts = self.status().split("SUGGESTED NEXT ACTIONS:")[1].splitlines()
        lint = [x for x in acts if x.startswith("  - progress.md: ")]
        self.assertEqual(len(lint), 3)
        self.assertTrue(lint[-1].endswith("(+2 more: check RUN --progress)"), lint)
        self.assertEqual(self.ri("check", self.R, "--progress").count("warning: progress.md: bare IDs"), 5)

    def test_templates_carry_frame_and_gap_step_lines(self):
        lines = self.path("frontier", "model.md").read_text(encoding="utf-8").splitlines()
        i = next(n for n, x in enumerate(lines) if x.startswith("Change:"))
        self.assertEqual(lines[i + 1], "Frame: RESOURCE-CURVE | ON-OFF | COMBINATION (frontier-method.md §1)")
        q = self.ri("q", "add", self.R, "--title", "t").split()[0]
        card = self.path("questions", f"{q}.md").read_text(encoding="utf-8")
        self.assertIn("\nR3: <lowest rung not implied by the nearest known result, closable in 1–2 rounds>\n", card)
        self.assertIn("Nearest known result: <locator>; gap step: <the step R1 needs beyond it>\n", card)
        self.assertIn("Lineage: parent <Qxx | user | prior program>;", card)

    def test_question_gate_notes_missing_gap_step_for_successor_cards(self):
        gate = lambda *qs: self.ri("task", "new", self.R, "--role", "skeptic", "--mode", "QUESTION-GATE",
                                   "--question", ",".join(qs))
        seed = self.ri("q", "add", self.R, "--title", "seed").split()[0]
        self.r1(seed)  # a QUESTION-GATE needs an exact R1 (Package B, K14)
        self.assertNotIn("gap step", gate(seed))  # a seed before the first SELECT
        succ = self.ri("q", "add", self.R, "--title", "s", "--parent", seed, "--operator", "STRENGTHEN").split()[0]
        self.r1(succ)
        out = gate(seed, succ)
        self.assertIn(f"note: {succ} has no gap step (FM §5); the skeptic tests it first; ask the next SELECT or "
                      "RENEW to fill it", out)
        self.assertNotIn(f"note: {seed}", out)
        card = self.path("questions", f"{succ}.md")
        card.write_text(card.read_text(encoding="utf-8").replace(
            "gap step: <the step R1 needs beyond it>", "gap step: the LP dual for k >= 2"), encoding="utf-8")
        self.assertNotIn("gap step (FM", gate(succ))
        sel = self.task("investigator", "SELECT")
        late = self.ri("q", "add", self.R, "--title", "picked").split()[0]
        self.r1(late)
        self.assertNotIn("gap step (FM", gate(late))  # the SELECT has not finished
        self.ri("task", "set", self.R, sel, "done")
        out = self.ri("task", "new", self.R, "--role", "skeptic", "--mode", "QUESTION-GATE", "--light",
                      "--question", late)  # exit 0: a note, never a refusal
        self.assertIn(f"note: {late} has no gap step (FM §5)", out)

    def test_queue_low_hint_names_a_constructive_lens(self):
        self.ri("task", "set", self.R, self.task("investigator", "SELECT"), "done")
        out = self.ri("event", self.R, "--type", "queue-low")
        self.assertIn("one of them constructive (program.md sec. 5.1)", out)
        out = self.status("--full")
        self.assertIn("E1 queue-low: proposal sweep with the 2 least-recently used lenses, one of them constructive "
                      "(program.md sec. 5.1), then SELECT; then event --handled", out)
        self.assertIn("-> first: proposal sweep with the 2 least-recently used lenses, one of them constructive", out)


class TestV63Verification(RiCase):
    """Package L: verification tightening (K42, K43, K61, K66)."""

    def setUp(self):
        super().setUp()
        self.init()
        self.lane()

    def transfer(self, claim="transfer:S03 Thm 2@M1", lr=None):
        lr = lr or self.task("literature-reviewer", "TRANSFER-AUDIT")
        return self.cand(lr, claim, "--kind", "transfer"), lr

    def isolated(self, cid, *lines):
        iso = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "ISOLATED", "--cand", cid,
                      "--start").split()[0]
        self.write(f"tasks/{iso}/review.md", "review")
        self.result(iso, "scope: ISOLATED", f"review {cid}: verdict=PASS; fidelity=MATCH", *lines,
                    "artifacts: [review.md]")
        return iso, self.ri("ingest", self.R, iso, "--accept")

    def test_attachments_are_hashed_and_tampering_blocks_acceptance(self):
        p = self.task("prover", "PROVE", lane="Q01")
        self.write(f"tasks/{p}/certs.json", '{"lp": "dual"}')
        self.write(f"tasks/{p}/check.py", "print(1)")
        c = self.cand(p, "Q01.R1", "--attach", f"tasks/{p}/certs.json", f"tasks/{p}/check.py")
        atts = self.state()["candidates"][c]["attachments"]
        self.assertEqual([a["path"] for a in atts], [f"candidates/{c}/certs.json", f"candidates/{c}/check.py"])
        self.assertEqual(atts[0]["sha256"], hashlib.sha256(b'{"lp": "dual"}').hexdigest())
        self.assertEqual(self.path("candidates", c, "certs.json").read_text(encoding="utf-8"), '{"lp": "dual"}')
        self.write(f"tasks/{p}/sub/certs.json", "{}")
        self.assertIn("two attachments are named certs.json", self.ri(
            "cand", "add", self.R, "--file", f"tasks/{p}/certs.json", "--author", p, "--claims", "Q01.R2",
            "--attach", f"tasks/{p}/certs.json", f"tasks/{p}/sub/certs.json", code=2))
        v1 = self.ri("task", "new", self.R, "--role", "verifier", "--mode", "INDIVIDUAL", "--cand", c).split()[0]
        self.assertIn(f"- candidates/{c}/certs.json (attachment of {c}, frozen)", self.assignment(v1))
        self.review(c, v1, "individual", "PASS")
        self.review(c, self.task("verifier", "CROSS-DRAFT", lane="Q01"), "cross", "PASS")
        self.write(f"candidates/{c}/certs.json", '{"lp": "forged"}')
        stale = f"attachment candidates/{c}/certs.json changed since freeze (stale): add a new candidate"
        self.assertIn(stale, self.ri("accept", self.R, c, code=1))
        self.assertIn(stale, self.ri("check", self.R, code=1))
        self.assertIn("stale", self.review(c, self.task("verifier", "SECOND-INDEPENDENT", lane="Q01"), "cross", "PASS",
                                           code=1))
        self.write(f"candidates/{c}/certs.json", '{"lp": "dual"}')
        self.assertIn(f"{c} accepted", self.ri("accept", self.R, c))
        self.assertIn("check OK", self.ri("check", self.R))

    def test_ingest_prover_data_field_attaches_files(self):
        p = self.task("prover", "PROVE", lane="Q01", ctx="p1")
        self.write(f"tasks/{p}/draft.md", "# Theorem\nBy the certificate.\n")
        self.write(f"tasks/{p}/certs.json", "{}")
        self.result(p, "direction: PROVE Q01.R1", "claims: Q01.R1", "kind: proof",
                    "data: [certs.json, missing.csv]   # files a computer-assisted step uses")
        out = self.ri("ingest", self.R, p)
        c = self.state()["candidates"]["C001"]
        self.assertEqual(c["attachments"], [{"path": "candidates/C001/certs.json",
                                             "sha256": hashlib.sha256(b"{}").hexdigest()}])
        self.assertIn("attachments candidates/C001/certs.json", out)
        self.assertIn(f"{p}: data file missing.csv not found; C001 was frozen without it", out.split("manual")[1])
        p2 = self.task("prover", "PROVE", lane="Q01", ctx="p2")
        self.write(f"tasks/{p2}/draft.md", "# Theorem\nProof.\n")
        self.result(p2, "direction: PROVE Q01.R2", "claims: Q01.R2", "kind: proof", "data: none")
        self.assertNotIn("manual", self.ri("ingest", self.R, p2))
        self.assertNotIn("attachments", self.state()["candidates"]["C002"])

    def test_individual_salvage_second_independent_take_one_candidate(self):
        p = self.task("prover", "PROVE", lane="Q01")
        c1, c2 = self.cand(p, "Q01.R1"), self.cand(p, "Q01.R2")
        for mode in ("INDIVIDUAL", "SALVAGE", "SECOND-INDEPENDENT"):
            out = self.ri("task", "new", self.R, "--role", "verifier", "--mode", mode, "--cand", f"{c1},{c2}", code=1)
            self.assertIn(f"{mode} takes one candidate per task", out)
            self.ri("task", "new", self.R, "--role", "verifier", "--mode", mode, "--cand", c1)
        self.assertEqual(len(self.state()["tasks"]), 4)

    def test_cross_draft_refuses_candidates_from_two_lanes_or_rounds(self):
        cross = lambda *cs, code=0: self.ri("task", "new", self.R, "--role", "verifier", "--mode", "CROSS-DRAFT",
                                            "--cand", ",".join(cs), code=code)
        c1 = self.cand(self.task("prover", "PROVE", lane="Q01"), "Q01.R1")
        q2 = self.lane("Other question")
        c2 = self.cand(self.task("prover", "PROVE", lane=q2), f"{q2}.R1")
        self.assertIn(f"a CROSS-DRAFT covers one lane round's cohort (program.md sec. 5.2); {c1}, {c2} span Q01 r1, "
                      f"{q2} r1", cross(c1, c2, code=1))
        self.ri("round", self.R, "Q01", "--open")
        c3 = self.cand(self.task("prover", "PROVE", lane="Q01"), "Q01.R2")
        self.assertIn("span Q01 r1, Q01 r2", cross(c1, c3, code=1))
        c4 = self.cand(self.task("prover", "PROVE", lane="Q01"), "Q01.R1")
        cross(c3, c4)

    def test_transfer_with_new_argument_needs_second_isolated_pass(self):
        tr, lr = self.transfer()
        iso, out = self.isolated(tr, f"new_argument {tr}: yes")
        self.assertIn(f"new_argument {tr}: yes -> a second ISOLATED pass from another fresh task is needed", out)
        self.assertNotIn(f"accepted: {tr}", out)
        self.assertIs(self.state()["reviews"][0]["new_argument"], True)
        self.assertIn("needs a second ISOLATED pass (new_argument: yes)", self.ri("accept", self.R, tr, code=1))
        self.assertIn(f"{tr} (second pass: new_argument yes): needs ISOLATED review (not by {lr}, {iso})", self.status())
        iso2, out = self.isolated(tr, f"new_argument {tr}: no")
        self.assertIn(f"accepted: {tr} accepted", out)
        tr2, _ = self.transfer("transfer:S03 Lemma 4@M1", lr)
        _, out = self.isolated(tr2, f"new_argument {tr2}: no")  # a re-reading of the source proof: one pass
        self.assertIn(f"accepted: {tr2} accepted", out)

    def test_selected_candidate_closure_is_load_bearing(self):
        tr, _ = self.transfer()
        self.review(tr, self.task("verifier", "ISOLATED"), "isolated", "PASS")
        self.ri("accept", self.R, tr)
        self.ri("ledger", "add", self.R, "--cand", tr)  # L001
        c = self.accepted("Q01.R2", "--deps", "L001")
        self.assertNotIn("load-bearing", self.status())
        cmp_ = self.task("comparator", ctx="cmp")
        self.result(cmp_, f"selected: [{c}]")
        self.assertIn(f"presented: {c}", self.ri("ingest", self.R, cmp_))
        self.assertEqual(self.state()["selected"], [c])
        self.assertIn(f"L001: load-bearing - dispatch a second ISOLATED review of {tr}", self.status())
        self.assertIn("load-bearing", self.path("ledger.md").read_text(encoding="utf-8"))
        src = self.cand(self.task("prover", "PROVE", lane="Q01"), "Q01.R1")
        frag = self.cand(self.task("ledger-auditor", lane="Q01"), None, "--from", src)
        self.review(frag, self.task("verifier", "ISOLATED"), "isolated", "PASS")
        self.ri("accept", self.R, frag)
        self.ri("ledger", "add", self.R, "--cand", frag)  # L002
        c3 = self.accepted("Q01.R3", "--deps", "L002")  # below R1, with no comparator
        self.assertNotIn("L002: load-bearing", self.status())
        self.ri("task", "new", self.R, "--role", "writer", "--cand", c3, "--extra", "Write the paper.")
        self.assertEqual(self.state()["selected"], [c, c3])
        self.assertIn(f"L002: load-bearing - dispatch a second ISOLATED review of {frag}", self.status())

    def test_status_batches_isolated_transfer_gates_into_one_command(self):
        t1, lr = self.transfer()
        t2, _ = self.transfer("transfer:S03 Lemma 4@M1", lr)
        out = self.status()
        self.assertIn(f"{t1}, {t2}: needs ISOLATED review (not by {lr}) - one task for all: task new RUN --role "
                      f"verifier --mode ISOLATED --cand {t1},{t2} --start", out)
        self.assertNotIn(f"{t1}: needs ISOLATED", out)
        self.ri("task", "new", self.R, "--role", "verifier", "--mode", "ISOLATED", "--cand", t1)
        out = self.status()
        self.assertIn(f"{t2}: needs ISOLATED review (not by {lr}) - one task for all: task new RUN --role verifier "
                      f"--mode ISOLATED --cand {t2} --start", out)
        self.assertNotIn(f"{t1}, {t2}", out)


class TestV63Fixes(RiCase):
    """Package O: ri.py fixes (K51, K78, K79, K80, K81)."""

    def setUp(self):
        super().setUp()
        self.init()

    def test_status_no_write_leaves_checkpoint_unchanged(self):
        cp = self.path("checkpoint.md")
        before = cp.read_bytes()
        self.assertIn("SUGGESTED NEXT ACTIONS", self.status("--no-write"))
        self.assertIn("next:", self.status("--brief", "--no-write"))
        self.assertEqual(cp.read_bytes(), before)
        self.status()
        self.assertNotEqual(cp.read_bytes(), before)

    def test_program_opening_hint_names_fast_start_and_seed_gate(self):
        self.assertIn("opening (program.md sec. 2): intake (seeds in priority order) -> SURVEY + LANDSCAPE + scout "
                      "ANCHOR + one light QUESTION-GATE on primary claim seeds (fast start: the first ADVANCE opens as "
                      "the foothold lane) -> MODEL (R1s for primary direction seeds; opening budget) -> MODEL-GATEs "
                      "(ingest files patches) -> one batched full QUESTION-GATE on primary seeds + PROPOSE x2-4 after "
                      "LANDSCAPE -> SELECT -> QUESTION-GATEs; open a lane as soon as one question is ready",
                      self.status("--full"))

    def test_second_accept_of_same_rung_updates_the_event(self):
        self.lane()
        c1 = self.accepted("Q01.R2")
        events = lambda: [e for e in self.state()["events"] if e["type"] == "rung-accepted"]
        self.assertEqual([(e["id"], e["claim"]) for e in events()], [("E1", "Q01.R2")])
        renew = self.task("investigator", "RENEW")
        self.ri("event", self.R, "--handled", "E1", "--by", renew)
        p = self.task("prover", "PROVE", lane="Q01")
        c2 = self.cand(p, "Q01.R2")
        self.review(c2, self.task("verifier", "INDIVIDUAL", lane="Q01"), "individual", "PASS")
        self.review(c2, self.task("verifier", "CROSS-DRAFT", lane="Q01"), "cross", "PASS")
        self.assertIn("rung-accepted Q01 already logged (E1): note updated", self.ri("accept", self.R, c2))
        (e,) = events()
        self.assertEqual(e["note"], f"{c1} accepted for Q01.R2; lane continues on R1; also {c2} accepted")
        self.assertEqual(e["handled_by"], renew)
        self.accepted("Q01.R1")
        self.assertEqual([e["type"] for e in self.state()["events"]], ["rung-accepted", "top-accepted"])

    def test_withdrawn_task_gets_no_reconcile_hint_and_needs_a_note(self):
        t = self.task("scout")
        self.assertIn(f"{t}: queued scout", self.status())
        self.assertIn("withdrawn needs --note", self.ri("task", "set", self.R, t, "withdrawn", code=2))
        self.ri("task", "set", self.R, t, "--status", "withdrawn", "--note", "never spawned: host limit")
        self.assertEqual(self.state()["tasks"][t]["status"], "withdrawn")
        self.assertNotIn(f"{t}:", self.status())
        d = self.task("scout")
        self.ri("task", "set", self.R, d, "done")
        self.assertIn("only a queued or running task without result.md", self.ri(
            "task", "set", self.R, d, "withdrawn", "--note", "x", code=1))
        r = self.task("scout", ctx="s1")
        self.write(f"tasks/{r}/result.md", "---\nstatus: completed\n---\n")
        self.ri("task", "set", self.R, r, "withdrawn", "--note", "x", code=1)
        self.lane()
        c = self.cand(self.task("prover", "PROVE", lane="Q01"), "Q01.R1")
        v = self.task("verifier", "INDIVIDUAL", lane="Q01")
        self.review(c, v, "individual", "FAIL", "--blocking", "O1 CRITICAL: Lemma 3 [PROB] - fails")
        x = self.task("verifier", "SECOND-INDEPENDENT", lane="Q01")
        self.review(c, x, "cross", "FAIL", "--blocking", "O1 CRITICAL: Lemma 3 [PROB] - fails")
        for k, t_ in self.state()["tasks"].items():
            if t_["status"] in ri.LIVE and t_["role"] != "scout":
                self.ri("task", "set", self.R, k, "done")
        due = "process advisor due (reviews since the last advisor task): Q01 r1"
        self.assertIn(due, self.status())
        adv = self.task("process-advisor")
        self.assertNotIn(due, self.status())
        self.ri("task", "set", self.R, adv, "withdrawn", "--note", "never spawned")
        self.assertIn(due, self.status())

    def test_record_confirmed_steps_exclude_manuscript_reviews(self):
        self.lane()
        c = self.cand(self.task("prover", "PROVE", lane="Q01"), "Q01.R1")
        self.review(c, self.task("verifier", "INDIVIDUAL", lane="Q01"), "individual", "FAIL",
                    "--blocking", "O1 CRITICAL: Lemma 3 - fails", "--confirmed", "Lemma 2")
        m = self.cand(self.task("writer"), "Q01.R1", "--kind", "manuscript")
        self.review(m, self.task("verifier", "PAPER"), "paper", "PASS", "--confirmed", "Theorem 1")
        record = self.path("lanes", "Q01", "record.md").read_text(encoding="utf-8")
        conf = record.split("## Confirmed steps\n")[1].split("## Open objections")[0]
        self.assertIn(f"- {c} Lemma 2", conf)
        self.assertNotIn("Theorem 1", conf)

    def test_ledger_entry_takes_the_candidate_model(self):
        tr = self.cand(self.task("literature-reviewer", "TRANSFER-AUDIT"), "transfer:S03 Thm 2@M3", "--kind", "transfer")
        st = self.state()
        st["candidates"][tr]["model"] = "M3"  # set by cand add from the claim's @Mx (Package D)
        self.save(st)
        self.review(tr, self.task("verifier", "ISOLATED"), "isolated", "PASS")
        self.ri("accept", self.R, tr)
        self.ri("ledger", "add", self.R, "--cand", tr)
        self.assertEqual(self.state()["ledger"]["L001"]["model"], "M3")


if __name__ == "__main__":
    unittest.main()
