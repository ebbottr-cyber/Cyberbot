import unittest
from cyberbot.strategy_lab import comparison,synthetic,simulate
from decimal import Decimal as D

class StrategyTests(unittest.TestCase):
    def test_demo(self):
        d=synthetic()
        self.assertEqual(len(d["strategies"]),5)
        self.assertFalse(d["promotion_enabled"])
        self.assertEqual(d["holdout_observations"],54)

    def test_cost_flat(self):
        bars=[{"open":"100","close":"100"} for _ in range(80)]
        d=comparison(bars,mode="synthetic",symbol="demo")
        results={r["id"]:r for r in d["strategies"]}
        self.assertLess(D(results["buy_hold"]["holdout_return_pct"]),0)
        self.assertEqual(D(results["cash"]["holdout_return_pct"]),0)
        self.assertIsNone(results["cash"]["win_pct"])

    def test_no_holdout_parameter_leak(self):
        a=[{"open":str(100+i),"close":str(100+i)} for i in range(100)]
        b=a[:70]+[{"open":str(200-i),"close":str(200-i)} for i in range(30)]
        x=comparison(a,mode="synthetic",symbol="x")
        y=comparison(b,mode="synthetic",symbol="x")
        self.assertEqual([s["window"] for s in x["strategies"]],[s["window"] for s in y["strategies"]])
        self.assertEqual([s["training_return_pct"] for s in x["strategies"]],[s["training_return_pct"] for s in y["strategies"]])

    def test_next_open(self):
        bars=[(D(10),D(10)),(D(10),D(11)),(D(11),D(12)),(D(20),D(20))]
        result=simulate(bars,"trend",3,3,4)
        self.assertLess(result["return"],0)
    def test_invalid(self):
        with self.assertRaises(ValueError): comparison([],mode="synthetic",symbol="x")
