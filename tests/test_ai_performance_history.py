"""Synthetic forward-history checks; no native model or external data."""
import json
from datetime import datetime,timedelta,timezone
import unittest
from tools.local_research.ai_performance_history import summarize


def row(t,actual=.1,chronos=.08):
    p={"mode":"forward_shadow_research","context_bars":21,"prediction_bars":1,
       "automatic_promotion":False,"real_orders":False,"last_price":100,
       "predictions":{"naive":0.,"mean":.02,"ar1":.04,"chronos":chronos}}
    o={"target_source_at":(t+timedelta(seconds=50)).isoformat(),
       "actual_return_pct":actual,"execution_verified":False,"real_orders":False,
       "absolute_errors_pct":{k:abs(actual-v) for k,v in p["predictions"].items()}}
    return (int(t.timestamp()//60),(t+timedelta(seconds=15)).isoformat(),json.dumps(p),json.dumps(o))


class ForwardHistoryTests(unittest.TestCase):
    def setUp(self):
        self.t=datetime(2020,1,1,tzinfo=timezone.utc)

    def test_same_target_errors(self):
        r=summarize([row(self.t),row(self.t+timedelta(minutes=1),-.1,-.08)])
        d=r["days"][0]
        self.assertEqual(d["measured_forecasts"],2)
        self.assertAlmostEqual(d["mae_pct"]["chronos"],.02)
        self.assertAlmostEqual(d["chronos_relative_mae_gain_pct"],80)
        self.assertEqual(d["direction_match_pct"]["chronos"],100)
        self.assertEqual(d["sample_status"],"LOW_SAMPLE")

    def test_daily_grouping(self):
        r=summarize([row(self.t),row(self.t+timedelta(days=1))])
        self.assertEqual(len(r["days"]),2)

    def test_invalid_and_duplicate_rejected(self):
        a=row(self.t)
        self.assertEqual(summarize([a,a])["status"],"DATA_REVIEW_REQUIRED")
        o=json.loads(a[3])
        o["absolute_errors_pct"]["chronos"]=9
        self.assertEqual(summarize([(*a[:3],json.dumps(o))])["status"],"DATA_REVIEW_REQUIRED")

    def test_zero_baseline(self):
        d=summarize([row(self.t,0,0)])["days"][0]
        self.assertIsNone(d["chronos_relative_mae_gain_pct"])

    def test_empty(self):
        self.assertEqual(summarize([])["status"],"INSUFFICIENT_EVIDENCE")
