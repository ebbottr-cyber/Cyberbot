import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from tools.solana_river_experiment import replay
from tools.solana_learning_dataset import FEATURE_NAMES
from tools.solana_model_experiment import evaluate
from tools.solana_lightgbm_experiment import OptionalModelUnavailable

BASE=datetime(2026,1,1,tzinfo=timezone.utc)
def stamp(s):return (BASE+timedelta(seconds=s)).isoformat()
def row(start,end,y=False,mint="m",part="later"):
    return {"mint":mint,"partition":part,"feature_at":stamp(start),"label_at":stamp(end),
            "features":dict(zip(FEATURE_NAMES,(100000000,10,0,180))),"label":{"positive_quote_net":y}}

class Spy:
    def __init__(self):self.learned=[]
    def learn_one(self,x,y):self.learned.append(y)
    def predict_proba_one(self,x):return {True:sum(self.learned)/len(self.learned) if self.learned else 0.5}

def report():
    rows=[row(i*60,i*60+180,i%2==0,str(i%5),"earlier") for i in range(100)]
    rows += [row(10000+i*60,10180+i*60,i%2==0,str(i%5)) for i in range(50)]
    return {"source_scope":"dexterm_bridge_only","research_only":True,"training_allowed":False,
            "training_performed":False,"model_promoted":False,"real_orders":False,"labels_are_real_fills":False,
            "feature_names":list(FEATURE_NAMES),"examples":rows,"example_count":len(rows),
            "dataset_sha256":"fixture","split_timestamp":stamp(9000)}

class RiverExperimentTests(unittest.TestCase):
    def test_delayed_labels_and_equal_timestamp_batch(self):
        earlier=[row(0,180,False,part="earlier")]
        later=[row(300,480,True),row(480,660,False),row(480,660,True,mint="n"),row(481,661,False)]
        values,info=replay(earlier,later,Spy(),split_timestamp=stamp(300))
        self.assertEqual(values,[0,0,0,0.5])
        self.assertEqual(info["updates_before_last_prediction_batch"],2)
        self.assertEqual(info["pending_labels_at_end"],3)
    def test_future_label_changes_do_not_change_prior_prediction(self):
        earlier=[row(0,180,False,part="earlier")]
        a=[row(300,480,True),row(480,660,False)]
        b=[row(300,480,False),row(480,660,False)]
        self.assertEqual(replay(earlier,a,Spy(),split_timestamp=stamp(300))[0],
                         replay(earlier,b,Spy(),split_timestamp=stamp(300))[0])
    def test_partition_and_horizon_validation(self):
        with self.assertRaises(ValueError):replay([row(0,300)],[],Spy(),split_timestamp=stamp(300))
        with self.assertRaises(ValueError):replay([],[row(300,301)],Spy(),split_timestamp=stamp(300))
    def test_optional_gate_and_result(self):
        with patch("tools.solana_model_experiment.fit_river",return_value=([0.8 if i%2==0 else 0.2 for i in range(50)],"mock",{"evaluation_mode":"delayed_prequential"})) as fitter:
            evaluate(report(),include_river=True)
            fitter.assert_not_called()
            d=evaluate(report(),include_river=True,allow_experiment=True)
            self.assertEqual(d["river_status"],"experiment_complete")
            self.assertEqual(d["results"][-1]["later_window"]["balanced_accuracy"],1)
            self.assertFalse(d["results"][-1]["direct_static_comparison"])
            self.assertFalse(d["model_promoted"])
    def test_missing_dependency_preserves_baselines(self):
        with patch("tools.solana_model_experiment.fit_river",side_effect=OptionalModelUnavailable("river_dependency_unavailable")):
            d=evaluate(report(),include_river=True,allow_experiment=True)
            self.assertEqual(d["status"],"experiment_partial")
            self.assertEqual(len(d["results"]),2)
            self.assertFalse(d["weights_updated"])
