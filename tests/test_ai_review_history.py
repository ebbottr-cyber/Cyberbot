"""Synthetic tests for review-only degradation warnings."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from tools.local_research.ai_review_history import degradation, history


class ReviewHistoryTests(unittest.TestCase):
    def forward(self,new_mae=.15,new_baseline=.2):
        yesterday=datetime.now(timezone.utc).date()-timedelta(days=1)
        return {"status":"RESEARCH_MEASURED","days":[
            {"day_utc":str(yesterday-timedelta(days=5-i)),
             "utc_day_ended":True,"measured_forecasts":25,
             "mae_pct":{"chronos":.1 if i<3 else new_mae,
                        "naive":.2 if i<3 else new_baseline}}
            for i in range(6)]}

    def test_degradation_requires_both_thresholds(self):
        self.assertEqual(degradation(self.forward())["status"],"REVIEW_DEGRADATION")
        self.assertEqual(degradation(self.forward(.15,.3))["status"],"NO_THRESHOLD_BREACH")
        self.assertFalse(degradation(self.forward())["automatic_action"])

    def test_low_sample_and_truncated_day(self):
        report=self.forward()
        report["days"][0]["measured_forecasts"]=19
        self.assertEqual(degradation(report)["status"],"INSUFFICIENT_EVIDENCE")
        report=self.forward()
        report["days"][0]["window_may_truncate_day"]=True
        self.assertEqual(degradation(report)["status"],"INSUFFICIENT_EVIDENCE")

    def test_missing_and_invalid_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertEqual(history(root,"river")["status"],"NOT_AVAILABLE")
            folder=root/"var/ai"
            folder.mkdir(parents=True)
            with closing(sqlite3.connect(folder/"river-replay-journal.sqlite3")) as db, db:
                db.execute("CREATE TABLE replay_reports (fingerprint TEXT,created_at TEXT,payload TEXT)")
                db.execute("INSERT INTO replay_reports VALUES ('x','2020-01-01T00:00:00+00:00','{}')")
            self.assertEqual(history(root,"river")["status"],"DATA_REVIEW_REQUIRED")

    def test_valid_replay_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            folder=root/"var/ai"
            folder.mkdir(parents=True)
            stamp="2020-01-01T00:00:00+00:00"
            report={"created_at":stamp,"version":"river-forward-replay-1","market":"FUTURES","symbol":"BTCUSDT",
                    "evidence_status":"EXPLORATORY_UNVERIFIED","live_prediction_verified":False,
                    "automatic_promotion":False,"profitability_verified":False,"real_orders":False,
                    "scored":100,"river_version":"0.23.0","paired_mae_pct":{n:.1 for n in
                        ("naive","mean","ar1","chronos","river")}}
            with closing(sqlite3.connect(folder/"river-replay-journal.sqlite3")) as db, db:
                db.execute("CREATE TABLE replay_reports (fingerprint TEXT,created_at TEXT,payload TEXT)")
                db.execute("INSERT INTO replay_reports VALUES (?,?,?)",("x",stamp,json.dumps(report)))
            result=history(root,"river")
            self.assertEqual(result["status"],"REPORTS_AVAILABLE")
            self.assertEqual(result["reports"][0]["samples"],100)
            self.assertTrue(result["reports_may_overlap"])
