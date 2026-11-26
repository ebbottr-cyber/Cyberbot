import unittest
from decimal import Decimal as D
from cyberbot.regimes import classify,evaluate,demo_rows,REGIMES

class RegimeTests(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(classify([100+i for i in range(21)])["id"],"bull")
        self.assertEqual(classify([120-i for i in range(21)])["id"],"bear")
        self.assertEqual(classify([100]*21)["id"],"sideways")
        self.assertEqual(classify([100 if i%2 else 110 for i in range(21)])["id"],"volatile")
    def test_counts_and_no_orders(self):
        d=evaluate(demo_rows("BIST"),mode="synthetic",market="BIST",symbol="demo")
        self.assertEqual(sum(d["regime_counts"].values()),d["tested_observations"])
        self.assertEqual(d["initial_capital"],"45000")
        self.assertFalse(d["automatic_strategy_switching"])
        self.assertFalse(d["promotion_enabled"])
        for reg in REGIMES:
            self.assertEqual(len([x for x in d["strategies"] if x["regime"]==reg]),5)
            self.assertTrue(all(x["observations"]==d["regime_counts"][reg] for x in d["strategies"] if x["regime"]==reg))
    def test_future_bar_not_in_label(self):
        rows=demo_rows("SOLANA")[:120]
        before=evaluate(rows,mode="synthetic",market="SOLANA",symbol="demo")
        rows[-1]={"open":rows[-1]["open"],"close":"1"}
        after=evaluate(rows,mode="synthetic",market="SOLANA",symbol="demo")
        self.assertEqual(before["regime_counts"],after["regime_counts"])
        self.assertEqual(after["initial_capital"],"1000")
    def test_flat_sample(self):
        r=evaluate([{"open":"100","close":"100"}]*120,mode="synthetic",market="NASDAQ",symbol="demo")
        self.assertEqual(r["regime_counts"]["sideways"],60)
        self.assertTrue(all(x["status"]=="insufficient_sample" for x in r["strategies"] if x["regime"]!="sideways"))
