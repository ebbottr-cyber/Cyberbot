"""Synthetic error categories and isolation tests."""
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile
import unittest
from tools.local_research.ai_error_memory import summarize,run
from tools.local_research.ai_regime_review import context


def row(t,actual=.4,prediction=-.1):
    predictions={"naive":0.,"mean":.02,"ar1":.04,"chronos":prediction}
    mid=100*(1+prediction/100)
    p={"mode":"forward_shadow_research","context_bars":21,"prediction_bars":1,
       "real_orders":False,"automatic_promotion":False,"last_price":100,
       "predictions":predictions,"p10":mid-.1,"p50":mid,"p90":mid+.1,
       "regime_context":context([100]*21)}
    o={"target_source_at":(t+timedelta(seconds=50)).isoformat(),
       "actual_return_pct":actual,"execution_verified":False,"real_orders":False,
       "interval_covered":p["p10"]<=100*(1+actual/100)<=p["p90"],
       "absolute_errors_pct":{k:abs(actual-v) for k,v in predictions.items()}}
    return (int(t.timestamp()//60),(t+timedelta(seconds=15)).isoformat(),
            json.dumps(p),"measured",json.dumps(o))


class ErrorMemoryTests(unittest.TestCase):
    t=datetime(2020,1,1,tzinfo=timezone.utc)

    def test_opposite_direction_large_error_and_interval(self):
        result=summarize([row(self.t)])
        g=next(x for x in result["groups"] if x["regime"]=="all")
        c=g["models"]["chronos"]["counts"]
        self.assertEqual(c["opposite_direction"],1)
        self.assertEqual(c["large_absolute_error"],1)
        self.assertEqual(c["worse_than_zero_return"],1)
        self.assertEqual(g["chronos_interval_counts"],{"above_p90":1})
        self.assertEqual(g["status"],"LOW_SAMPLE")

    def test_deadband_and_covered(self):
        g=summarize([row(self.t,.005,.005)])["groups"][0]
        self.assertEqual(g["models"]["chronos"]["counts"]["opposite_direction"],0)
        self.assertEqual(g["models"]["chronos"]["counts"]["false_movement"],0)
        self.assertEqual(g["chronos_interval_counts"],{"covered":1})

    def test_unmeasurable_not_counted_as_error(self):
        r=row(self.t)
        result=summarize([(*r[:3],"unmeasurable",json.dumps({"reason":"missing_target_sample"}))])
        self.assertEqual(result["measured_records"],0)
        self.assertEqual(result["unmeasurable_records"],{"missing_target_sample":1})
        self.assertEqual(result["status"],"INSUFFICIENT_EVIDENCE")

    def test_inconsistent_coverage_and_duplicate_rejected(self):
        r=row(self.t)
        o=json.loads(r[4])
        o["interval_covered"]=True
        self.assertEqual(summarize([(*r[:4],json.dumps(o))])["status"],"DATA_REVIEW_REQUIRED")
        self.assertEqual(summarize([r,r])["status"],"DATA_REVIEW_REQUIRED")

    def test_old_metadata_is_unknown_not_invented(self):
        r=row(self.t)
        p=json.loads(r[2])
        del p["regime_context"]
        result=summarize([(*r[:2],json.dumps(p),*r[3:])])
        self.assertIn("unknown",[g["regime"] for g in result["groups"]])
        self.assertFalse(result["model_weights_updated"])

    def test_missing_journal_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertEqual(run(root)["status"],"NOT_AVAILABLE")
            self.assertFalse((root/"var").exists())
