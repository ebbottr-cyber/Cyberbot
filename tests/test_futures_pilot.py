import os,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from decimal import Decimal as D
from unittest.mock import patch
from cyberbot.futures_pilot import observe,request,snapshot,PilotError

class FuturesPilotTests(unittest.TestCase):
    def test_funding_depth_and_liquidation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);t=datetime(2026,1,1,7,59,55,tzinfo=timezone.utc)
            env={"CYBERBOT_DB":str(p/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(p/"learning.sqlite3"),"CYBERBOT_WORKER_DB":str(p/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(p/"pilot.sqlite3"),"CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":"","CYBERBOT_OBSERVED_PILOT_ENABLED":"1","CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED":"1","CYBERBOT_FUTURES_PILOT_ENABLED":"1","CYBERBOT_FUTURES_PILOT_SYMBOL":"BTCUSDT"}
            def quote(at,price="100",depth="1000",funding=None):
                return {"market":"FUTURES","symbol":"BTCUSDT","currency":"USDT","contract":"linear_perpetual","source":"fixture","source_at":at.isoformat(),"bid":price,"ask":str(D(price)*D("1.001")),"mark":price,"bid_depth_usdt":depth,"ask_depth_usdt":depth,"funding":funding or []}
            def status():return snapshot(clock=lambda:t)
            with patch.dict(os.environ,env):
                self.assertFalse(status()["initialized"]);self.assertEqual(list(p.iterdir()),[])
                observe(quote(t),clock=lambda:t);request("SHORT",clock=lambda:t)
                t+=timedelta(seconds=1);self.assertEqual(observe(quote(t),clock=lambda:t)["status"],"open_fill")
                qty=D(status()["position"]["qty"])
                t+=timedelta(seconds=4);self.assertTrue(status()["funding_due"])
                with self.assertRaises(PilotError):observe(quote(t),clock=lambda:t)
                self.assertIsNone(status()["equity"])
                event={"source":"fixture","symbol":"BTCUSDT","settled_at":t.isoformat(),"rate":".001","mark":"100"}
                observe(quote(t,funding=[event]),clock=lambda:t)
                self.assertEqual(D(status()["position"]["funding"]),qty*D("100")*D(".001"))
                self.assertEqual(status()["funding_events"],1)
                request("CLOSE",clock=lambda:t);t+=timedelta(seconds=1)
                self.assertEqual(observe(quote(t,depth="0"),clock=lambda:t)["status"],"exit_waiting_depth")
                self.assertIsNone(status()["equity"])
                t+=timedelta(seconds=1);self.assertEqual(observe(quote(t),clock=lambda:t)["status"],"close_fill")
                request("LONG",clock=lambda:t);t+=timedelta(seconds=1);observe(quote(t),clock=lambda:t)
                pos=status()["position"];cash=status()["cash"]
                self.assertEqual(D(pos["margin"]),D(pos["qty"])*D(pos["entry"])/2)
                t+=timedelta(seconds=40)
                self.assertEqual(observe(quote(t,price="20"),clock=lambda:t)["status"],"model_liquidation")
                self.assertEqual(status()["cash"],cash);self.assertIsNone(status()["position"])
                self.assertEqual(status()["gap_count"],1);self.assertEqual(status()["liquidations"],1)
                self.assertFalse(status()["exchange_execution_verified"])
                self.assertEqual(list(p.iterdir()),[p/"pilot.sqlite3"])
                with patch.dict(os.environ,{"CYBERBOT_FUTURES_PILOT_ENABLED":"0"}):
                    with self.assertRaises(PilotError):request("LONG",clock=lambda:t)
