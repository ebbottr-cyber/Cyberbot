"""Deterministic offline tests: no external market data or orders."""
import unittest
from datetime import date, timedelta
from tools.fund_etf_walkforward import evaluate, simulate


def observations(n=500):
    start = date.today()-timedelta(days=n+1)
    return [((start+timedelta(days=i)).isoformat(),
             100+i*.05+((i%23)-11)*.08) for i in range(n)]


class WalkForwardTests(unittest.TestCase):
    def test_insufficient(self):
        self.assertEqual(evaluate(observations(90))["status"], "insufficient_evaluation")

    def test_fold_order_and_no_test_selection(self):
        rows = observations()
        a = evaluate(rows, train=100, test=50)
        self.assertGreaterEqual(a["fold_count"], 3)
        changed = rows[:161]+[(d, p*1.5) for d,p in rows[161:]]
        b = evaluate(changed, train=100, test=50)
        self.assertEqual(a["folds"][0]["selected"], b["folds"][0]["selected"])
        self.assertEqual(a["folds"][0]["training"], b["folds"][0]["training"])
        for fold in a["folds"]:
            self.assertLess(fold["train_end"], fold["test_start"])
        self.assertFalse(a["model_promoted"])
        self.assertFalse(a["real_orders"])

    def test_costs_reduce_constant_price_roundtrip(self):
        prices = [100.0]*100
        free = simulate(prices, 65, 80, "buy_hold", 0, 1)
        paid = simulate(prices, 65, 80, "buy_hold", 25, 1)
        self.assertAlmostEqual(free["return_pct"], 0)
        self.assertLess(paid["return_pct"], 0)
        self.assertEqual(paid["trades"], 2)

    def test_signal_lag(self):
        prices = [100.0]*100
        prices[70] = 120
        # At observation 70, the close is not yet available to the signal.
        # The signal is visible at 71, but final liquidation is precommitted.
        result = simulate(prices, 70, 72, "momentum_20", 0, 1)
        self.assertEqual(result["trades"], 0)

    def test_duplicate_and_future_rejected(self):
        rows = observations()
        with self.assertRaises(ValueError):
            evaluate(rows+[rows[-1]])
        with self.assertRaises(ValueError):
            evaluate(rows+[((date.today()+timedelta(days=1)).isoformat(), 100)])


if __name__ == "__main__":
    unittest.main()
