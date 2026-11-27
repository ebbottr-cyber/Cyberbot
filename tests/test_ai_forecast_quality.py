import copy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from tools.local_research.ai_forecast_quality import assess,run


def payload():
    return {"mode":"forward_shadow_research","context_bars":21,"prediction_bars":1,
            "real_orders":False,"automatic_promotion":False,"last_price":100,
            "p10":99.9,"p50":100.1,"p90":100.2,
            "predictions":{"naive":0,"mean":.09,"ar1":.08,"chronos":.1},
            "quality_context":{"last_observation_age_seconds":20,
                               "mean_abs_context_return_pct":.1}}


class QualityTests(unittest.TestCase):
    def test_wider_interval_lowers_quality(self):
        p=payload()
        a=assess(p)
        p["p90"]=101
        b=assess(p)
        self.assertGreater(a["quality_score"],b["quality_score"])
        self.assertFalse(a["calibrated_probability"])
        self.assertFalse(a["three_ai_agreement_available"])

    def test_disagreement_lowers_quality(self):
        p=payload()
        a=assess(p)
        p["predictions"]["ar1"]=-.3
        self.assertGreater(a["quality_score"],assess(p)["quality_score"])

    def test_missing_stale_and_flat_context(self):
        p=payload()
        del p["quality_context"]
        self.assertEqual(assess(p)["status"],"INSUFFICIENT_METADATA")
        p=payload()
        p["quality_context"]["last_observation_age_seconds"]=61
        self.assertEqual(assess(p)["status"],"STALE_CONTEXT")
        p=payload()
        p["quality_context"]["mean_abs_context_return_pct"]=0
        self.assertIsNone(assess(p)["quality_score"])

    def test_invalid_forecast(self):
        for key,value in (("p90",99),("p50",101),("p10",float("nan")),("real_orders",True)):
            p=payload()
            p[key]=value
            self.assertEqual(assess(p)["status"],"DATA_REVIEW_REQUIRED")

    def test_latest_stale_score_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            folder=root/"var/ai"
            folder.mkdir(parents=True)
            t=datetime(2026,1,1,0,0,15,tzinfo=timezone.utc)
            with closing(sqlite3.connect(folder/"forward-models-v2.sqlite3")) as db,db:
                db.execute("CREATE TABLE forecasts (market TEXT,symbol TEXT,source TEXT,target_minute INTEGER,created_at TEXT,payload TEXT)")
                db.execute("INSERT INTO forecasts VALUES (?,?,?,?,?,?)",
                           ("FUTURES","BTCUSDT","binance-usdm-public",int(t.timestamp()//60),t.isoformat(),json.dumps(payload())))
            self.assertEqual(run(root,now=t)["status"],"DESCRIPTIVE_ONLY")
            stale=run(root,now=t+timedelta(seconds=61))
            self.assertEqual(stale["status"],"STALE_FORECAST")
            self.assertIsNone(stale["quality_score"])
