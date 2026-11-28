"""Exercise installed numerical models and integrated paper research, offline."""
import importlib.util
import math
import sqlite3
import tempfile
import unittest
from datetime import date,timedelta
from pathlib import Path
from contextlib import closing
from tools.fund_etf_cycle import cycle
from tools.fund_etf_ai_review import model_review
from tools.fund_etf_portfolio import optimize


class FundIntegrationTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db=Path(folder.name)/"fund.sqlite3"
        self.days=[(date.today()-timedelta(days=320-i)).isoformat() for i in range(320)]
        with closing(sqlite3.connect(self.db)) as db,db:
            db.execute("CREATE TABLE fund_prices (market TEXT,symbol TEXT,session TEXT,currency TEXT,close TEXT,source TEXT)")
            for symbol,k in (("AAA",1),("BBB",2)):
                db.executemany("INSERT INTO fund_prices VALUES (?,?,?,?,?,?)",[
                    ("TEFAS",symbol,d,"TRY",str(100+i*.04+math.sin(i*.35*k)*2),"fixture")
                    for i,d in enumerate(self.days)])

    def test_paper_replay_uses_archive(self):
        days=self.days[-5:]
        rules=dict(source="fixture",calendar_source="fixture",corporate_actions_reviewed=True,
                   timezone="UTC",valid_from=days[0],valid_to=days[-1],
                   buy_price_lag=0,buy_publication_lag=1,buy_settlement_lag=2,
                   sell_price_lag=0,sell_publication_lag=1,sell_settlement_lag=2,fee_bps=25)
        job=dict(id="paper",market="TEFAS",symbol="AAA",currency="TRY",source="fixture",
                 rules=rules,sessions=[dict(date=d,cutoff="13:00") for d in days],
                 orders=[dict(id="b",timestamp=days[0]+"T10:00:00+00:00",side="BUY",amount=100)],
                 as_of=days[-1],initial_cash=1000)
        report=cycle(self.db,{"paper_replays":[job]})
        p=report["paper_replays"][0]
        self.assertEqual(p["status"],"paper_replay")
        self.assertIsNotNone(p["pnl"])
        self.assertFalse(p["real_orders"])
        job["prices"]={}
        self.assertEqual(cycle(self.db,{"paper_replays":[job]})["paper_replays"][0]["status"],"blocked")

    @unittest.skipUnless(all(importlib.util.find_spec(n) for n in ("numpy","scipy")),"optional numerical dependencies")
    def test_actual_optimizer(self):
        out=optimize(self.db,"TEFAS",["AAA","BBB"],"TRY","fixture",max_weight=.75)
        self.assertEqual(out["status"],"research_only")
        self.assertAlmostEqual(sum(out["weights"].values()),1)
        self.assertFalse(out["real_orders"])

    @unittest.skipUnless(all(importlib.util.find_spec(n) for n in ("sklearn","lightgbm","xgboost","river")),"optional ML dependencies")
    def test_actual_model_runtime(self):
        out=model_review(self.db,"TEFAS","AAA","TRY","fixture",horizon=1,step=50)
        self.assertEqual(out.get("errors"),{})
        self.assertIn(out["status"],("review_required","no_eligible_model"))
        self.assertEqual(set(out["models"]),{"LogisticRegression","LightGBM","XGBoost","River"})
        self.assertFalse(out["model_promoted"])


if __name__=="__main__":
    unittest.main()
