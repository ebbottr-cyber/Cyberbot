import os,tempfile,unittest,sqlite3,json
from pathlib import Path
from contextlib import closing
from datetime import datetime,timezone,timedelta
from decimal import Decimal as D
from unittest.mock import patch
from cyberbot import futures_performance as p,futures_pilot as f
AT=datetime(2026,1,1,12,tzinfo=timezone.utc)
class PerformanceTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name);self.now=AT
        e={"CYBERBOT_DB":str(self.root/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(self.root/"learn.sqlite3"),
           "CYBERBOT_WORKER_DB":str(self.root/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(self.root/"pilot.sqlite3"),
           "CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":"","CYBERBOT_OBSERVED_PILOT_ENABLED":"1","CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED":"1",
           "CYBERBOT_FUTURES_PILOT_ENABLED":"1","CYBERBOT_FUTURES_PILOT_SYMBOL":"BTCUSDT","CYBERBOT_PILOT_KILL_SWITCH":"0"}
        env=patch.dict(os.environ,e);env.start();self.addCleanup(env.stop)
    def clock(self):return self.now
    def observe(self,price="100",depth="1000"):
        self.now+=timedelta(seconds=1)
        return f.observe({"market":"FUTURES","symbol":"BTCUSDT","currency":"USDT","contract":"linear_perpetual","source":"fixture",
                          "source_at":self.now.isoformat(),"bid":price,"ask":str(D(price)+D(".1")),"mark":price,
                          "bid_depth_usdt":depth,"ask_depth_usdt":depth,"funding":[]},clock=self.clock)
    def trade(self,side,exit_price):
        self.observe();f.request(side,clock=self.clock);self.observe()
        f.request("CLOSE",clock=self.clock);self.observe(exit_price)
    def report(self):return p.report("BTCUSDT",clock=self.clock)
    def test_empty_read_only(self):
        self.assertEqual(self.report()["status"],"not_initialized");self.assertEqual(list(self.root.iterdir()),[])
    def test_closed_pnl_fees_and_reconciliation(self):
        self.trade("LONG","102");self.trade("SHORT","102")
        path=self.root/"pilot.sqlite3";old=path.read_bytes()
        m=self.report()["metrics"];c=m["closed"]
        self.assertEqual(c["closed_trades"],2);self.assertEqual(c["wins"],1);self.assertEqual(c["losses"],1)
        self.assertEqual(D(c["win_rate_pct"]),50)
        self.assertEqual(D(m["realized_balance_usdt"]),D(f.START)+D(c["net_pnl_usdt"]))
        self.assertEqual(D(m["available_cash_usdt"]),D(f.snapshot(clock=self.clock)["cash"]))
        self.assertGreater(D(c["entry_fees_usdt"]),0);self.assertGreater(D(c["modeled_exit_fees_charged_usdt"]),0)
        self.assertGreater(D(m["realized_max_drawdown_pct"]),0)
        self.assertEqual(m["by_origin"]["manual"]["closed_trades"],2)
        self.assertEqual(path.read_bytes(),old)
    def test_open_and_stale_valuation(self):
        self.observe();f.request("LONG",clock=self.clock);self.observe()
        m=self.report()["metrics"];self.assertTrue(m["open_position"]);self.assertEqual(m["closed"]["closed_trades"],0)
        self.assertIsNone(m["closed"]["win_rate_pct"]);self.assertIsNotNone(m["open_position_unrealized_net_usdt"])
        self.now+=timedelta(seconds=31)
        m=self.report()["metrics"];self.assertIsNone(m["current_modeled_equity_usdt"]);self.assertEqual(m["equity_unavailable_reason"],"stale_quote")
    def test_liquidation_and_depth(self):
        self.observe();f.request("LONG",clock=self.clock);self.observe()
        self.observe("100","0");self.observe("20")
        m=self.report()["metrics"];self.assertEqual(m["closed"]["liquidations"],1)
        self.assertEqual(D(m["closed"]["modeled_exit_fees_charged_usdt"]),0)
        self.assertGreater(m["depth_skipped_samples"],0)
    def test_missing_history_rejected_and_bound(self):
        self.trade("LONG","101")
        with patch.object(p,"MAX_EVENTS",1):self.assertEqual(self.report()["status"],"event_limit_exceeded")
        with closing(sqlite3.connect(self.root/"pilot.sqlite3")) as db:
            db.execute("DELETE FROM observed_events WHERE event='open_fill'");db.commit()
        with self.assertRaises(ValueError):self.report()
