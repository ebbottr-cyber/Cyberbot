import unittest
from unittest.mock import patch
from tools.solana_native_model_check import run,fixture
from tools.solana_model_experiment import evaluate
from tools.solana_paper_replay import instant
from tools.solana_lightgbm_experiment import OptionalModelUnavailable

class NativeCheckTests(unittest.TestCase):
    def test_opt_in_required(self):
        with patch("tools.solana_native_model_check.evaluate") as f:
            with self.assertRaises(ValueError):run()
            f.assert_not_called()
    def test_fixture_chronology_and_class_support(self):
        r=fixture();cut=instant(r["split_timestamp"])
        self.assertEqual(r["example_count"],180)
        self.assertTrue(all(instant(x["label_at"])<cut for x in r["examples"] if x["partition"]=="earlier"))
        self.assertTrue(all(instant(x["feature_at"])>=cut for x in r["examples"] if x["partition"]=="later"))
        self.assertEqual(evaluate(r,allow_experiment=True)["blockers"],[])
    def test_unavailable_native_dependencies_do_not_pass(self):
        with patch("tools.solana_model_experiment.fit_lightgbm",side_effect=OptionalModelUnavailable("missing")),patch("tools.solana_model_experiment.fit_river",side_effect=OptionalModelUnavailable("missing")):
            d=run(enabled=True)
        self.assertEqual(d["status"],"native_check_incomplete")
        self.assertFalse(d["native_optional_model_fit_verified"])
        self.assertFalse(d["real_orders"])
        self.assertFalse(d["model_saved"])
