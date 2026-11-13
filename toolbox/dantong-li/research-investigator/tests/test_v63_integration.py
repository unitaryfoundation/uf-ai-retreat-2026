"""v6.3 integration tests: behaviours that come from two packages meeting in one function (scripts/ri.py).

Run:  python -B -m unittest discover -s tests -v     (from the skill directory)
"""
import unittest
import zipfile
from pathlib import Path

from test_ri import RiCase, ri


class TestV63Integration(RiCase):
    def setUp(self):
        super().setUp()
        self.init()

    def test_default_model_packet_lists_uncarded_raw_so_its_later_card_is_not_a_new_source(self):
        # Package G (opening MODEL inputs) with Package C (file-cards new-source rule)
        arc = Path(self.tmp.name, "bundle.zip")
        with zipfile.ZipFile(arc, "w") as z:
            z.writestr("papers/a.pdf", "%PDF a")  # S01
        self.ri("intake", self.R, "--archive", arc)
        model = self.task("investigator", "MODEL")
        self.assertIn("- sources/raw/papers/a.pdf (S01, uncarded)", self.assignment(model))
        self.ri("task", "set", self.R, model, "done")
        lit = self.task("literature-reviewer", "SURVEY")
        self.write(f"tasks/{lit}/S01.md", "# S01\nTitle: A\n")
        self.result(lit, "mode: SURVEY")
        self.ri("ingest", self.R, lit)
        out = self.ri("file-cards", self.R, lit)
        self.assertIn("S01: no new-source event (sources/raw/papers/a.pdf was an uncarded input of MODEL)", out)
        self.assertEqual(self.state()["events"], [])

    def test_withdrawn_task_is_not_an_opening_step(self):
        # Package O (withdrawn) with Package B (watchdog's next opening step)
        self.assertIn("next opening step: the first wave", self.status())
        self.task("literature-reviewer", "LANDSCAPE")
        self.assertIn("next opening step: investigator MODEL", self.status())
        model = self.task("investigator", "MODEL")
        self.assertIn("next opening step: skeptic MODEL-GATEs", self.status())
        self.ri("task", "set", self.R, model, "withdrawn", "--note", "never spawned")
        self.assertIn("next opening step: investigator MODEL", self.status())

    def test_comparator_ingest_records_the_selection_and_warns_on_length(self):
        # Package L (st['selected'] from the comparator) with Package M (K74 length warning)
        self.lane()
        c = self.accepted("Q01.R1")
        k = self.task("comparator", ctx="cmp")
        self.write(f"tasks/{k}/selection.md", "word " * 601)
        self.result(k, f"selected: [{c}]")
        out = self.ri("ingest", self.R, k)
        self.assertIn(f"presented: {c} (their dependency closures are load-bearing)", out)
        self.assertIn("warning: selection.md has 601 words for one selected candidate", out)
        self.assertEqual(self.state()["selected"], [c])

    def test_writer_length_budget_counts_its_own_candidates_not_every_earlier_selection(self):
        # Package L (writer --cand adds to st['selected']) with Package M (K74 writer warning)
        self.lane()
        c1 = self.accepted("Q01.R1")
        self.ri("task", "new", self.R, "--role", "writer", "--cand", c1, "--extra", "Write.", "--start")
        c2 = self.accepted("Q01.R2")
        self.assertEqual(self.state()["selected"], [c1])
        w = self.ri("task", "new", self.R, "--role", "writer", "--cand", c2, "--extra", "Write.", "--start").split()[0]
        self.assertEqual(self.state()["selected"], [c1, c2])
        base = ri.words_in(self.path("candidates", f"{c2}.md"))
        self.write(f"tasks/{w}/manuscript.md", "word " * (base + 1201))
        self.result(w, "gaps_sent_back: none")
        self.assertIn(f"more than the presented candidates ({base}) + 1,200", self.ri("ingest", self.R, w))

    def test_combined_model_and_question_gate_result_files_the_patch_and_routes_the_question(self):
        # Package E (model items) with Package A (question items) in one skeptic result (K64)
        q = self.ri("q", "add", self.R, "--title", "claim").split()[0]
        self.r1(q)
        sk = self.ri("task", "new", self.R, "--role", "skeptic", "--mode", "MODEL-GATE", "--title", "M1",
                     "--question", q, "--light", "--start").split()[0]
        self.write(f"tasks/{sk}/patch-M1.md", "Accounting: count queries, not rounds.\n")
        self.result(sk, "mode: MODEL-GATE", "M1: {verdict: PATCH, corrections: none}",
                    f"{q}: {{verdict: ADVANCE, plausibility: mixed}}")
        out = self.ri("ingest", self.R, sk)
        self.assertIn("  M1: PATCH", out)
        self.assertIn(f"= M1 + patch ({sk})", out)
        self.assertIn(f"{q}: ADVANCE (plausibility mixed) -> q set RUN {q} --plausibility mixed", out)
        st = self.state()
        self.assertEqual([m["base"] for m in st["models"].values()], ["M1"])
        self.assertEqual([v["code"] for v in st["questions"][q]["verdicts"]], ["ADVANCE"])


if __name__ == "__main__":
    unittest.main()
