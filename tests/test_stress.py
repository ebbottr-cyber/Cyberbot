import unittest
from decimal import Decimal as D
from cyberbot.stress import run,universe,SCENARIOS
from cyberbot.market import INDEX

class StressTests(unittest.TestCase):
    def test_scenarios(self):
        for name in SCENARIOS:
            with self.subTest(name=name):
                r=run(name,60)
                self.assertTrue(r["passed"],r["invariant_violations"])
                self.assertFalse(r["real_orders"])
                self.assertFalse(r["profitability_verified"])
                self.assertEqual(len(r["curve"]),60)
                self.assertEqual(r["entry_attempts"],r["closed_trades"]+r["rejected_entries"])
                self.assertGreaterEqual(D(r["max_recorded_drawdown_pct"]),0)
                self.assertEqual([a["initial_equity"] for a in r["accounts"]],["45000","1000","1000","1000"])
                self.assertEqual(r["stress_fx"]["status"],"synthetic_reference")
        self.assertIn("DEMO-BIST",INDEX)
        self.assertEqual(len(INDEX["DEMO-BIST"].prices),10)
    def test_gap_guard(self):
        r=run("gap",60)
        self.assertGreater(r["stop_exits"],0)
        self.assertGreater(r["rejected_entries"],0)
        self.assertGreater(D(r["max_recorded_drawdown_pct"]),D("3"))
    def test_bounds(self):
        with self.assertRaises(ValueError):universe("bad",60)
        with self.assertRaises(ValueError):universe("gap",500)
