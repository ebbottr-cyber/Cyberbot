import unittest
from tools.solana_model_experiment import evaluate,fit,metrics
from tools.solana_learning_dataset import FEATURE_NAMES

def report(n=100,m=50):
    rows=[]
    for partition,count in (("earlier",n),("later",m)):
        for i in range(count):
            positive=i%2==0
            rows.append({"mint":str(i%5),"partition":partition,
                         "features":dict(zip(FEATURE_NAMES,(100000000,100 if positive else -100,0,180))),
                         "label":{"positive_quote_net":positive}})
    return {"source_scope":"dexterm_bridge_only","research_only":True,"training_allowed":False,
            "training_performed":False,"model_promoted":False,"real_orders":False,"labels_are_real_fills":False,
            "feature_names":list(FEATURE_NAMES),"examples":rows,"example_count":len(rows),"dataset_sha256":"fixture"}

class ModelExperimentTests(unittest.TestCase):
    def test_default_and_small_dataset_blocked(self):
        self.assertFalse(evaluate(report())["experimental_fit_performed"])
        d=evaluate(report(10,10),allow_experiment=True)
        self.assertIn("earlier_sample_count",d["blockers"])
        self.assertFalse(d["training_allowed"])
    def test_experiment_metrics_not_model_promotion(self):
        d=evaluate(report(),allow_experiment=True)
        self.assertTrue(d["experimental_fit_performed"])
        self.assertEqual(d["results"][1]["later_window"]["balanced_accuracy"],1)
        self.assertFalse(d["model_saved"])
        self.assertFalse(d["model_promoted"])
        self.assertFalse(d["real_orders"])
    def test_single_class_and_truncation_blocked(self):
        r=report()
        for x in r["examples"]:x["label"]["positive_quote_net"]=True
        r["bridge_history_truncated"]=True
        d=evaluate(r,allow_experiment=True)
        self.assertIn("later_class_support",d["blockers"])
        self.assertIn("archive_window_truncated",d["blockers"])
    def test_fit_is_deterministic_and_train_only(self):
        train=[([1,2,3,4],0),([1,8,3,4],1)]*50
        a=fit(train);b=fit(train)
        self.assertEqual(a([1,8,3,4]),b([1,8,3,4]))
        self.assertGreater(a([1,8,3,4]),a([1,2,3,4]))
    def test_unexpected_feature_or_flags_rejected(self):
        r=report();r["examples"][0]["features"]["future_price"]=1
        with self.assertRaises(ValueError):evaluate(r,allow_experiment=True)
        r=report();r["real_orders"]=True
        with self.assertRaises(ValueError):evaluate(r,allow_experiment=True)

    def test_lightgbm_lazy_gate_and_default(self):
        from unittest.mock import patch
        with patch("tools.solana_model_experiment.fit_lightgbm") as fitter:
            evaluate(report(),include_lightgbm=True)
            evaluate(report(),allow_experiment=True)
            evaluate(report(10,10),allow_experiment=True,include_lightgbm=True)
            fitter.assert_not_called()
    def test_lightgbm_shared_test_window(self):
        from unittest.mock import patch
        with patch("tools.solana_model_experiment.fit_lightgbm",return_value=([0.8 if i%2==0 else 0.2 for i in range(50)],"mock")) as fitter:
            d=evaluate(report(),allow_experiment=True,include_lightgbm=True)
            train,test=fitter.call_args.args
            self.assertEqual((len(train),len(test)),(100,50))
            self.assertEqual(d["results"][2]["later_window"]["balanced_accuracy"],1)
            self.assertEqual(d["lightgbm_status"],"experiment_complete")
            self.assertFalse(d["model_promoted"])
    def test_missing_optional_dependency_preserves_baselines(self):
        from unittest.mock import patch
        from tools.solana_lightgbm_experiment import OptionalModelUnavailable
        with patch("tools.solana_model_experiment.fit_lightgbm",side_effect=OptionalModelUnavailable("lightgbm_or_native_dependency_unavailable")):
            d=evaluate(report(),allow_experiment=True,include_lightgbm=True)
            self.assertEqual(d["status"],"experiment_partial")
            self.assertEqual(len(d["results"]),2)
            self.assertFalse(d["model_saved"])
    def test_bad_prediction_rejected(self):
        from unittest.mock import patch
        with patch("tools.solana_model_experiment.fit_lightgbm",return_value=([float("nan")]*50,"mock")):
            d=evaluate(report(),allow_experiment=True,include_lightgbm=True)
            self.assertEqual(d["lightgbm_reason"],"invalid_predictions")
            self.assertEqual(len(d["results"]),2)
