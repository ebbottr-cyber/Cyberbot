import unittest
from cyberbot.robustness import bootstrap,score,evaluate,returns_from
from cyberbot.learning import demo_rows
from cyberbot.strategy_lab import simulate
from decimal import Decimal as D

class RobustnessTests(unittest.TestCase):
    def test_bootstrap_reproducible(self):
        r=[.01,-.02,0,.005,-.001]*20
        self.assertEqual(bootstrap(r),bootstrap(r))
        z=bootstrap([0.]*60)
        self.assertEqual(z["loss_path_pct"],0)
        self.assertEqual(z["p95_drawdown_pct"],0)
        self.assertEqual(z["p05_return_pct"],0)
    def test_score_gates(self):
        mc={"drawdown_over_10_path_pct":0,"loss_path_pct":0,"p95_drawdown_pct":0}
        a=score(folds=12,trades=40,positive=12,net=.2,dd=0,cost_net=.2,mc=mc)
        self.assertEqual(a["score"],100)
        self.assertEqual(a["status"],"research_candidate")
        self.assertIsNone(score(folds=3,trades=2,positive=3,net=.2,dd=0,cost_net=.2,mc=mc)["score"])
        self.assertEqual(score(folds=12,trades=40,positive=12,net=.2,dd=.2,cost_net=.2,mc=mc)["status"],"weak")
    def test_capital_and_references(self):
        d=evaluate(demo_rows(),mode="synthetic",market="BIST",symbol="demo")
        self.assertEqual(d["initial_capital"],"45000")
        self.assertFalse(d["promotion_enabled"])
        cash=next(s for s in d["strategies"] if s["id"]=="cash")
        self.assertIsNone(cash["score"])
        self.assertEqual(cash["monte_carlo"]["p50_ending_capital"],"45000.00")
        self.assertEqual(len(d["strategies"]),5)
        self.assertTrue(all(s["fold_count"]==9 for s in d["strategies"]))
    def test_cost_increase(self):
        bars=[(D(100),D(100))]*60
        a=simulate(bars,"buy_hold",3,20,60)
        b=simulate(bars,"buy_hold",3,20,60,fee=D(".002"),slip=D(".004"))
        self.assertLess(b["return"],a["return"])
        self.assertAlmostEqual(float(a["return"]),__import__("math").prod(1+r for r in returns_from(a))-1)
