"""Tests for v6.3 packages B (the user's priorities decide the first lanes) and C (literature routing).

Run with the rest of the suite:  python -B -m unittest discover -s tests   (from the skill directory)
"""
import os
import re
import unittest
import zipfile
from pathlib import Path

from test_ri import RiCase, ri


class TestV63Opening(RiCase):
    """Package B: seeds in the user's order, an R1 before any QUESTION-GATE, intent files, the no-prover watchdog."""

    def setUp(self):
        super().setUp()
        self.init()

    def gate(self, *questions, code=0, light=False):
        out = self.ri("task", "new", self.R, "--role", "skeptic", "--mode", "QUESTION-GATE", "--question",
                      ",".join(questions), *(["--light"] if light else []), code=code)
        return out if code else out.split()[0]

    def test_contract_has_from_your_notes_section_and_delegated_turn_model(self):
        contract = self.path("contract.md").read_text(encoding="utf-8")
        self.assertIn('## From your notes (verbatim, with paths)\n(priorities, success criteria, the result the user '
                      'wants; "none stated" if none)\n', contract)
        self.assertLess(contract.index("## Key difference (verbatim)"), contract.index("## From your notes"))
        self.assertLess(contract.index("## From your notes"), contract.index("## Mode"))
        self.assertIn("turn_model: text-only reply ends the turn: <yes | no | unknown (treat as yes) | delegated "
                      "(single return)>", contract)

    def test_q_add_priority_orders_status_questions(self):
        for title, prio in (("a", "secondary"), ("b", None), ("c", "primary"), ("d", "secondary")):
            out = self.ri("q", "add", self.R, "--title", title, *(["--priority", prio] if prio else []))
            self.assertEqual("(secondary seed)" in out, prio == "secondary")
        qs = self.state()["questions"]
        self.assertEqual([qs[q]["priority"] for q in sorted(qs)], ["secondary", None, "primary", "secondary"])
        seqs = [qs[q]["created_seq"] for q in sorted(qs)]
        self.assertEqual(seqs, sorted(seqs))
        self.ri("q", "set", self.R, "Q04", "--status", "vetting")
        self.assertIn("questions: draft Q02 Q03 Q01(2nd) | vetting Q04(2nd)", self.status())
        self.ri("q", "add", self.R, "--title", "e", "--priority", "tertiary", code=2)
        self.assertIn("--priority", " ".join(self.ri("q", "add", "-h").split()))

    def test_question_gate_refused_without_r1_and_allowed_for_fast_start_statement(self):
        self.ri("q", "add", self.R, "--title", "seed claim")
        out = self.gate("Q01", light=True, code=1)
        self.assertIn("Q01 has no R1 yet: MODEL step 8 or RENEW writes it first", out)
        self.assertEqual(self.state()["counters"]["T"], 0)
        self.ri("q", "set", self.R, "Q01", "--status", "active")  # the template statement: Goal line still <R1>
        self.gate("Q01", code=1)
        stmt = self.path("lanes", "Q01", "statement.md")
        stmt.write_text(stmt.read_text(encoding="utf-8").replace(
            "Goal. Prove or disprove: <R1>.", "Goal. Prove or disprove: every 3-regular graph has property P."),
            encoding="utf-8")
        tid = self.gate("Q01", light=True)  # a fast start: the claim is its Goal line
        self.assertTrue(self.state()["tasks"][tid]["light"])
        self.ri("q", "add", self.R, "--title", "direction seed")
        self.assertIn("Q02 has no R1 yet", self.gate("Q01", "Q02", code=1))
        self.ri("task", "new", self.R, "--role", "skeptic", "--mode", "MODEL-GATE", "--question", "Q02",
                "--extra", "x", code=1)
        self.r1("Q02")
        self.gate("Q01", "Q02")
        self.ri("q", "add", self.R, "--title", "third")  # other roles never need an R1
        self.ri("task", "new", self.R, "--role", "skeptic", "--mode", "CLAIM-GATE", "--question", "Q03", "--extra", "x")

    def test_intake_types_intent_files_in_folders_and_readme_targets(self):
        readme = ("# Pack\nSee [the memo](docs/context-memo.md) and `docs/context.txt`, and "
                  "[a paper](papers/arxiv-2301.12345.md) or [web](https://example.org/x.md).\n"
                  "START HERE: docs/plan-v2.md\n")
        expect = {"pack/README.md": "user-notes", "pack/guides/01-overview.md": "user-notes",
                  "pack/notes/ideas.md": "user-notes", "pack/docs/AGENT_BRIEF.md": "user-notes",
                  "pack/chat-export.md": "user-notes", "pack/docs/context-memo.md": "user-notes",
                  "pack/docs/context.txt": "user-notes", "pack/docs/plan-v2.md": "user-notes",
                  "pack/a/b/guide.md": "user-notes", "pack/papers/arxiv-2301.12345.md": "notes",
                  "pack/a/b/c/guide.md": "notes", "pack/code/guide.py": "code", "pack/docs/other.md": "notes",
                  "pack/data/status.csv": "data", "pack/transcripts/day1.pdf": "paper-pdf"}
        arc = Path(self.tmp.name, "pack.zip")
        with zipfile.ZipFile(arc, "w") as z:
            for name in expect:
                z.writestr(name, readme if name.endswith("README.md") else "text")
        out = self.ri("intake", self.R, "--archive", arc)
        idx = self.path("sources", "index.md").read_text(encoding="utf-8")
        got = {r.split("|")[2].strip(): r.split("|")[4].strip() for r in idx.splitlines() if re.match(r"\| S\d+ ", r)}
        self.assertEqual(got, expect)
        line = next(x for x in out.splitlines() if x.startswith("user-notes (read in full"))
        self.assertIn("sources/raw/pack/docs/plan-v2.md", line)
        self.assertNotIn("arxiv-2301", line)

    def test_no_prover_watchdog_line_then_safeguard_line_in_select_and_renew_packets(self):
        self.ri("q", "add", self.R, "--title", "seed conjecture")
        self.ri("q", "add", self.R, "--title", "optional probe", "--priority", "secondary")
        self.r1("Q02")
        self.assertRegex(self.status(), r"no prover yet: 0 tasks, \d+ min; next opening step: the first wave: SURVEY "
                                        r"per family \+ LANDSCAPE \+ scout ANCHOR")
        self.task("literature-reviewer", "SURVEY")
        self.assertIn("next opening step: investigator MODEL (once the baseline family's card is filed)", self.status())
        model = self.task("investigator", "MODEL")
        self.assertIn("no prover yet: 2 tasks", self.status())
        self.assertIn("next opening step: skeptic MODEL-GATEs", self.status())
        mg = self.task("skeptic", "MODEL-GATE")
        self.assertIn("next opening step: investigator PROPOSE", self.status())  # Q01 has no R1; Q02 is secondary
        self.r1("Q01")
        self.assertIn("next opening step: one batched full QUESTION-GATE on the primary seeds with an R1, once every "
                      "MODEL-GATE has returned (--question Q01)", self.status())
        light = self.gate("Q01", light=True)  # a light gate is not the batched seed gate
        self.assertIn("(--question Q01)", self.status())
        seed_gate = self.gate("Q01")
        self.assertIn("next opening step: investigator PROPOSE x2-4 (after LANDSCAPE)", self.status())
        prop = self.task("investigator", "PROPOSE", title="lens OBVIOUS-CONSTRUCTION")
        self.assertIn("next opening step: investigator SELECT", self.status())
        sel = self.task("investigator", "SELECT")
        self.assertIn("skeptic QUESTION-GATEs on the selected questions (after SELECT returns)", self.status())
        self.ri("task", "set", self.R, model, mg, light, seed_gate, prop, sel, "done")
        self.ri("q", "add", self.R, "--title", "selected card")  # Q03, registered after SELECT
        out = self.status()
        self.assertIn("next opening step: skeptic QUESTION-GATEs on the selected questions (--question Q03)", out)
        self.assertNotIn("no-prover safeguard", out)  # SELECT's card is not gated yet
        early = self.ri("task", "new", self.R, "--role", "investigator", "--mode", "RENEW").split()[0]
        self.assertNotIn("No-prover safeguard", self.assignment(early))
        self.ri("task", "set", self.R, early, "cancelled")
        self.r1("Q03")
        qg = self.gate("Q03")
        self.assertNotIn("no-prover safeguard", self.status())  # its QUESTION-GATE is live
        self.ri("task", "set", self.R, qg, "done")
        out = self.status()
        self.assertIn(f"no-prover safeguard (SELECT {sel}'s QUESTION-GATEs left nothing ready): the next investigator "
                      "SELECT or RENEW packet carries the safeguard line; dispatch investigator RENEW", out)
        self.assertIn("next opening step: none missing, and no question is ready", out)
        ren = self.ri("task", "new", self.R, "--role", "investigator", "--mode", "RENEW").split()[0]
        self.assertIn(ri.SAFEGUARD, self.assignment(ren))
        sel2 = self.task("investigator", "SELECT")
        self.assertEqual(self.assignment(sel2).count("No-prover safeguard:"), 1)
        redo = self.ri("task", "new", self.R, "--redo", sel2).split()[0]
        self.assertEqual(self.assignment(redo).count("No-prover safeguard:"), 1)
        self.ri("q", "set", self.R, "Q03", "--status", "ready")
        self.assertNotIn("no-prover safeguard", self.status())  # a ready question
        self.assertIn("next opening step: open a lane for Q03", self.status())
        self.ri("q", "set", self.R, "Q03", "--status", "active")
        self.ri("round", self.R, "Q03", "--open")
        self.task("prover", "PROVE", lane="Q03")
        out = self.status()
        self.assertNotIn("no prover yet", out)
        self.assertNotIn("no-prover safeguard", out)
        st = self.state()
        st["questions"]["Q03"]["status"] = "parked"
        self.assertIsNone(ri.no_prover_safeguard(st))  # any prover task ends it

    def test_watchdog_without_seeds_and_after_20_finished_tasks(self):
        model = self.task("investigator", "MODEL")
        self.ri("task", "set", self.R, model, "done")
        self.assertIn("next opening step: skeptic MODEL-GATEs on MODEL's models; no seeds and no foothold R1",
                      self.status())
        scouts = [self.task("scout", "EXPLORE") for _ in range(19)]
        self.ri("task", "set", self.R, *scouts[:18], "done")
        self.assertNotIn("no-prover safeguard", self.status())  # 19 finished
        self.ri("task", "set", self.R, scouts[18], "done")
        out = self.status()
        self.assertIn("no-prover safeguard (20 tasks finished): the next investigator SELECT or RENEW packet carries "
                      "the safeguard line\n", out + "\n")  # no SELECT yet: no RENEW suggested
        self.assertNotIn("dispatch investigator RENEW", out)
        R2 = str(Path(self.tmp.name, "f"))
        self.ri("init", R2, "--objective", "claim", "--mode", "focused")
        self.assertNotIn("no prover yet", self.ri("status", R2))  # program mode only


class TestV63Literature(RiCase):
    """Package C: file-cards, literature hints in ingest, focused literature events, intake --only and code."""

    def setUp(self):
        super().setUp()
        self.init()
        arc = Path(self.tmp.name, "bundle.zip")
        with zipfile.ZipFile(arc, "w") as z:
            z.writestr("papers/a.pdf", "%PDF a")  # S01
            z.writestr("papers/b.pdf", "%PDF b")  # S02
        self.ri("intake", self.R, "--archive", arc)

    def lit(self, mode="SURVEY", files=(), fields=(), ingest=True):
        """A finished literature-reviewer task with the given output files."""
        tid = self.task("literature-reviewer", mode)
        for name, text in files:
            p = ri.xp(self.path("tasks", tid, *name.split("/")))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(text) if isinstance(text, bytes) else p.write_text(text, encoding="utf-8")
        self.result(tid, f"mode: {mode}", *fields)
        if ingest:
            return tid, self.ri("ingest", self.R, tid)
        return tid

    def index(self):
        return self.path("sources", "index.md").read_text(encoding="utf-8")

    def test_file_cards_assigns_ids_dedupes_by_arxiv_and_rewrites_bounds(self):
        bounds = ("# Bounds\n\n| card | model | regime | side |\n|---|---|---|---|\n| S01 | M0 | n large | IMP |\n"
                  "| NEW-smith | M1 | k = 1 | ACH |\n")
        t1, _ = self.lit(files=(("S01.md", "# S01\nTitle: Paper A\nAuthors: X. Y\n## Results\nIMP 2.\n"),
                                ("NEW-smith.md", "# NEW-smith\n- **Identity:** Smith, Lookahead, 2021, arXiv:2101.12345v2\n"
                                                 "## Results\nACH 1/2 (cites 1905.00001).\n"),
                                ("bounds.md", bounds)))
        out = self.ri("file-cards", self.R, t1)
        self.assertIn(f"S01 <- tasks/{t1}/S01.md", out)
        self.assertIn(f"S03 <- tasks/{t1}/NEW-smith.md (new card)", out)
        self.assertEqual(self.path("sources", "S03.md").read_text(encoding="utf-8").splitlines()[0], "# NEW-smith")
        self.assertIn(f"| S03 | NEW-smith.md ({t1}) | sources/S03.md | card |", self.index())
        self.assertIn(f"| card from {t1} | - |", self.index())
        filed = self.path("sources", "bounds.md").read_text(encoding="utf-8")
        self.assertIn("| S01 | M0 | n large | IMP |\n| S03 | M1 | k = 1 | ACH |\n", filed)
        self.assertNotIn("| card |", filed)
        self.assertNotIn("NEW-smith", filed)
        t2, _ = self.lit("LANDSCAPE", files=(
            ("NEW-smith-v2.md", "# Smith (version 2)\nTitle: Lookahead again\narXiv 2101.12345\n"),
            ("NEW-lee.md", "# Lee\nTitle: Advice\nDOI: 10.1145/123.456.\n"),
            ("bounds.md", "NEW-smith-v2: ACH 2/3 in M1 (Thm 1)\nNEW-lee: IMP 3/4 in M2\na row with no card name\n")))
        t3, _ = self.lit("TARGETED", files=(("NEW-lee-again.md", "# Lee et al.\nTitle: Something else\n"
                                                                 "doi.org/10.1145/123.456\n"),
                                            ("bounds.md", "Lee bound holds for k >= 2 (Thm 4)\n")))
        out = self.ri("file-cards", self.R, t2, t3)
        self.assertIn("NEW-smith-v2.md: duplicate of S03", out)
        self.assertIn(f"S04 <- tasks/{t2}/NEW-lee.md (new card)", out)
        self.assertIn("NEW-lee-again.md: duplicate of S04", out)  # by DOI, though the titles differ
        self.assertIn(f"{t2}: bounds.md row with no card name: a row with no card name", out)
        idx = self.index()
        self.assertIn(f"| - | NEW-smith-v2.md ({t2}) | tasks/{t2}/NEW-smith-v2.md | card |", idx)
        self.assertIn("| duplicate of S03 | - |", idx)
        self.assertIn(f"| - | NEW-lee-again.md ({t3}) | tasks/{t3}/NEW-lee-again.md | card |", idx)
        filed = self.path("sources", "bounds.md").read_text(encoding="utf-8")
        self.assertIn("S03: ACH 2/3 in M1 (Thm 1)\nS04: IMP 3/4 in M2\nS04: Lee bound holds for k >= 2 (Thm 4)\n", filed)
        self.assertFalse(self.path("sources", "S05.md").exists())
        self.assertEqual(self.state()["counters"]["S"], 4)
        self.assertIn(f"{t1}: already filed", self.ri("file-cards", self.R, t1))
        t4, _ = self.lit(files=(("S01.md", "# S01\nTitle: Paper A\nAuthors: X. Y\n## Results\nIMP 2, with the full "
                                           "proof sketch and more detail.\n"),))
        self.assertIn(f"S01 <- tasks/{t4}/S01.md (larger); tasks/{t1}/S01.md kept as a duplicate row",
                      self.ri("file-cards", self.R, t4))
        self.assertIn("more detail", self.path("sources", "S01.md").read_text(encoding="utf-8"))
        self.assertIn(f"| - | S01.md ({t1}) | tasks/{t1}/S01.md | card |", self.index())
        self.assertIn("check OK", self.ri("check", self.R))

    def test_file_cards_copies_raw_downloads_with_index_rows(self):
        t1, _ = self.lit("LANDSCAPE", files=(("raw/smith.pdf", b"%PDF-1.4 smith"), ("raw/sub/lee notes.txt", "text")))
        out = self.ri("file-cards", self.R, t1)
        self.assertIn(f"S03 <- tasks/{t1}/raw/smith.pdf -> sources/raw/{t1}/smith.pdf", out)
        self.assertEqual(self.path("sources", "raw", t1, "smith.pdf").read_bytes(), b"%PDF-1.4 smith")
        self.assertTrue(self.path("sources", "raw", t1, "sub", "lee notes.txt").is_file())
        idx = self.index()
        self.assertIn(f"| S03 | raw/smith.pdf ({t1}) | sources/raw/{t1}/smith.pdf | paper-pdf | 14 B | downloaded by {t1} | - |",
                      idx)
        self.assertIn(f"| S04 | raw/sub/lee notes.txt ({t1}) | sources/raw/{t1}/sub/lee notes.txt | notes |", idx)
        self.assertFalse(self.path("sources", "bounds.md").exists())
        live = self.task("literature-reviewer", "SURVEY")
        other = self.task("scout", "EXPLORE")
        self.ri("task", "set", self.R, other, "done")
        out = self.ri("file-cards", self.R, live, other)
        self.assertIn(f"{live}: not a finished literature-reviewer task (literature-reviewer, queued): ingest it first", out)
        self.assertIn(f"{other}: not a finished literature-reviewer task (scout, done)", out)
        self.assertIn("nothing filed", out)
        self.ri("file-cards", self.R, "T099", code=2)

    def test_file_cards_after_model_logs_new_source_except_uncarded_inputs(self):
        early, _ = self.lit(files=(("NEW-early.md", "# Early\nTitle: Early\n"),))
        self.path("model.md").write_text("Model it.\n- sources/raw/papers/b.pdf (uncarded)\n", encoding="utf-8")
        model = self.task("investigator", "MODEL", fill=False, extra=("--assignment-file", "model.md"))
        self.assertNotIn("new-source", self.ri("file-cards", self.R, early))  # MODEL has not finished
        self.ri("task", "set", self.R, model, "done")
        self.ri("q", "add", self.R, "--title", "lane")
        self.ri("q", "set", self.R, "Q01", "--status", "active")
        self.write("lanes/Q01/statement.md", "Background. Read: Smith (arXiv 2101.12345).\n")
        self.ri("q", "add", self.R, "--title", "other lane")
        self.ri("q", "set", self.R, "Q02", "--status", "active")
        late, _ = self.lit(files=(("S01.md", "# S01\nTitle: A\n"), ("S02.md", "# S02\nTitle: B\n"),
                                  ("NEW-smith.md", "# Smith\nIdentity: arXiv:2101.12345\n")))
        out = self.ri("file-cards", self.R, late)
        self.assertIn("S02: no new-source event (sources/raw/papers/b.pdf was an uncarded input of MODEL)", out)
        evs = [(e["type"], e["lane"], e["note"]) for e in self.state()["events"]]
        self.assertEqual(evs, [("new-source", None, f"S01 filed from {late} (S01.md)"),
                               ("new-source", "Q01", f"S04 filed from {late} (NEW-smith.md)")])
        self.assertIn("E2 new-source Q01 (HELD until RENEW): S04", out)
        self.assertEqual(self.state()["questions"]["Q01"]["held_by"], ["E2"])
        self.assertNotIn("held_by", self.state()["questions"]["Q02"])
        self.assertIn("Q01 HELD by E2 (new-source) until RENEW", self.status())

    def test_ingest_prints_settles_as_hit_bridges_as_context_and_follow_ups(self):
        land, out = self.lit("LANDSCAPE", files=(("landscape.md", "already studied: ..."), ("NEW-smith.md", "# S\n")),
                             fields=("found: bridges (Smith 2021 studies T with lookahead)", "web: yes",
                                     "follow_ups: [TARGETED lookahead lower bound for Q01; TARGETED advice for M1]"))
        self.assertIn(f"context: pass tasks/{land}/landscape.md by path to MODEL, SELECT and the lane's next "
                      "summarizers; no event", out)
        self.assertIn("outer work: TARGETED lookahead lower bound for Q01; TARGETED advice for M1 (program.md sec. 2 "
                      "step 3: while MODEL runs, never in its blocking wave; later the next SELECT or RENEW re-lists them)",
                      out)
        self.assertIn(f"next: file-cards RUN {land} (1 card)", out)
        self.assertNotIn("literature-hit", out)
        tgt, out = self.lit("TARGETED", fields=("found: settles (S05 Thm 3 answers Q02 fully)", "follow_ups: none"))
        self.assertIn("literature-hit: event --type literature-hit [--lane Q02 if it names that question's claim] "
                      "--note-file <file> (program.md sec. 7)", out)
        self.assertNotIn("outer work", out)
        self.assertNotIn("file-cards", out)
        self.assertNotIn("focused mode: hold", out)
        _, out = self.lit("SURVEY", fields=("found: bridges",))
        self.assertIn("result.md by path to MODEL", out)  # no landscape.md or targeted.md
        self.assertEqual(self.state()["events"], [])  # ingest logs nothing: the orchestrator decides
        self.assertIn(f"S03 <- tasks/{land}/NEW-smith.md (new card)", self.ri("file-cards", self.R, land))
        self.assertEqual(self.state()["tasks"][tgt]["status"], "done")

    def focused_run(self):
        self.R = str(Path(self.tmp.name, "f"))
        self.ri("init", self.R, "--objective", "claim", "--mode", "focused")
        self.ri("q", "add", self.R, "--title", "claim", "--model", "M1")
        self.ri("q", "set", self.R, "Q01", "--status", "active", "--rung", "R1")
        self.ri("round", self.R, "Q01", "--open")

    def test_focused_literature_hit_with_lane_prints_hold_rule(self):
        self.ri("q", "add", self.R, "--title", "program lane")
        self.assertNotIn("focused mode: hold", self.ri("event", self.R, "--type", "literature-hit", "--lane", "Q01"))
        self.focused_run()
        out = self.ri("event", self.R, "--type", "literature-hit", "--lane", "Q01", "--note", "S05 settles it")
        self.assertIn("note: focused mode: hold Q01 (--lane) only if the source refutes the claim or the contract asks "
                      "whether it is known (program.md sec. 3); else log it without --lane and tell the user", out)
        self.assertEqual(self.state()["questions"]["Q01"]["held_by"], ["E1"])  # a note, never a refusal
        self.assertNotIn("focused mode: hold", self.ri("event", self.R, "--type", "literature-hit"))
        _, out = self.lit("SURVEY", fields=("found: settles (the claim, S01 Thm 2)",))
        self.assertIn("  focused mode: hold Q01 (--lane) only if", out)

    def test_focused_end_routes_literature_events_to_consolidation(self):
        self.focused_run()
        self.ri("event", self.R, "--type", "literature-hit", "--lane", "Q01", "--note", "refuting source")
        self.assertIn("events pending: literature-hit Q01 (E1) -> dispatch investigator RENEW", self.status())
        self.ri("event", self.R, "--handled", "E1", "--by", self.task("investigator", "RENEW"))
        c = self.accepted("Q01.R1")  # E2 top-accepted
        self.ri("event", self.R, "--type", "literature-hit", "--lane", "Q01", "--note", "late hit")
        self.ri("event", self.R, "--type", "new-source", "--lane", "Q01", "--note", "S09")
        out = self.status()
        self.assertNotIn("dispatch investigator RENEW", out)
        self.assertIn("Q01 HELD by E3 (literature-hit), E4 (new-source) until consolidation", out)
        self.assertIn(f"Q01 focused, R1 accepted ({c}; target R1): no RENEW for E2 top-accepted, E3 literature-hit, "
                      f"E4 new-source; consolidate Q01.R1 ({c}): copy {c} to reports/Q01-R1-proof-{c}.md now "
                      f"(proof-lane.md sec. 6); writer --cand {c} (no comparator) with a skeptic CLAIM-GATE in parallel "
                      "-> verifier PAPER; then event --handled E2 E3 E4 --by <comparator or writer task>", out)
        self.assertIn("literature-hit", ri.FOCUSED_END_TYPES)
        self.assertIn("new-source", ri.FOCUSED_END_TYPES)

    def test_focused_literature_hit_without_lane_is_context_not_renew(self):
        self.focused_run()
        self.ri("event", self.R, "--type", "literature-hit", "--note", "S05 states a weaker form")
        out = self.status()
        self.assertNotIn("dispatch investigator RENEW", out)
        self.assertIn("E1 literature-hit (no hold): context: its note goes to the lane's next summarizers and the "
                      "closing CLAIM-GATE; no RENEW (program.md sec. 3); the delivery task marks it handled", out)
        self.assertIn("E1 literature-hit: S05 states a weaker form -> first: context:", out)
        c = self.accepted("Q01.R1")
        out = self.status()
        self.assertIn(f"no RENEW for E1 literature-hit, E2 top-accepted; consolidate Q01.R1 ({c})", out)
        R2 = str(Path(self.tmp.name, "p"))  # program mode: still a RENEW
        self.ri("init", R2, "--objective", "x")
        self.ri("event", R2, "--type", "literature-hit", "--note", "x")
        self.R = R2
        self.selected()  # program.md sec. 7: events go to RENEW once the first SELECT has finished
        self.assertIn("events pending: literature-hit (E1) -> dispatch investigator RENEW", self.ri("status", R2))

    def zip_of(self, name, members):
        p = Path(self.tmp.name, name)
        with zipfile.ZipFile(p, "w", zipfile.ZIP_STORED) as z:
            for n, data in members:
                z.writestr(n, data)
        return p

    def limits(self):
        c = self.path("contract.md").read_text(encoding="utf-8")
        return c.split("## Limits\n", 1)[1].split("\n## ", 1)[0]

    def test_intake_only_prefix_and_recorded_cap_override(self):
        arc = self.zip_of("big.zip", [("b/README.md", "START HERE: docs/a.md"), ("b/docs/a.md", "a"),
                                      ("b/docs/sub/c.md", "c"), ("b/data/x.bin", os.urandom(700_000)),
                                      ("b/data/y.bin", os.urandom(700_000))])
        out = self.ri("intake", self.R, "--archive", arc, "--max-mb", "1", code=1)
        self.assertIn("over the 1 MB cap. Extract part with --only <path prefix>, or raise --max-mb only for a genuine "
                      "bundle (it is recorded in contract.md); largest parts: b/data/ (1.3 MB)", out)
        out = self.ri("intake", self.R, "--archive", arc, "--max-mb", "1", "--only", "b/docs/", "--only", "b/README.md")
        self.assertIn("3 files into sources/raw/", out)
        self.assertIn("skipped 2 outside --only", out)
        idx = self.index()
        self.assertIn("| b/README.md | sources/raw/b/README.md | user-notes |", idx)  # the bundle root is still b/
        self.assertIn("| b/docs/a.md | sources/raw/b/docs/a.md | user-notes |", idx)  # README target
        self.assertIn("| b/docs/sub/c.md | sources/raw/b/docs/sub/c.md | notes |", idx)
        self.assertNotIn(".bin", idx)
        self.assertNotIn("Intake cap", self.limits())
        out = self.ri("intake", self.R, "--archive", arc, "--only", "b/nothing", code=1)
        self.assertIn("top-level entries: b/README.md, b/data, b/docs", out)
        self.ri("intake", self.R, "--archive", arc, "--only", "..", code=2)
        self.ri("intake", self.R, "--archive", arc, "--only", "/", code=2)
        out = self.ri("intake", self.R, "--archive", arc, "--max-mb", "600")
        today = ri.now()[:10]
        self.assertIn(f"contract.md Limits: Intake cap raised to 600 MB (default 500) on {today}; tell the user.", out)
        self.assertEqual(self.limits(), "- User limits: <time, rounds, cost, stop conditions; \"none stated\" if none>\n"
                                        f"- Intake cap raised to 600 MB (default 500) on {today}; tell the user.\n")
        self.assertIn("## Lane budgets", self.path("contract.md").read_text(encoding="utf-8"))
        self.assertIn("check OK", self.ri("check", self.R))

    def test_intake_bundled_code_line_and_scout_authorization(self):
        out = self.ri("intake", self.R, "--archive", self.zip_of("code.zip", [("sim.py", "print(1)"),
                                                                              ("lib/util.jl", "x"), ("p.pdf", "%PDF")]))
        self.assertIn("bundle holds 2 code files: ask once in your opening message whether scouts may run copies in "
                      "their task directory; proceed meanwhile", out)
        self.assertIn("- Bundled code: not asked (2 code files; runtime.md §1)\n", self.limits())
        out = self.ri("intake", self.R, "--archive", self.zip_of("more.zip", [("run.py", "x")]))
        self.assertNotIn("bundle holds", out)
        self.assertEqual(self.limits().count("Bundled code"), 1)
        self.assertNotIn(ri.BUNDLED_CODE_OK, self.assignment(self.task("scout", "EXPLORE")))
        c = self.path("contract.md")
        for answer, granted in (("not allowed", False), ("allowed", True)):
            text = re.sub(r"Bundled code: [^(\n]*", f"Bundled code: {answer} ", c.read_text(encoding="utf-8"))
            c.write_text(text, encoding="utf-8")
            self.assertEqual(ri.BUNDLED_CODE_OK in self.assignment(self.task("scout", "EXPLORE")), granted, answer)
        self.assertIn(ri.BUNDLED_CODE_OK, self.assignment(self.task("scout", "SANITY")))
        self.assertNotIn(ri.BUNDLED_CODE_OK, self.assignment(self.task("skeptic", "CLAIM-GATE")))
        self.assertNotIn("bundle holds", self.ri("intake", self.R, "--archive", self.zip_of("t.zip", [("t.md", "t")])))

    def test_scale_note_for_large_index(self):
        idx = self.path("sources", "index.md")
        base = idx.read_text(encoding="utf-8")
        rows = "".join(f"| S{i:02d} | f{i} | sources/raw/f{i} | other | 1 B | readable | - |\n" for i in range(3, 2001))
        idx.write_text(base + rows, encoding="utf-8")  # 2,000 rows: no note
        self.assertNotIn("Scale note", self.assignment(self.task("literature-reviewer", "SURVEY")))
        idx.write_text(base + rows + "| - | dup | tasks/T001/NEW-x.md | card | 1 B | duplicate of S01 | - |\n",
                       encoding="utf-8")
        note = "Scale note: sources/index.md has 2001 rows; search it for the rows named here; never read it whole."
        for role, mode in (("literature-reviewer", "SURVEY"), ("investigator", "MODEL"), ("skeptic", "CLAIM-GATE")):
            self.assertIn(note, self.assignment(self.task(role, mode)), role)
        for role, mode in (("scout", "EXPLORE"), ("summarizer", None), ("writer", None)):
            self.assertNotIn("Scale note", self.assignment(self.task(role, mode)), role)
        lit = self.task("literature-reviewer", "LANDSCAPE")
        self.assertEqual(self.assignment(self.ri("task", "new", self.R, "--redo", lit).split()[0]).count("Scale note"), 1)


if __name__ == "__main__":
    unittest.main()
