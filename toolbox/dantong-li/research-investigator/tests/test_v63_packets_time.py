"""Tests for the v6.3 packages F (dispatch), G (packets and independence) and H (time lines) of scripts/ri.py.

Run:  python -B -m unittest discover -s tests -v     (from the skill directory)
"""
import os
import re
import unittest
from pathlib import Path

from test_ri import RiCase, ri

INDEX = """# Sources index (orchestrator-owned; `ri.py intake` adds rows)

| ID | Original name | Stored path | Type | Size | Status | Relevance |
|---|---|---|---|---|---|---|
| S01 | arxiv-2301.12345.pdf | sources/raw/arxiv-2301.12345.pdf | paper-pdf | 1.0 KB | readable | - |
| S02 | notes.md | sources/raw/notes.md | user-notes | 120 B | readable | - |
| S03 | survey.pdf | sources/raw/survey.pdf | paper-pdf | 2.0 KB | readable | - |
| S04 | solver.py | sources/raw/solver.py | code | 300 B | readable | - |
"""

CARD = """# Q01 — Does X help?    version: 2    status: vetting
(investigator-owned; the status that counts is in state.json - see `ri.py status`)
Model: M1   Kind: ACH   Tier: AMBITIOUS — the leading gap of H1;
  a second line of the tier reason.
R1: for all n >= 1, c(1, n) <= 2.
Plausibility: mixed (T004)
Forecast: likely true
Skeptic: T004 ADVANCE; plausibility mixed;
  continuation of the skeptic line.
Lineage: parent user; operator none; trigger E1
History: v1 T002 created; v2 T005 R1 sharpened
"""


class G4Case(RiCase):
    def setUp(self):
        super().setUp()
        self.init()

    def new(self, *args, code=0):
        """task new; returns (task ID, combined output)."""
        out = self.ri("task", "new", self.R, *args, code=code)
        return (out.split()[0] if code == 0 else None), out

    def finish(self, tid, *lines):
        self.result(tid, *lines)
        self.ri("ingest", self.R, tid)

    def sources(self):
        self.write("sources/index.md", INDEX)
        self.write("sources/S01.md", "# S01 card\nTitle: Baseline. Authors: Smith and Jones (2019).\n")


class TestV63Opening(G4Case):
    def test_start_writes_dispatch_md_with_the_spawn_line(self):
        q = self.lane()
        tid, out = self.new("--role", "prover", "--direction", f"PROVE {q}.R1", "--start")
        spawn = next(x for x in out.splitlines() if x.startswith("dispatch: "))
        self.assertEqual(ri.xp(self.path("tasks", tid, "dispatch.md")).read_text(encoding="utf-8"), spawn + "\n")
        pk = os.path.join(os.path.abspath(self.R), "tasks", tid, "packet.md")
        self.assertIn(f"Read {pk} and follow it.", spawn)
        queued, _ = self.new("--role", "prover", "--direction", f"PROVE {q}.R1")
        self.assertFalse(self.path("tasks", queued, "dispatch.md").exists())
        self.ri("task", "set", self.R, tid, "unknown")
        redo, out = self.new("--redo", tid, "--start")
        self.assertIn(f"tasks{os.sep}{redo}{os.sep}packet.md", self.path("tasks", redo, "dispatch.md").read_text(encoding="utf-8"))
        self.assertNotIn("possibly dispatched", self.status())


class TestV63Packets(G4Case):
    def test_new_default_assignments_have_no_placeholder(self):
        self.sources()
        self.ri("q", "add", self.R, "--title", "seed")
        lit = self.task("literature-reviewer", "LANDSCAPE")
        self.write(f"tasks/{lit}/landscape.md", "already studied: none")
        self.finish(lit, "follow_ups: [TARGETED aliases of X for Q01]", "found: settles (S03 Thm 1)")
        quiet = self.task("literature-reviewer", "SURVEY")
        self.finish(quiet, "follow_ups: none")
        anchor = self.task("scout", "EXPLORE", title="ANCHOR S01")
        self.write(f"tasks/{anchor}/table.md", "k = 0 table")
        self.finish(anchor, "outcome: table-ready")
        sk = self.task("skeptic", "MODEL-GATE", title="M1")
        self.write(f"tasks/{sk}/gate.md", "M1 degenerate")
        self.finish(sk, "M1: {verdict: DEGENERATE}")
        p = self.task("prover", "PROVE", lane=self.lane())  # Q02, active
        c = self.cand(p, "Q02.R1")
        cases = [
            (("--role", "investigator", "--mode", "MODEL"),
             ("- sources/raw/notes.md (user-notes S02: read in full)", "- sources/S01.md", "- sources/raw/survey.pdf (S03, uncarded)",
              "- sources/index.md: 1 code or data file(s) without a card", f"- tasks/{lit}/landscape.md (LANDSCAPE)", f"- tasks/{anchor}/table.md (ANCHOR)",
              f"- tasks/{lit}/result.md (literature-reviewer LANDSCAPE: found settles)", "- questions/Q01.md (primary seed, draft)",
              "Opening budget: investigator.md MODEL.")),
            (("--role", "investigator", "--mode", "MODEL", "--title", "apply gate verdicts"),
             (f"- tasks/{sk}/gate.md (MODEL-GATE: DEGENERATE)", "- frontier/model.md")),
            (("--role", "investigator", "--mode", "MODEL", "--title", "focused fast start"), ("keep R1 verbatim",)),
            (("--role", "investigator", "--mode", "MODEL", "--title", "focused"), ("target rung Rt",)),
            (("--role", "investigator", "--mode", "PROPOSE", "--title", "lens NEUTRALIZE"),
             ("lens NEUTRALIZE", "Never open: other proposers' cards.md.", f"- tasks/{lit}/landscape.md (LANDSCAPE)")),
            (("--role", "investigator", "--mode", "SELECT"),
             (f"- tasks/{lit}/result.md (literature-reviewer LANDSCAPE: follow_ups)", "Capacity: K not set",
              "- frontier/map.md", "- questions/ (statuses: Q01 draft, Q02 active)", f"- tasks/{sk}/result.md (skeptic MODEL-GATE)",
              f"- tasks/{anchor}/result.md (scout EXPLORE)")),
            (("--role", "skeptic", "--mode", "MODEL-GATE", "--title", "M1, M2"),
             ("MODEL-GATE of M1, M2", "- contract.md (the key difference)")),
            (("--role", "literature-reviewer", "--mode", "SURVEY", "--title", "S01-S03"),
             ("- sources/raw/arxiv-2301.12345.pdf (S01)", "- sources/raw/survey.pdf (S03)", "- contract.md")),
            (("--role", "literature-reviewer", "--mode", "LANDSCAPE"), ("- sources/raw/notes.md (user-notes S02)",)),
            (("--role", "literature-reviewer", "--mode", "TRANSFER-AUDIT", "--title", "S01 Thm 2"),
             ("TRANSFER-AUDIT of S01 Thm 2", "- sources/S01.md", "- sources/raw/arxiv-2301.12345.pdf (S01)")),
            (("--role", "scout", "--mode", "EXPLORE", "--title", "cell k=1"), ("EXPLORE cell k=1", "- frontier/map.md")),
            (("--role", "scout", "--mode", "EXPLORE", "--title", "ANCHOR S01"),
             ("- sources/raw/arxiv-2301.12345.pdf (the baseline source file, S01)",)),
            (("--role", "writer", "--cand", c), (f"- candidates/{c}.md (proposed; claims Q02.R1)", "no comparator ran",
                                                  "Word budget")),
        ]
        for args, needles in cases:
            tid, _ = self.new(*args, "--start")
            a = self.assignment(tid)
            self.assertNotIn(ri.PLACEHOLDER, a, args)
            self.assertTrue(a.startswith("Request: "), args)
            self.assertEqual(sum(x.startswith("Return") for x in a.splitlines()), 1, args)
            for needle in needles:
                self.assertIn(needle, a, args)
            for name in ("report.md", "analysis.md", "summary.md", "findings.md"):
                self.assertNotIn(name, a, args)
        sel = [k for k, t in self.state()["tasks"].items() if t.get("mode") == "SELECT"][0]
        self.assertNotIn(f"tasks/{quiet}/result.md", self.assignment(sel))  # follow_ups: none
        renew, _ = self.new("--role", "investigator", "--mode", "RENEW")
        self.assertNotIn(f"tasks/{lit}/result.md", self.assignment(renew))  # listed by the SELECT already
        late = self.task("literature-reviewer", "TARGETED")
        self.finish(late, "follow_ups: [TARGETED settles check for Q02]")
        self.write("frontier/patches/M3.md", "M3 = M1 + patch")
        renew, _ = self.new("--role", "investigator", "--mode", "RENEW")
        a = self.assignment(renew)
        self.assertIn(f"- tasks/{late}/result.md (literature-reviewer TARGETED: follow_ups)", a)
        self.assertIn(ri.PATCH_DIR_LINE, a)
        self.assertIsNone(ri.default_assignment(self.state(), self.R, "T099", "investigator", "PROPOSE", None, None, [],
                                                None, None, [], None, title=None))  # PROPOSE needs a lens
        self.assertIn("still the placeholder",
                      self.new("--role", "literature-reviewer", "--mode", "TARGETED", "--start", code=1)[1])

    def test_writer_cand_and_propose_defaults_list_their_inputs(self):
        self.lane()
        base = self.accepted("Q01.R3")
        self.ri("ledger", "add", self.R, "--cand", base)  # L001
        p = self.task("prover", "PROVE", lane="Q01")
        c = self.cand(p, "Q01.R1", "--deps", "L001", text="# Draft\n## Theorem\nFor all n. Uses S03 Thm 2.\n")
        self.write("sources/S03.md", "# S03 card\n")
        v1, v2 = self.task("verifier", "INDIVIDUAL", lane="Q01"), self.task("verifier", "CROSS-DRAFT", lane="Q01")
        for v, scope in ((v1, "individual"), (v2, "cross")):
            self.write(f"tasks/{v}/review.md", "MINOR fill O3 in Section 2")
            self.review(c, v, scope, "PASS_WITH_MINOR", "--blocking", "O3 MINOR: Section 2 - a missing constant")
        self.ri("accept", self.R, c)
        a = self.assignment(self.new("--role", "writer", "--cand", c, "--start")[0])
        for needle in (f"- candidates/{c}.md (accepted; claims Q01.R1)", f"- candidates/{base}.md (ledger entry L001)",
                       f"- tasks/{v1}/review.md (individual review of {c})", f"- tasks/{v2}/review.md (cross review of {c})",
                       "- lanes/Q01/statement.md", "- contract.md", "- sources/S03.md (cited)"):
            self.assertIn(needle, a)
        self.ri("q", "add", self.R, "--title", "old idea")
        self.ri("q", "set", self.R, "Q02", "--status", "parked")
        a = self.assignment(self.new("--role", "investigator", "--mode", "PROPOSE", "--title", "lens EXTREMAL")[0])
        self.assertIn("- questions/Q02.md (parked)", a)
        self.assertNotIn("- questions/Q01.md", a)
        self.assertIn("scout/ (filed tables: cite them instead of recomputing)",
                      self.assignment(self.new("--role", "prover", "--direction", "PROVE Q01.R2")[0]))

    def test_focused_fast_start_model_assignment_keeps_r1_verbatim_text(self):
        self.R = str(Path(self.tmp.name, "f"))
        self.ri("init", self.R, "--objective", "claim", "--mode", "focused")
        self.ri("q", "add", self.R, "--title", "claim")
        self.ri("q", "set", self.R, "Q01", "--status", "active", "--rung", "R1")
        self.write("lanes/Q01/statement.md", "Goal. Prove or disprove: the claim verbatim.\nD: not R1. D refutes: R1\n")
        fast, _ = self.new("--role", "investigator", "--mode", "MODEL", "--title", "focused fast start", "--start")
        a = self.assignment(fast)
        self.assertIn("M0 and M1 only; keep R1 verbatim and keep its name; add weaker fallbacks R2.. below it, refine D, "
                      "and list stronger variants under 'Stronger (after R1)' (with the converse for the whole class when "
                      "one is plausible, frontier-method.md sec. 10 TIGHTNESS); write the statement in your task "
                      "directory as new/Q01-statement.md.", a)
        self.assertIn("- lanes/Q01/statement.md (the fast-start statement)", a)
        self.assertIn("Return: new/Q01-statement.md, reading.md", a)
        det, _ = self.new("--role", "investigator", "--mode", "MODEL", "--title", "focused")
        a = self.assignment(det)
        self.assertIn("seed Q01: the user's problem as target rung Rt; optional stronger rungs R1..Rt-1 above it, marked "
                      "optional (Rt = R1 if there are none); weaker fallbacks below; D with 'D refutes: Rt'.", a)
        self.assertNotIn("keep R1 verbatim", a)
        survey, _ = self.new("--role", "literature-reviewer", "--mode", "SURVEY")
        self.assertIn("Settles check: yes", self.assignment(survey))

    def test_assignment_lint_warns_on_unfiled_citation_and_steering_words(self):
        self.sources()
        q = self.lane()
        text = ("Compare 2301.12345v2 with 2405.00001. Smith and Jones (2019) and Lee et al. 2021 matter; "
                "doi 10.1145/3519935.3520001. This is likely easy; do not pretend otherwise.")
        tid, out = self.new("--role", "investigator", "--mode", "BREADTH", "--extra", text)
        warns = [x for x in out.splitlines() if x.startswith("warning (I1)")]
        self.assertEqual(len(warns), 5, out)
        for tok in ("'2405.00001'", "'Lee et al. 2021'", "'10.1145/3519935.3520001'", "'likely'", "'do not pretend'"):
            self.assertTrue(any(tok in w for w in warns), tok)
        self.assertNotIn("2301.12345", " ".join(warns))  # filed: its index row names it
        self.assertNotIn("Smith", " ".join(warns))  # filed: the S01 card names Smith and 2019
        self.assertIn(text, self.assignment(tid))  # never refused, never changed
        self.write("assign.md", "Request: EXPLAIN why 2405.00001 matters; promising.\n")
        _, out = self.new("--role", "investigator", "--mode", "EXPLAIN", "--assignment-file", "assign.md")
        self.assertIn("'2405.00001'", out)
        self.assertIn("'promising'", out)
        _, out = self.new("--role", "verifier", "--mode", "INDIVIDUAL", "--cand", self.cand(self.task("prover", "PROVE", lane=q)))
        self.assertNotIn("warning (I1)", out)  # defaults are never linted
        self.assertEqual(ri.lint_assignment(self.R, "writer", None, "Expected value. Smith 2019."),
                         ["warning (I1): steering word 'Expected'; an Assignment carries no opinion about the outcome"])
        self.assertEqual([w.split("'")[1] for w in ri.lint_assignment(self.R, "writer", None, "Why 2405.00001?")],
                         ["2405.00001"])  # an arXiv ID is not also an author-year token

    def test_question_gate_lists_gate_copy_without_tier_and_skeptic_lines(self):
        q = self.ri("q", "add", self.R, "--title", "Does X help?").split()[0]
        self.write(f"questions/{q}.md", CARD)
        tid, _ = self.new("--role", "skeptic", "--mode", "QUESTION-GATE", "--question", q)
        a = self.assignment(tid)
        self.assertIn(f"- tasks/{tid}/card-{q}.md (the question card, gate copy)", a)
        self.assertNotIn(f"questions/{q}.md", a)
        for needle in (f"- lanes/{q}/statement.md", "- frontier/transfer.md", "- ledger.md", "- contract.md"):
            self.assertIn(needle, a)
        copy = self.path("tasks", tid, f"card-{q}.md").read_text(encoding="utf-8")
        self.assertIn("Model: M1   Kind: ACH\nR1: for all n >= 1, c(1, n) <= 2.\nLineage:", copy)
        for gone in ("Tier", "AMBITIOUS", "second line of the tier", "Plausibility", "Forecast", "Skeptic", "continuation"):
            self.assertNotIn(gone, copy)
        self.assertIn("History: v1 T002 created", copy)
        self.assertIn("queued skeptic", self.status())  # the card copy is a packet input, not a worker output
        self.assertNotIn("possibly dispatched", self.status())

    def test_model_gate_with_question_takes_both_inputs_and_allows_light(self):
        q = self.ri("q", "add", self.R, "--title", "claim").split()[0]
        self.write(f"questions/{q}.md", CARD)
        self.write("frontier/patches/M2.md", "M2 = M1 + patch")
        tid, _ = self.new("--role", "skeptic", "--mode", "MODEL-GATE", "--title", "M2", "--question", q, "--light", "--start")
        a = self.assignment(tid)
        for needle in ("Request: MODEL-GATE of M2", f"Request: QUESTION-GATE of {q}", "- frontier/patches/M2.md",
                       f"- tasks/{tid}/card-{q}.md", f"- lanes/{q}/statement.md", ri.LIGHT_MODEL_GATE.format(q)):
            self.assertIn(needle, a)
        self.assertTrue(self.state()["tasks"][tid]["light"])
        self.assertIn("--light is only for", self.new("--role", "skeptic", "--mode", "MODEL-GATE", "--light", code=2)[1])
        a = self.assignment(self.new("--role", "skeptic", "--mode", "MODEL-GATE")[0])
        self.assertIn("MODEL-GATE of the models in frontier/model.md without a MODEL-GATE line", a)

    def test_gate_packets_refuse_other_cohort_candidate_prover_dir_and_same_candidate_scout_output(self):
        q = self.lane()
        base = self.accepted("Q01.R3")
        self.ri("ledger", "add", self.R, "--cand", base)  # L001, a dependency below
        p1, p2 = self.task("prover", "PROVE", lane=q), self.task("prover", "PROVE", lane=q)
        c1, c2 = self.cand(p1, "Q01.R1", "--deps", "L001"), self.cand(p2, "Q01.R1")
        sc = self.task("scout", "SANITY", extra=("--cand", c1))
        refused = {("verifier", "INDIVIDUAL"): (f"Also candidates/{c2}.md.", f"Data: candidates/{c2}/grid.csv",
                                                f"Code: tasks/{p1}/check.py", f"See tasks/{p2}", f"Table: scout/{sc}/table.md",
                                                f"Table: tasks/{sc}/table.md"),
                   ("verifier", "ISOLATED"): (f"tasks/{p1}/draft.md",),
                   ("scout", "WITNESS"): (f"candidates/{c2}.md", f"tasks/{p2}/code.py")}
        for (role, mode), texts in refused.items():
            for text in texts:
                out = self.new("--role", role, "--mode", mode, "--cand", c1, "--extra", text, code=1)[1]
                self.assertIn("never-include", out, text)
        lit = self.task("literature-reviewer", "SURVEY")
        for text in (f"Also candidates/{c1}.md and candidates/{base}.md (ledger entry L001).", f"tasks/{lit}/S01.md"):
            self.new("--role", "verifier", "--mode", "INDIVIDUAL", "--cand", c1, "--extra", text)
        self.new("--role", "verifier", "--mode", "INDIVIDUAL", "--cand", c2, "--extra", f"Table: scout/{sc}/table.md")
        self.new("--role", "scout", "--mode", "SANITY", "--cand", c1, "--extra", f"Earlier table: scout/{sc}/table.md")
        self.new("--role", "verifier", "--mode", "CROSS-DRAFT", "--cand", f"{c1},{c2}", "--extra", f"candidates/{c2}.md")
        self.new("--role", "summarizer", "--direction", "PROVE Q01.R1", "--extra", f"tasks/{p1}/draft.md")  # not a gate
        self.write("a.md", f"Request: INDIVIDUAL review of {c1}.\nInputs (open by path):\n- candidates/{c2}.md\n")
        self.new("--role", "verifier", "--mode", "INDIVIDUAL", "--cand", c1, "--assignment-file", "a.md", code=1)

    def test_quarantine_requires_a_reason_code(self):
        self.lane()
        c = self.accepted("Q01.R2")
        self.ri("ledger", "add", self.R, "--cand", c)
        self.assertIn("--code", self.ri("quarantine", self.R, "L001", "--reason", "x", code=2))
        self.ri("quarantine", self.R, "L001", "--code", "label", "--reason", "a label in the file", code=2)
        self.ri("quarantine", self.R, "L001", "--code", "Failed-Isolated", "--reason", "second ISOLATED review failed")
        st = self.state()
        self.assertEqual((st["ledger"]["L001"]["code"], st["candidates"][c]["code"]), ("failed-isolated", "failed-isolated"))
        self.assertIn("quarantine L001 (failed-isolated)", st["events"][-1]["note"])
        self.assertIn("failed-isolated: second ISOLATED review failed", self.path("ledger.md").read_text(encoding="utf-8"))
        self.assertIn("quarantine --code contradiction", ri.CONTRA_TAIL)

    def test_cand_add_warns_on_labels_in_frozen_file(self):
        q = self.lane()
        p = self.task("prover", "PROVE", lane=q)
        warn = "labels and verdicts belong in result.md (envelope rule 4); gates ignore them"
        for text, what in (("---\ntask: T001\nrole: prover\nstatus: completed\n---\n# Theorem\nx\n", "a result.md header block"),
                           ("# Theorem\nx\nLabel: agent-checked\n", "an I5 label line"),
                           ("# Theorem\nx\nVerdict: PASS\n", "a verdict line"),
                           ("# Lemma\n**KILL(IMPLIED)**\n", "a verdict line")):
            self.n += 1
            self.write(f"tasks/{p}/d{self.n}.md", text)
            out = self.ri("cand", "add", self.R, "--file", f"tasks/{p}/d{self.n}.md", "--author", p, "--claims", "Q01.R1")
            self.assertIn(warn, out, text)
            self.assertIn(what, out, text)
        clean = "# Draft\n---\n## Lemma 1\nStatus: proved\n## Lemma 2\nStatus: uses G1\n---\nThe verdict of Lemma 1 is clear.\n"
        self.write(f"tasks/{p}/clean.md", clean)
        self.assertNotIn(warn, self.ri("cand", "add", self.R, "--file", f"tasks/{p}/clean.md", "--author", p, "--claims", "Q01.R2"))
        w = self.task("writer")
        self.write(f"tasks/{w}/manuscript.md", "# Title\nResults: agent-checked\n")  # the writer's template asks for it
        self.assertNotIn(warn, self.ri("cand", "add", self.R, "--file", f"tasks/{w}/manuscript.md", "--author", w,
                                       "--kind", "manuscript"))

    def test_load_bearing_and_contradiction_hints_name_the_code(self):
        self.lane()
        p = self.task("prover", "PROVE", lane="Q01")
        src = self.cand(p, "Q01.R2")
        frag = self.cand(self.task("ledger-auditor", lane="Q01"), None, "--from", src)
        self.review(frag, self.task("verifier", "ISOLATED"), "isolated", "PASS")
        self.ri("accept", self.R, frag)
        self.ri("ledger", "add", self.R, "--cand", frag)
        self.accepted("Q01.R1", "--deps", "L001")
        self.assertIn(f"review of {frag} (if it fails: quarantine L001 --code failed-isolated)", self.status())


class TestV63Hygiene(G4Case):
    def test_every_default_packet_has_a_time_line(self):
        q = self.lane()
        self.write(f"questions/{q}.md", CARD)  # a card with an R1: a QUESTION-GATE needs one
        c = self.cand(self.task("prover", "PROVE", lane=q))
        work = "Time: return within about {} minutes of work; save partial work first (status partial)."
        cases = [(("--role", "verifier", "--mode", "INDIVIDUAL", "--cand", c), work.format(60)),
                 (("--role", "verifier", "--mode", "ISOLATED", "--cand", c), work.format(45)),
                 (("--role", "prover", "--direction", "PROVE Q01.R1"), work.format(90)),
                 (("--role", "scout", "--mode", "SANITY", "--cand", c), ri.SCOUT_TIME),
                 (("--role", "summarizer", "--direction", "PROVE Q01.R1"), work.format(20)),
                 (("--role", "skeptic", "--mode", "QUESTION-GATE", "--question", q), work.format(25)),
                 (("--role", "investigator", "--mode", "RENEW"), work.format(45)),
                 (("--role", "investigator", "--mode", "SELECT"), work.format(60)),
                 (("--role", "literature-reviewer", "--mode", "LANDSCAPE"), work.format(45)),
                 (("--role", "literature-reviewer", "--mode", "TARGETED", "--extra", "Search the stuck step."), work.format(45)),
                 (("--role", "comparator", "--extra", "Compare C001."), work.format(45)),
                 (("--role", "writer", "--extra", "Write it."), work.format(60))]
        for args, line in cases:
            lines = self.assignment(self.new(*args)[0]).splitlines()
            self.assertEqual(lines[-2:], [line, lines[-1]], args)
            self.assertTrue(lines[-1].startswith("Stop condition:"), args)
            self.assertEqual(sum(bool(re.match(r"Time\s*:", x)) for x in lines), 1, args)
        self.assertTrue(ri.SCOUT_TIME.startswith("Time: at most about 20 minutes of compute, each run under 5 minutes"))
        for mode in ("SURVEY", "LANDSCAPE", "TRANSFER-AUDIT", "TARGETED"):
            self.assertEqual(ri.role_minutes("literature-reviewer", mode), 45)
        self.assertEqual([ri.role_minutes("investigator", m) for m in ("MODEL", "SELECT", "PROPOSE", "BREADTH")], [60, 60, 45, 45])
        self.assertEqual([ri.role_minutes("verifier", m) for m in ("PAPER", "CROSS-DRAFT", "ADJUDICATE")], [60, 60, 45])
        self.assertEqual([ri.role_minutes(r) for r in ("process-advisor", "ledger-auditor", "skeptic")], [45, 45, 25])

    def test_assignment_time_line_wins(self):
        self.write("a.md", "Do it.\nTime: about 10 minutes.\nStop condition: after one page.\n")
        tid, _ = self.new("--role", "writer", "--assignment-file", "a.md")
        self.assertEqual(self.assignment(tid).splitlines(),
                         ["Do it.", "Time: about 10 minutes.", ri.RETURN_DEFAULT, "Stop condition: after one page."])
        tid, _ = self.new("--role", "prover", "--extra", "Prove it.", "--extra", "time: 30 minutes at most")
        self.assertEqual(sum("minutes" in x for x in self.assignment(tid).splitlines()), 1)
        old, _ = self.new("--role", "scout", "--mode", "EXPLORE", "--title", "cell k=1", "--start")
        self.ri("task", "set", self.R, old, "unknown")
        redo, _ = self.new("--redo", old)
        self.assertEqual(self.assignment(redo), self.assignment(old))
        self.assertEqual(self.assignment(redo).count("Time:"), 1)


if __name__ == "__main__":
    unittest.main()
