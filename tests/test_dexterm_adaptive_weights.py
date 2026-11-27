import unittest
from datetime import datetime,timezone,timedelta
from tools.dexterm_adaptive_weights import replay
from tools.dexterm_model_experiment import evaluate
from tools.dexterm_learning_dataset import FEATURE_NAMES

BASE=datetime(2026,1,1,tzinfo=timezone.utc)
def stamp(s):return (BASE+timedelta(seconds=s)).isoformat()
def row(s,y=True,mint="m"):
    return {"mint":mint,"partition":"later","feature_at":stamp(s),"label_at":stamp(s+180),
            "label":{"positive_quote_net":y}}
def probs(n):return {"logistic_baseline":[.99]*n,"lightgbm":[.01]*n}

class AdaptiveWeightTests(unittest.TestCase):
    def test_no_equal_timestamp_label_leak(self):
        rows=[row(i*180) for i in range(25)]
        d=replay(rows,probs(len(rows)),split_timestamp=stamp(0))
        self.assertEqual(d["weight_trace"][1]["mature_labels"],0)
        self.assertEqual(d["weight_trace"][20]["logistic_weight"],.5)
        self.assertGreater(d["weight_trace"][21]["logistic_weight"],.5)
        self.assertLessEqual(d["weight_trace"][-1]["logistic_weight"],.75)
        self.assertFalse(d["weights_updated"])
        self.assertFalse(d["real_orders"])
    def test_future_label_changes_leave_prior_weights_unchanged(self):
        a=[row(i*180) for i in range(30)]
        b=[row(i*180,i<25) for i in range(30)]
        x=replay(a,probs(30),split_timestamp=stamp(0))
        y=replay(b,probs(30),split_timestamp=stamp(0))
        self.assertEqual(x["weight_trace"][:27],y["weight_trace"][:27])
        self.assertFalse(x["performance_improvement_verified"])
    def test_same_timestamp_batch(self):
        rows=[row(0,mint=str(i)) for i in range(20)]+[row(180),row(181)]
        d=replay(rows,probs(len(rows)),split_timestamp=stamp(0))
        self.assertEqual(d["weight_trace"][-2]["logistic_weight"],.5)
        self.assertGreater(d["weight_trace"][-1]["logistic_weight"],.5)
    def test_missing_model_and_invalid_inputs(self):
        d=replay([row(0)],{"logistic_baseline":[.5]},split_timestamp=stamp(0))
        self.assertEqual(d["status"],"adaptive_weights_blocked")
        with self.assertRaises(ValueError):replay([row(0)],probs(1),split_timestamp=stamp(1))
        with self.assertRaises(ValueError):replay([row(0)],{"logistic_baseline":[float("nan")]},split_timestamp=stamp(0))
    def test_experiment_gate_default(self):
        d=evaluate({"source_scope":"dexterm_bridge_only","research_only":True,"training_allowed":False,
                    "training_performed":False,"model_promoted":False,"real_orders":False,"labels_are_real_fills":False,
                    "feature_names":list(FEATURE_NAMES),"examples":[],"example_count":0,"dataset_sha256":"fixture"},
                    include_adaptive=True)
        self.assertEqual(d["adaptive_weights"]["status"],"blocked_by_experiment_gate")
