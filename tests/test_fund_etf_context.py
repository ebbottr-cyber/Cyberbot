"""Offline regression tests for point-in-time context and risk gate."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from tools.fund_etf_context import context, contextual_decision


class ContextTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db=Path(folder.name)/"context.sqlite3"
        self.spec=[dict(source="FRED",series="RATE",unit="percent",max_age_days=30,change_threshold=2)]
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TABLE fund_macro (source TEXT,series TEXT,unit TEXT,period TEXT,released TEXT,value TEXT)")
            db.executemany("INSERT INTO fund_macro VALUES (?,?,?,?,?,?)",[
                ("FRED","RATE","percent","2025-01-01","2025-01-02","3"),
                ("FRED","RATE","percent","2025-01-03","2025-01-04","4"),
                ("FRED","RATE","percent","2025-01-03","2025-01-09","99")])
            db.execute("CREATE TABLE fund_news (id TEXT,market TEXT,symbol TEXT,source TEXT,title TEXT,url TEXT,published TEXT)")
            db.executemany("INSERT INTO fund_news VALUES (?,?,?,?,?,?,?)",[
                ("old","ETF","ABC","fixture","Old","https://example.com/old","2025-01-07T12:00:00+00:00"),
                ("future","ETF","ABC","fixture","Future","https://example.com/future","2025-01-08T13:00:00+00:00"),
                ("other","ETF","XYZ","fixture","Other","https://example.com/other","2025-01-07T12:00:00+00:00")])

    def test_no_future_data_or_other_symbol(self):
        result=context(self.db,"ETF","ABC","2025-01-08T12:00:00+00:00",self.spec)
        self.assertEqual(result["macro"][0]["value"],"4")
        self.assertEqual([r["id"] for r in result["news"]],["old"])
        self.assertEqual(result["status"],"review_required")

    def test_stale_series(self):
        result=context(self.db,"ETF","ABC","2025-03-01T12:00:00Z",self.spec)
        self.assertEqual(result["macro"][0]["status"],"stale")
        self.assertEqual(result["status"],"review_required")

    def test_defer_buy_not_exit(self):
        metrics=dict(status="research_only",market="ETF",symbol="ABC",last_session="2025-01-07",
                     age_days=1,max_drawdown_pct=5,last_20_observation_return_pct=4)
        ranking=dict(research_score=90,relative_risk_score=20)
        info=context(self.db,"ETF","ABC","2025-01-08T12:00:00Z",self.spec)
        self.assertEqual(contextual_decision(metrics,ranking,info)["action"],"WAIT")
        metrics["max_drawdown_pct"]=30
        self.assertEqual(contextual_decision(metrics,ranking,info,held=True)["action"],"SELL_REVIEW")

    def test_requires_timezone(self):
        with self.assertRaises(ValueError):
            context(self.db,"ETF","ABC","2025-01-08T12:00:00",self.spec)


if __name__=="__main__":
    unittest.main()
