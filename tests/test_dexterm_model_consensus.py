import unittest
from unittest.mock import patch
from tools.dexterm_model_consensus import analyze
from tools.dexterm_model_experiment import evaluate
from tools.dexterm_learning_dataset import FEATURE_NAMES

def report():
    rows=[]
    for part,n in (("earlier",100),("later",50)):
        for i in range(n):
            y=i%2==0
            rows.append({"mint":str(i%5),"partition":part,
                         "features":dict(zip(FEATURE_NAMES,(100000000,100 if y else -100,0,180))),
                         "label":{"positive_quote_net":y}})
    return {"source_scope":"dexterm_bridge_only","research_only":True,"training_allowed":False,
            "training_performed":False,"model_promoted":False,"real_orders":False,"labels_are_real_fills":False,
            "feature_names":list(FEATURE_NAMES),"examples":rows,"example_count":len(rows),"dataset_sha256":"fixture"}

class ModelConsensusTests(unittest.TestCase):
    def test_agreement_and_abstention_accounting(self):
        d=analyze([1,0,1,0],{"logistic_baseline":[.9,.2,.9,.4],"lightgbm":[.8,.1,.1,.45]})
        self.assertEqual(d["counts"],{"joint_positive":1,"joint_nonpositive":1,"disagreement":1,"uncertain":1})
        self.assertEqual(d["covered_accuracy"],1)
        self.assertEqual(d["coverage_pct"],50)
        self.assertFalse(d["trade_eligible"])
    def test_missing_model_blocks_and_no_vote_from_river(self):
        d=analyze([1],{"logistic_baseline":[.9]})
        self.assertEqual(d["missing_models"],["lightgbm"])
        self.assertEqual(d["status"],"consensus_blocked")
        with self.assertRaises(ValueError):analyze([1],{"river_logistic":[.9]})
    def test_invalid_alignment_and_probabilities(self):
        for values in ([],[float("nan")],[1.1]):
            with self.assertRaises(ValueError):analyze([1],{"logistic_baseline":values})
    def test_full_abstention_has_no_accuracy(self):
        d=analyze([1,0],{"logistic_baseline":[.5,.4],"lightgbm":[.55,.45]})
        self.assertIsNone(d["covered_accuracy"])
        self.assertEqual(d["abstained_samples"],2)
    def test_experiment_gate_and_shared_predictions(self):
        d=evaluate(report())
        self.assertEqual(d["consensus"]["status"],"blocked_by_experiment_gate")
        with patch("tools.dexterm_model_experiment.fit_lightgbm",return_value=([.8 if i%2==0 else .2 for i in range(50)],"mock")):
            d=evaluate(report(),allow_experiment=True,include_lightgbm=True)
        self.assertEqual(d["consensus"]["sample_count"],50)
        self.assertEqual(d["consensus"]["status"],"consensus_diagnostic_complete")
        self.assertFalse(d["consensus"]["model_promoted"])
        self.assertFalse(d["real_orders"])
