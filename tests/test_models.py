import unittest
from cyberbot.models import evaluate,fit_predict,summarize,LocalModelError
from cyberbot.learning import demo_rows

class ModelTests(unittest.TestCase):
    def test_constant(self):
        d=evaluate([100]*120,mode="synthetic")
        self.assertEqual(d["test_observations"],59)
        self.assertTrue(all(x["mae_pct"]==0 for x in d["models"]))
        self.assertFalse(d["promotion_enabled"])
    def test_forecast(self):
        d=evaluate([x["close"] for x in demo_rows()],mode="synthetic")
        self.assertEqual(d["test_observations"],179)
        self.assertEqual(len(d["models"]),3)
        self.assertFalse(d["chronos_connected"])
    def test_invalid(self):
        with self.assertRaises(ValueError):evaluate([float("nan")]*120,mode="synthetic")
        with self.assertRaises(ValueError):evaluate([100]*10,mode="synthetic")
    def test_summary_mock(self):
        def transport(p):
            self.assertFalse(p["stream"])
            self.assertNotIn("tools",p)
            return {"response":"Sentetik araştırma özeti."}
        d=summarize({"mode":"synthetic"},"local-model",transport=transport)
        self.assertFalse(d["verified"])
        self.assertFalse(d["real_orders"])
        with self.assertRaises(LocalModelError):summarize({},"bad model",transport=transport)
        with self.assertRaises(LocalModelError):summarize({},"local-model",transport=lambda p:{})
