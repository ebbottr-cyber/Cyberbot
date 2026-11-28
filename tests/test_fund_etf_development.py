"""Offline evidence persistence and guarded dashboard tests."""
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from tools.fund_etf_development import record, overview
from cyberbot.fund_etf_api import development_data, with_fund_development

class DevelopmentTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.archive=Path(folder.name)/"prices.sqlite3"
        self.history=Path(folder.name)/"history.sqlite3"
        with closing(sqlite3.connect(self.archive)) as db,db:
            db.execute("CREATE TABLE fund_prices (market TEXT,symbol TEXT,currency TEXT,source TEXT,session TEXT,close TEXT)")
            db.execute("INSERT INTO fund_prices VALUES ('ETF','AAA','USD','fixture','2025-01-02','100')")
        self.item=dict(metrics=dict(market="ETF",symbol="AAA",currency="USD",source="fixture",last_session="2025-01-02"),
            backtest=dict(status="offline_research",real_orders=False,fold_count=3,summary={},cost_bps=25),
            model_review=dict(status="no_eligible_model",real_orders=False,ranking={"results":[{"model":"fixture","brier":.3}]}))
    def tick(self):
        return record(self.history,self.archive,self.item,"2025-01-03T10:00:00+00:00")
    def test_dedup_and_separate_stages(self):
        self.assertEqual(self.tick(),2)
        self.assertEqual(self.tick(),0)
        result=overview(self.history)
        self.assertEqual(result["markets"][1]["records"],2)
        self.assertEqual(len(result["recent"]),2)
        self.assertFalse(result["independent_evidence_verified"])
    def test_changed_prices_new_record(self):
        self.tick()
        with closing(sqlite3.connect(self.archive)) as db,db:
            db.execute("UPDATE fund_prices SET close='101'")
        self.assertEqual(self.tick(),2)
        self.assertEqual(overview(self.history)["markets"][1]["records"],4)
    def test_insufficient_not_counted_and_retry(self):
        self.item["backtest"]["status"]="insufficient_evaluation"
        self.item["model_review"]["status"]="blocked"
        self.assertEqual(self.tick(),0)
        self.item["backtest"]["status"]="offline_research"
        self.assertEqual(self.tick(),1)
    def test_endpoint_and_idempotent_fragment(self):
        self.tick()
        with patch.dict(os.environ,{"CYBERBOT_FUND_ETF_DEVELOPMENT":str(self.history),
                                   "CYBERBOT_FUND_ETF_SNAPSHOT":str(self.history.parent/"missing.json")}):
            response=development_data()
        data=json.loads(response.body)
        self.assertEqual(response.status_code,200)
        self.assertEqual(data["paper_accounts"],[])
        self.assertFalse(data["real_orders"])
        html=with_fund_development("<main>original</main>")
        self.assertIn("original",html)
        self.assertEqual(html,with_fund_development(html))
        self.assertEqual(html.count('id="fundDevelopment"'),1)

if __name__=="__main__":
    unittest.main()
