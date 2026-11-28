"""Offline orchestration checks with mocked optional model dependencies."""
import sqlite3
from contextlib import closing
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from tools import fund_etf_ai_review as review


class AIReviewTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)/"prices.sqlite3"
        self.identity = ("ETF", "TEST", "USD", "fixture")
        start = date.today()-timedelta(days=800)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TABLE fund_prices (market TEXT,symbol TEXT,currency TEXT,source TEXT,session TEXT,close TEXT)")
            db.executemany("INSERT INTO fund_prices VALUES (?,?,?,?,?,?)",
                           [self.identity+((start+timedelta(days=i)).isoformat(),str(100+i*.01))
                            for i in range(750)])

    def report(self):
        start = date.today()-timedelta(days=600)
        return {"status":"offline_research","horizon_observations":5,
                "predictions":[{"date":(start+timedelta(days=i)).isoformat(),
                                "actual":1,"baseline":0,"probability":.9}
                               for i in range(500)]}

    def test_common_snapshot_and_no_promotion(self):
        with patch.object(review,"logistic",side_effect=lambda *a,**k:self.report()), \
             patch.object(review,"challengers",side_effect=lambda *a,**k:{n:self.report() for n in ("LightGBM","XGBoost","River")}):
            result = review.model_review(self.path,*self.identity)
        self.assertEqual(result["status"],"review_required")
        self.assertIn(result["candidate"],review.EXPECTED)
        self.assertFalse(result["model_promoted"])
        self.assertFalse(result["real_orders"])

    def test_missing_model_blocks(self):
        with patch.object(review,"logistic",side_effect=ImportError), \
             patch.object(review,"challengers",return_value={}):
            result = review.model_review(self.path,*self.identity)
        self.assertEqual(result["status"],"blocked")
        self.assertIsNone(result["candidate"])

    def test_future_price_blocks(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO fund_prices VALUES (?,?,?,?,?,?)",
                       self.identity+((date.today()+timedelta(days=1)).isoformat(),"100"))
        self.assertEqual(review.model_review(self.path,*self.identity)["status"],"blocked")

    def test_local_decision_fallback(self):
        result = review.research_decision({}, {})
        self.assertEqual(result["decision"]["action"],"WAIT")
        self.assertEqual(result["commentary_provider"],"local_rules")
        self.assertFalse(result["execution_allowed"])

    def test_commentary_cannot_change_action(self):
        with patch.object(review,"explain",return_value={"action":"BUY_REVIEW","commentary":"test","provider":"gemini"}):
            result = review.research_decision({}, {})
        self.assertEqual(result["decision"]["action"],"WAIT")
        self.assertFalse(result["execution_allowed"])


if __name__ == "__main__":
    unittest.main()
