"""Synthetic-only tests for the read-only review policy."""
from datetime import datetime, timedelta, timezone
import json
import unittest

from tools.local_research.adaptive_review import review, validated


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


class AdaptiveReviewTests(unittest.TestCase):
    def test_sparse_history(self):
        result = review(list(records(days=1, per_day=4)))
        self.assertEqual(result["status"], "INSUFFICIENT_EVIDENCE")
        self.assertIsNone(result["review_candidate"])

    def test_review_only(self):
        result = review(records())
        self.assertEqual(result["status"], "REVIEW_ONLY")
        self.assertEqual(result["review_candidate"], "chronos")
        self.assertEqual(result["development_blocks"], 48)
        self.assertEqual(result["holdout_blocks"], 24)
        self.assertFalse(result["automatic_model_selection"])

    def test_holdout_regression(self):
        result = review(records(degrade=True))
        self.assertEqual(result["status"], "NO_CANDIDATE")
        self.assertIsNone(result["review_candidate"])

    def test_overlapping_context(self):
        result = review(records(days=1, per_day=4, spacing=1))
        self.assertEqual(result["retained_blocks"], 1)

    def test_late_forecast(self):
        row = list(next(records()))
        row[1] = (datetime.fromisoformat(row[1])+timedelta(seconds=30)).isoformat()
        with self.assertRaises(ValueError):
            validated(row)

    def test_mismatched_errors(self):
        row = list(next(records()))
        outcome = json.loads(row[3])
        outcome["absolute_errors_pct"]["chronos"] = 0
        row[3] = json.dumps(outcome)
        with self.assertRaises(ValueError):
            validated(row)

    def test_duplicate_record(self):
        rows = list(records())
        rows.insert(1, rows[0])
        result = review(rows)
        self.assertEqual(result["rejected_records"], 1)
        self.assertEqual(result["status"], "DATA_REVIEW_REQUIRED")
        self.assertIsNone(result["review_candidate"])


if __name__ == "__main__":
    unittest.main()
