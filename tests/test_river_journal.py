"""Synthetic test only: no River dependency, no market data."""
import json
import unittest
from tools.local_research.river_journal import replay
from datetime import datetime, timedelta, timezone


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


class Spy:
    def __init__(self):
        self.events = []
        self.last = 0.
    def predict_one(self, x):
        self.events.append("predict")
        return self.last
    def learn_one(self, x, y):
        self.events.append("learn")
        self.last = y


class RiverJournalTests(unittest.TestCase):
    def test_reconstruct_without_future_labels(self):
        rows = list(records())
        model = Spy()
        result = replay(rows, model)
        self.assertEqual(model.events, ["predict", "learn"]*72)
        self.assertEqual(result["observations"], 72)
        self.assertEqual(result["scored"], 12)
        self.assertEqual(result["paired_mae_pct"]["river"], 0)
        self.assertFalse(result["live_prediction_verified"])
        self.assertFalse(result["automatic_promotion"])

    def test_deterministic_digest(self):
        rows = list(records())
        self.assertEqual(replay(rows, Spy())["source_fingerprint"],
                         replay(rows, Spy())["source_fingerprint"])

    def test_duplicate_rejected(self):
        rows = list(records())
        rows.insert(1,rows[0])
        with self.assertRaises(ValueError):
            replay(rows, Spy())

    def test_invalid_error_rejected(self):
        row = list(next(records()))
        o = json.loads(row[3])
        o["absolute_errors_pct"]["naive"] = 999
        row[3] = json.dumps(o)
        with self.assertRaises(ValueError):
            replay([row], Spy())

    def test_empty_evidence(self):
        result = replay([], Spy())
        self.assertEqual(result["scored"], 0)
        self.assertEqual(result["paired_mae_pct"], {})


if __name__ == "__main__":
    unittest.main()
