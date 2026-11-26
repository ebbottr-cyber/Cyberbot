import os,tempfile,unittest,sqlite3,json
from contextlib import closing
from datetime import datetime,timezone,timedelta
from pathlib import Path
from decimal import Decimal as D
from unittest.mock import patch
from cyberbot.observed_pilot import observe,request,snapshot,PilotError

class XetraPilotTests(unittest.TestCase):
    def test_fx_fill_and_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);t=datetime(2026,1,1,12,tzinfo=timezone.utc)
            env={"CYBERBOT_DB":str(p/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(p/"learning.sqlite3"),"CYBERBOT_WORKER_DB":str(p/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(p/"pilot.sqlite3"),"CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":"","CYBERBOT_OBSERVED_PILOT_ENABLED":"1","CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED":"1","CYBERBOT_OBSERVED_FX_RIGHTS_CONFIRMED":"1"}
            def quote(at,fx_at=None,bid="1.10",ask="1.101"):
                return {"market":"XETRA","symbol":"SAP.DE","currency":"EUR","source":"fixture","session_open":True,"source_at":at.isoformat(),"bid":"100","ask":"100.1","fx":{"pair":"EUR/USD","source":"fixture_fx","source_at":(fx_at or at).isoformat(),"bid":bid,"ask":ask}}
            def state():
                with closing(sqlite3.connect(p/"pilot.sqlite3")) as db:return json.loads(db.execute("SELECT payload FROM observed_accounts WHERE market='XETRA'").fetchone()[0])
            def status():return next(x for x in snapshot(clock=lambda:t)["accounts"] if x["market"]=="XETRA")
            with patch.dict(os.environ,env):
                with patch.dict(os.environ,{"CYBERBOT_OBSERVED_FX_RIGHTS_CONFIRMED":"0"}):
                    with self.assertRaises(PilotError):observe("XETRA",quote(t),clock=lambda:t)
                with self.assertRaises(PilotError):observe("XETRA",quote(t,t-timedelta(seconds=11)),clock=lambda:t)
                observe("XETRA",quote(t),clock=lambda:t);request("XETRA","buy",clock=lambda:t)
                prior=t;t+=timedelta(seconds=1)
                self.assertEqual(observe("XETRA",quote(t,prior),clock=lambda:t)["status"],"observation")
                self.assertEqual(status()["fills"],0)
                t+=timedelta(seconds=1)
                self.assertEqual(observe("XETRA",quote(t),clock=lambda:t)["status"],"buy_fill")
                pos=state()["position"];qty=D(pos["quantity"])
                self.assertEqual(qty,qty.to_integral_value())
                self.assertEqual(D(pos["cost"]),qty*D(pos["entry"])*D("1.101")*D("1.001"))
                self.assertEqual(status()["currency"],"USD");self.assertEqual(status()["price_currency"],"EUR")
                request("XETRA","sell",clock=lambda:t);t+=timedelta(seconds=1)
                self.assertEqual(observe("XETRA",quote(t,bid="1.12",ask="1.121"),clock=lambda:t)["status"],"sell_fill")
                expected=D(1000)-D(pos["cost"])+qty*D("100")*D(".998")*D(".999")*D("1.12")
                self.assertEqual(D(status()["cash"]),expected)
                self.assertFalse(status()["position_open"])
                with patch.dict(os.environ,{"CYBERBOT_OBSERVED_FX_RIGHTS_CONFIRMED":"0"}):
                    self.assertIsNone(status()["equity"])
                    with self.assertRaises(PilotError):request("XETRA","buy",clock=lambda:t)
                self.assertFalse((p/"paper.sqlite3").exists())
