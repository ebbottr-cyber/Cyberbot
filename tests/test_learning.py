import tempfile
import unittest
from pathlib import Path
from cyberbot.learning import research,demo_rows,Journal

class LearningTests(unittest.TestCase):
    def test_folds_and_guard(self):
        r=research(demo_rows(),mode="synthetic",symbol="demo")
        self.assertEqual(len(r["strategies"]),5)
        self.assertFalse(r["promotion_enabled"])
        for s in r["strategies"]:
            self.assertEqual(s["fold_count"],9)
            self.assertEqual(s["folds"][0]["test_start"],60)
            self.assertEqual(s["folds"][-1]["test_end_exclusive"],240)

    def test_no_future_selection(self):
        a=demo_rows()
        b=a[:60]+[{"open":"100","close":"100"} for _ in a[60:]]
        x=research(a,mode="synthetic",symbol="demo")
        y=research(b,mode="synthetic",symbol="demo")
        for s,t in zip(x["strategies"],y["strategies"]):
            self.assertEqual(s["folds"][0]["window"],t["folds"][0]["window"])
            self.assertEqual(s["folds"][0]["training_pct"],t["folds"][0]["training_pct"])
        self.assertNotEqual(x["id"],y["id"])

    def test_journal_dedup(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"learning.sqlite3"
            j=Journal(p)
            r=research(demo_rows(),mode="synthetic",symbol="demo")
            self.assertTrue(j.save(r))
            self.assertFalse(j.save(r))
            self.assertEqual(Journal(p).recent()["counts"],{"synthetic":1})
            self.assertEqual(j.get(r["id"]),r)
            self.assertIsNone(j.get("unknown"))

    def test_short(self):
        with self.assertRaises(ValueError):research([],mode="synthetic",symbol="demo")
