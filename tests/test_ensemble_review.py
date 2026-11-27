"""Synthetic tests for ensemble weights and chronological label isolation."""
from datetime import datetime,timedelta,timezone
import json
import unittest
from tools.local_research.ensemble_review import compare, WEIGHTS


def rows(change_holdout=False):
    start=datetime(2020,1,1,tzinfo=timezone.utc)
    for day in range(12):
        for i in range(10):
            t=start+timedelta(days=day,minutes=22*i)
            actual=.1 if not change_holdout or day<9 else -.2
            p={"mode":"forward_shadow_research","context_bars":21,"prediction_bars":1,
               "automatic_promotion":False,"real_orders":False,"last_price":100,
               "predictions":{"naive":0.,"mean":.02,"ar1":.04,"chronos":.08}}
            o={"target_source_at":(t+timedelta(seconds=50)).isoformat(),
               "actual_return_pct":actual,"execution_verified":False,"real_orders":False,
               "absolute_errors_pct":{k:abs(actual-v) for k,v in p["predictions"].items()}}
            yield (int(t.timestamp()//60),(t+timedelta(seconds=15)).isoformat(),
                   json.dumps(p),json.dumps(o))


class Online:
    def __init__(self):
        self.events=[]
    def learn_one(self,x,y):
        self.events.append("learn")
    def predict_one(self,x):
        self.events.append("predict")
        return .12


class EnsembleTests(unittest.TestCase):
    def test_weight_grid(self):
        for w in WEIGHTS:
            self.assertAlmostEqual(sum(w),1.)
            self.assertTrue(all(.2<=v<=.6 for v in w))

    def test_chronological_isolation(self):
        online=Online()
        def batch(x,y,z):
            self.assertEqual(len(x),60)
            self.assertEqual(y,[.1]*60)
            self.assertEqual(len(z),60)
            return [.1]*len(z)
        r=compare(rows(),batch_fit=batch,online_factory=lambda:online)
        self.assertEqual(r["train_samples"],60)
        self.assertEqual(r["calibration_samples"],30)
        self.assertEqual(r["test_samples"],30)
        self.assertEqual(online.events,["learn"]*60+["predict","learn"]*60)
        self.assertTrue(r["weights_frozen_before_holdout"])
        self.assertFalse(r["automatic_promotion"])
        self.assertFalse(r["real_orders"])

    def test_holdout_labels_do_not_choose_weights(self):
        def batch(x,y,z):
            return [.09]*len(z)
        a=compare(rows(),batch_fit=batch,online_factory=Online)
        b=compare(rows(True),batch_fit=batch,online_factory=Online)
        self.assertEqual(a["weights"],b["weights"])
        self.assertEqual(a["calibration_mae_pct"],b["calibration_mae_pct"])
        self.assertNotEqual(a["holdout_daily_weighted_mae_pct"],b["holdout_daily_weighted_mae_pct"])

    def test_insufficient_history(self):
        r=compare(list(rows())[:20],batch_fit=lambda *args: self.fail("must not fit"))
        self.assertEqual(r["status"],"INSUFFICIENT_EVIDENCE")

    def test_zero_error_reference_is_not_beaten(self):
        r=compare(rows(),batch_fit=lambda x,y,z:[.1]*len(z),online_factory=Online)
        self.assertEqual(r["status"],"NO_CLEAR_ADVANTAGE")
