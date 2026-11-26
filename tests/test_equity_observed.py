import os,tempfile,unittest,json
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from cyberbot.providers.equity_observed import prepare,iex_probe,PilotError
from cyberbot.pilot_ingress import ingest
from cyberbot import observed_pilot as p
class EquityObservedTests(unittest.TestCase):
    def test_venue_calendar_depth(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);t=datetime(2026,1,2,12,tzinfo=timezone.utc)
            env={"CYBERBOT_DB":str(root/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(root/"learn.sqlite3"),"CYBERBOT_WORKER_DB":str(root/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(root/"pilot.sqlite3"),"CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":"","CYBERBOT_EQUITY_OBSERVED_ENABLED":"1","CYBERBOT_EQUITY_QUOTE_RIGHTS_BIST":"1","CYBERBOT_EQUITY_SESSION_REVIEWED_BIST":"1","CYBERBOT_INGRESS_SOURCE_BIST":"fixture","CYBERBOT_OBSERVED_PILOT_ENABLED":"1","CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED":"1","CYBERBOT_PILOT_INGRESS_ENABLED":"1"}
            schedule={"market":"BIST","mic":"XIST","reviewed_at":t.isoformat(),"reference":"fixture-calendar","continuous_windows":[{"open":(t-timedelta(hours=1)).isoformat(),"close":(t+timedelta(hours=1)).isoformat()}]}
            def raw(size="2"):return {"market":"BIST","symbol":"THYAO.IS","mic":"XIST","currency":"TRY","source":"fixture","source_at":t.isoformat(),"bid":"100","ask":"100","bid_size":size,"ask_size":size,"realtime":True,"continuous_trading":True}
            def tick(size="2"):return ingest(prepare("BIST",raw(size),schedule,t),clock=lambda:t)
            with patch.dict(os.environ,env):
                with self.assertRaises(PilotError):prepare("BIST",{**raw(),"mic":"IEXG"},schedule,t)
                with self.assertRaises(PilotError):prepare("BIST",raw(),{**schedule,"continuous_windows":[]},t)
                self.assertEqual(list(root.iterdir()),[])
                tick();p.request("BIST","buy",clock=lambda:t)
                t+=timedelta(seconds=1);tick();p.request("BIST","sell",clock=lambda:t)
                t+=timedelta(seconds=1);self.assertEqual(tick("1")["status"],"exit_waiting_depth")
                self.assertIsNone(p.snapshot(clock=lambda:t)["accounts"][0]["equity"])
                t+=timedelta(seconds=70);self.assertEqual(tick()["status"],"sell_fill")
    def test_iex_only(self):
        t=datetime(2026,1,2,15,tzinfo=timezone.utc)
        with patch.dict(os.environ,{"CYBERBOT_IEX_PROBE_ENABLED":"1","CYBERBOT_IEX_DATA_RIGHTS_CONFIRMED":"1","CYBERBOT_ALPACA_KEY":"fixture","CYBERBOT_ALPACA_SECRET":"fixture"}):
            d=iex_probe(transport=lambda:{"symbol":"AAPL","quote":{"t":t.isoformat(),"bp":100,"ap":101,"bx":"V","ax":"V"}},clock=lambda:t)
            self.assertFalse(d["applied"]);self.assertFalse(d["nasdaq_venue_verified"])
