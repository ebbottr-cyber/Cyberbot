"""Synthetic regime tests without external data or native model runtime."""
from datetime import datetime,timedelta,timezone
import json
import unittest
from tools.local_research.ai_regime_review import context,summarize,classify


def row(t,regime):
    p={"mode":"forward_shadow_research","context_bars":21,"prediction_bars":1,
       "real_orders":False,"automatic_promotion":False,"last_price":100,
       "predictions":{"naive":0,"mean":.02,"ar1":.04,"chronos":.08}}
    if regime is not None:
        p["regime_context"]=regime
    o={"target_source_at":(t+timedelta(seconds=50)).isoformat(),
       "actual_return_pct":.1,"execution_verified":False,"real_orders":False,
       "absolute_errors_pct":{n:abs(.1-v) for n,v in p["predictions"].items()}}
    return (int(t.timestamp()//60),(t+timedelta(seconds=15)).isoformat(),json.dumps(p),json.dumps(o))


class RegimeReviewTests(unittest.TestCase):
    t=datetime(2020,1,1,tzinfo=timezone.utc)

    def test_context_regimes(self):
        self.assertEqual(context([100+i*.1 for i in range(21)])["direction"],"bull")
        self.assertEqual(context([100-i*.1 for i in range(21)])["direction"],"bear")
        self.assertEqual(context([100]*21)["direction"],"sideways")
        self.assertEqual(context([100+i%2 for i in range(21)])["volatility"],"high")
        self.assertEqual(classify(.5,.2),("bull","high"))

    def test_old_records_are_not_backfilled(self):
        r=summarize([row(self.t,None)])
        self.assertEqual(r["missing_regime_metadata"],1)
        self.assertEqual(r["status"],"INSUFFICIENT_EVIDENCE")

    def test_spacing_across_regimes(self):
        a=context([100]*21)
        b=context([100+i*.1 for i in range(21)])
        r=summarize([row(self.t,a),row(self.t+timedelta(minutes=1),b),
                     row(self.t+timedelta(minutes=22),b)])
        self.assertEqual(r["retained_blocks"],2)
        self.assertEqual(sum(x["blocks"] for x in r["regimes"]),2)

    def test_invalid_metadata(self):
        a=context([100]*21)
        a["direction"]="bear"
        self.assertEqual(summarize([row(self.t,a)])["status"],"DATA_REVIEW_REQUIRED")

    def test_daily_evidence_threshold(self):
        a=context([100]*21)
        rows=[row(self.t+timedelta(days=d,minutes=22*i),a)
              for d in range(5) for i in range(6)]
        r=summarize(rows)
        side=next(x for x in r["regimes"] if x["direction"]=="sideways" and x["volatility"]=="normal")
        self.assertEqual(side["status"],"DESCRIPTIVE_ONLY")
        self.assertEqual(side["blocks"],30)
        self.assertAlmostEqual(side["daily_weighted_mae_pct"]["chronos"],.02)
        self.assertFalse(r["automatic_strategy_switching"])
