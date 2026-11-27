"""No market data or optional ML dependency required."""
import math
import unittest
from tools.local_research import river_review, vps_guard


class TestVpsResearch(unittest.TestCase):
    def test_admission(self):
        vps_guard.self_test()

    def test_predict_before_update(self):
        events = []
        class Fake:
            def predict_one(self, x):
                events.append("predict")
                return 0.
            def learn_one(self, x, y):
                events.append("learn")
        p = [100.]
        for i in range(180):
            p.append(p[-1]*(1+0.001*math.sin(i/7)))
        result = river_review.evaluate(p, model_factory=Fake)
        self.assertEqual(events, ["predict", "learn"]*160)
        self.assertEqual(result["scored"], 100)
        self.assertEqual(result["paired_mae_pct"]["river"], result["paired_mae_pct"]["naive"])
        self.assertFalse(result["automatic_promotion"])
        self.assertFalse(result["live_learning_enabled"])

    def test_insufficient_history(self):
        with self.assertRaises(ValueError):
            river_review.evaluate([100.]*30, model_factory=lambda: None)

    def test_invalid_prediction(self):
        class Fake:
            def predict_one(self, x):
                return float("nan")
            def learn_one(self, x, y):
                raise AssertionError("must reject before learning")
        with self.assertRaises(ValueError):
            river_review.evaluate([100.]*180, model_factory=Fake)


if __name__ == "__main__":
    unittest.main()
