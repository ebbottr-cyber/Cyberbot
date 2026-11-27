"""Read-only paired status, synthetic SQLite only."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from tools.local_research.ai_status import paired_status


class PairedStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)

    def write(self, payload):
        with sqlite3.connect(self.folder/"paired-ai-review.sqlite3") as db:
            db.execute("CREATE TABLE paired_reports (fingerprint TEXT,created_at TEXT,payload TEXT)")
            db.execute("INSERT INTO paired_reports VALUES (?,?,?)",
                       ("test","2020-01-01",json.dumps(payload)))

    def report(self):
        return {"version":"paired-ai-review-1",
                "comparison_protocol":"same_targets_frozen_batch_online_replay",
                "evidence_status":"EXPLORATORY_UNVERIFIED",
                "live_prediction_verified":False,"automatic_promotion":False,
                "real_orders":False,"status":"RESEARCH_MEASURED",
                "train_samples":84,"test_samples":36,
                "daily_weighted_mae_pct":{n:1.0 for n in
                    ("naive","mean","ar1","chronos","lightgbm","river")}}

    def test_missing(self):
        self.assertEqual(paired_status(self.folder)["status"],"NOT_AVAILABLE")

    def test_valid(self):
        self.write(self.report())
        result=paired_status(self.folder)
        self.assertEqual(result["status"],"RESEARCH_MEASURED")
        self.assertEqual(result["observations_scored"],36)

    def test_reject_promotion(self):
        self.write({**self.report(),"automatic_promotion":True})
        self.assertEqual(paired_status(self.folder)["status"],"DATA_REVIEW_REQUIRED")

    def test_nonfinite(self):
        p=self.report()
        p["daily_weighted_mae_pct"]["river"]=float("nan")
        self.write(p)
        self.assertEqual(paired_status(self.folder)["status"],"DATA_REVIEW_REQUIRED")


if __name__=="__main__":
    unittest.main()
