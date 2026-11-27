"""Synthetic tests; no model dependency or network needed."""
from datetime import datetime, timedelta, timezone
import json
import unittest
from tools.local_research.lightgbm_journal import evaluate, prepare


def records(days=12, per_day=6, degrade=False, spacing=22):
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    for day in range(days):
        for i in range(per_day):
            t = start + timedelta(days=day, minutes=i*spacing)
            prediction = -0.5 if degrade and day >= 8 else 0.9
            pred = {"naive": 0.0, "mean": 0.2, "ar1": 0.3, "chronos": prediction}
            actual = 1.0
            p = {"mode": "forward_shadow_research", "context_bars": 21,
                 "prediction_bars": 1, "automatic_promotion": False,
                 "real_orders": False, "last_price": 100, "predictions": pred}
            o = {"target_source_at": (t+timedelta(seconds=50)).isoformat(),
                 "actual_return_pct": actual, "execution_verified": False,
                 "real_orders": False,
                 "absolute_errors_pct": {n: abs(actual-x) for n,x in pred.items()}}
            yield (int(t.timestamp()//60), (t+timedelta(seconds=15)).isoformat(),
                   json.dumps(p), json.dumps(o))


class LightGBMJournalTests(unittest.TestCase):
    def test_short_history_does_not_fit(self):
        result = evaluate(records(days=2), fit_predict=lambda *a: self.fail("unexpected fit"))
        self.assertEqual(result["status"], "INSUFFICIENT_EVIDENCE")

    def test_temporal_holdout(self):
        train, test = prepare(records(days=20, per_day=6))
        self.assertEqual(len(train), 84)
        self.assertEqual(len(test), 36)
        self.assertLess(train[-1][0],test[0][0])
        self.assertLess(train[-1][1],test[0][1])

    def test_paired_evaluation(self):
        def fit(x,y,test_x):
            self.assertEqual(len(x),84)
            self.assertEqual(len(y),84)
            self.assertEqual(len(test_x),36)
            return [1.0]*len(test_x)
        result = evaluate(records(days=20),fit_predict=fit)
        self.assertEqual(result["status"],"RESEARCH_MEASURED")
        self.assertEqual(result["paired_mae_pct"]["lightgbm"],0)
        self.assertFalse(result["automatic_promotion"])

    def test_duplicate_fails(self):
        rows=list(records())
        rows.insert(1,rows[0])
        with self.assertRaises(ValueError):
            prepare(rows)

    def test_bad_prediction_fails(self):
        with self.assertRaises(ValueError):
            evaluate(records(days=20),fit_predict=lambda *a:[float("nan")]*36)


if __name__ == "__main__":
    unittest.main()
