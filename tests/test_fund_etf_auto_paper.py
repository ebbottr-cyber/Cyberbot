"""Regression tests for durable paper intents, replay and immutable evidence."""
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from decimal import Decimal
from tools.fund_etf_auto_paper import run_account


class AutoPaperTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.archive=Path(folder.name)/"prices.sqlite3"
        self.ledger=Path(folder.name)/"paper.sqlite3"
        self.day=date.today()-timedelta(days=20)
        days=[self.day+timedelta(days=i) for i in range(-30,15)]
        rules=dict(source="fixture",calendar_source="fixture",corporate_actions_reviewed=True,
                   timezone="UTC",valid_from=days[0].isoformat(),valid_to=days[-1].isoformat(),
                   buy_price_lag=0,buy_publication_lag=1,buy_settlement_lag=2,
                   sell_price_lag=0,sell_publication_lag=1,sell_settlement_lag=2,fee_bps=25)
        self.account=dict(id="test",market="TEFAS",symbol="AAA",currency="TRY",source="fixture",
            enabled=True,terms_confirmed=True,initial_cash="1000",rules=rules,
            sessions=[dict(date=d.isoformat(),cutoff="13:00") for d in days])
        with closing(sqlite3.connect(self.archive)) as db,db:
            db.execute("CREATE TABLE fund_prices (market TEXT,symbol TEXT,session TEXT,currency TEXT,close TEXT,source TEXT)")
            db.executemany("INSERT INTO fund_prices VALUES (?,?,?,?,?,?)",
                [("TEFAS","AAA",d.isoformat(),"TRY",str(100+i*.1),"fixture") for i,d in enumerate(days)])

    def clock(self,offset=0,hour=15):
        return datetime.combine(self.day+timedelta(days=offset),datetime.min.time(),timezone.utc)+timedelta(hours=hour)

    def report(self,now,*,sell=False,status="research_only"):
        signal=(now.date()-timedelta(days=1)).isoformat()
        m=dict(market="TEFAS",symbol="AAA",currency="TRY",source="fixture",status="research_only",
               last_session=signal,age_days=1,max_drawdown_pct=5,last_20_observation_return_pct=-2 if sell else 4)
        ctx=dict(market="TEFAS",symbol="AAA",status="research_only",cutoff=now.isoformat(),alerts=[])
        return dict(status=status,analysis_cutoff=now.isoformat(),instruments=[
            dict(status="research_review",research_eligible=True,metrics=m,context=ctx,
                rank=dict(research_score=20 if sell else 90,relative_risk_score=20),
                decision=dict(action="WAIT" if sell else "BUY_REVIEW"))])

    def tick(self,offset=0,**kwargs):
        now=self.clock(offset)
        return run_account(self.ledger,self.archive,self.account,self.report(now,**kwargs),now=now)

    def test_buy_dedup_and_sell_settlement(self):
        first=self.tick()
        self.assertEqual(len(first["history"]),1)
        self.assertEqual(first["history"][0]["side"],"BUY")
        self.assertEqual(Decimal(first["reserved_cash"]),200)
        self.assertIsNone(first["pnl"])
        self.assertEqual(len(self.tick()["history"]),1)
        self.assertEqual(len(self.tick(2)["pending"]),1)
        sell=self.tick(4,sell=True)
        self.assertEqual(len(sell["history"]),2)
        self.assertEqual(sell["history"][-1]["side"],"SELL")
        end=self.tick(8,sell=True)
        self.assertEqual(end["pending"],[])
        self.assertEqual(Decimal(end["available_units"]),0)
        self.assertIsNotNone(end["pnl"])
        self.assertFalse(end["real_orders"])

    def test_partial_no_buy_and_disabled(self):
        self.assertEqual(self.tick(status="partial")["history"],[])
        self.account["enabled"]=False
        self.assertEqual(self.tick()["status"],"disabled")

    def test_before_cutoff_no_same_day_price(self):
        now=self.clock(hour=10)
        result=run_account(self.ledger,self.archive,self.account,self.report(now),now=now)
        self.assertEqual(result["history"],[])

    def test_revision_and_terms_blocked(self):
        self.tick()
        self.account["initial_cash"]="2000"
        self.assertEqual(self.tick()["status"],"blocked")
        self.account["initial_cash"]="1000"
        with closing(sqlite3.connect(self.archive)) as db,db:
            db.execute("UPDATE fund_prices SET close='101' WHERE session=?",
                       ((self.day-timedelta(days=1)).isoformat(),))
        self.assertEqual(self.tick()["status"],"blocked")


if __name__=="__main__":
    unittest.main()
