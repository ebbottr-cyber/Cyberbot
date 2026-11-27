import os,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from decimal import Decimal as D
from unittest.mock import patch
from cyberbot import futures_safety as safety,futures_pilot as fut
from cyberbot.providers import binance_observed as b

START=datetime(2026,1,1,12,tzinfo=timezone.utc)
SYM="BTCUSDT"
class SafetyTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        env={"CYBERBOT_DB":str(self.root/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(self.root/"learn.sqlite3"),
             "CYBERBOT_WORKER_DB":str(self.root/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(self.root/"pilot.sqlite3"),
             "CYBERBOT_FUTURES_AI_MEMORY_DB":str(self.root/"memory.sqlite3"),"CYBERBOT_FUTURES_TRAINING_DB":str(self.root/"training.sqlite3"),
             "CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":"","CYBERBOT_PILOT_KILL_SWITCH":"0",
             "CYBERBOT_BINANCE_OBSERVED_ENABLED":"1","CYBERBOT_BINANCE_DATA_RIGHTS_CONFIRMED":"1",
             "CYBERBOT_FUTURES_SAFETY_PROBE_ENABLED":"1","CYBERBOT_FUTURES_PILOT_SYMBOL":SYM,
             "CYBERBOT_OBSERVED_PILOT_ENABLED":"1","CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED":"1",
             "CYBERBOT_FUTURES_PILOT_ENABLED":"1","CYBERBOT_PILOT_INGRESS_ENABLED":"1","CYBERBOT_INGRESS_SOURCE_FUTURES":b.SOURCE}
        p=patch.dict(os.environ,env);p.start();self.addCleanup(p.stop)
        self.now=START;self.calls=[]
    def clock(self):return self.now
    def sleep(self,s):self.now+=timedelta(seconds=s)
    def transport(self,endpoint,params):
        self.calls.append(endpoint);ms=int(self.now.timestamp()*1000)
        if endpoint==b.INFO:return []
        if endpoint==b.BOOK:return {"symbol":SYM,"time":ms,"bidPrice":"100","askPrice":"100.1","bidQty":"10","askQty":"10"}
        if endpoint==b.MARK:return {"symbol":SYM,"time":ms,"markPrice":"100","nextFundingTime":(ms//b.PERIOD_MS+1)*b.PERIOD_MS}
        raise AssertionError(endpoint)
    def test_probe_no_writes_and_advancing_quotes(self):
        d=safety.probe(SYM,clock=self.clock,sleep=self.sleep,transport=self.transport)
        self.assertEqual(d["status"],"quotes_advanced")
        self.assertEqual(d["source_advance_seconds"],3)
        self.assertEqual(self.calls,[b.INFO,b.BOOK,b.MARK]*2)
        self.assertFalse(d["live_connection_sampled"]);self.assertFalse(d["paper_applied"])
        self.assertEqual(list(self.root.iterdir()),[])
    def test_probe_permission_and_nonadvancing(self):
        with patch.dict(os.environ,{"CYBERBOT_FUTURES_SAFETY_PROBE_ENABLED":"0"}):
            with self.assertRaises(ValueError):safety.probe(SYM,clock=self.clock,sleep=self.sleep,transport=self.transport)
        self.assertEqual(self.calls,[])
        d=safety.probe(SYM,clock=self.clock,sleep=lambda _:None,transport=self.transport)
        self.assertEqual(d["status"],"quotes_not_advancing")
    def test_read_only_status_and_kill_switch(self):
        d=safety.status(SYM,clock=self.clock)
        self.assertIn("paper_not_initialized",d["blockers"])
        self.assertEqual(list(self.root.iterdir()),[])
        b.run(apply=True,clock=self.clock,transport=self.transport)
        path=self.root/"pilot.sqlite3";old=path.read_bytes()
        d=safety.status(SYM,clock=self.clock)
        self.assertTrue(d["paper_initialized"]);self.assertTrue(d["entry_gate"])
        self.assertEqual(D(d["modeled_entry_budget_usdt"]),D(5))
        with patch.dict(os.environ,{"CYBERBOT_PILOT_KILL_SWITCH":"1"}):
            d=safety.status(SYM,clock=self.clock)
            self.assertIn("kill_switch",d["blockers"])
            with self.assertRaises(ValueError):fut.request("LONG",clock=self.clock)
        self.assertEqual(path.read_bytes(),old)
    def test_budget_capped_by_remaining_loss_room(self):
        s=fut.initial(SYM);s.update(cash="970.1",day_equity="1000",peak="1000")
        self.assertEqual(fut.entry_risk_budget(s),D(".1"))
        s["cash"]="969";self.assertEqual(fut.entry_risk_budget(s),D(0))
        s.update(cash="900.2",day_equity="900",peak="1000")
        self.assertEqual(fut.entry_risk_budget(s),D(".2"))
