"""Synthetic tests of the common evaluation protocol."""
from datetime import datetime, timedelta, timezone
import json
import unittest
from tools.local_research.paired_ai_review import compare


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


class Online:
    def __init__(self):
        self.events=[]
    def learn_one(self,x,y):
        self.events.append("learn")
    def predict_one(self,x):
        self.events.append("predict")
        return .8


class PairedReviewTests(unittest.TestCase):
    def test_identical_targets(self):
        online=Online()
        def batch(x,y,test):
            self.assertEqual(len(x),84)
            self.assertEqual(len(y),84)
            self.assertEqual(len(test),36)
            return [.7]*len(test)
        result=compare(records(days=20),batch_fit=batch,online_factory=lambda:online)
        self.assertEqual(result["status"],"RESEARCH_MEASURED")
        self.assertEqual(result["test_samples"],36)
        self.assertEqual(result["holdout_days"],6)
        self.assertEqual(online.events,["learn"]*84+["predict","learn"]*36)
        self.assertAlmostEqual(result["daily_weighted_mae_pct"]["lightgbm"],.3)
        self.assertAlmostEqual(result["daily_weighted_mae_pct"]["river"],.2)
        self.assertAlmostEqual(result["daily_weighted_mae_pct"]["chronos"],.1)
        self.assertFalse(result["automatic_promotion"])
        self.assertEqual(result["gemini"],"ADVISORY_ONLY_NOT_RANKED")

    def test_insufficient(self):
        result=compare(records(days=1),batch_fit=lambda *a:self.fail("unexpected fit"))
        self.assertEqual(result["status"],"INSUFFICIENT_EVIDENCE")

    def test_wrong_prediction_count(self):
        with self.assertRaises(ValueError):
            compare(records(days=20),batch_fit=lambda *a:[],online_factory=Online)

    def test_nonfinite(self):
        with self.assertRaises(ValueError):
            compare(records(days=20),batch_fit=lambda *a:[float("inf")]*36,online_factory=Online)

    def test_duplicate(self):
        rows=list(records(days=20))
        rows.insert(1,rows[0])
        with self.assertRaises(ValueError):
            compare(rows)


if __name__ == "__main__":
    unittest.main()
