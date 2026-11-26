import os,tempfile,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
from cyberbot.observed_pilot import observe,request,snapshot,PilotError
from cyberbot.db_paths import checked,PathCollision
class PilotTests(unittest.TestCase):
    def test_next_quote_and_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);t=datetime(2026,1,1,tzinfo=timezone.utc)
            env={"CYBERBOT_DB":str(p/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(p/"learning.sqlite3"),"CYBERBOT_WORKER_DB":str(p/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(p/"pilot.sqlite3"),"CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":"","CYBERBOT_OBSERVED_PILOT_ENABLED":"1","CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED":"1"}
            def quote(at,bid="100",ask="100.1"):return {"market":"BIST","symbol":"THYAO.IS","currency":"TRY","source":"fixture","session_open":True,"source_at":at.isoformat(),"bid":bid,"ask":ask}
            with patch.dict(os.environ,env):
                self.assertFalse(snapshot(clock=lambda:t)["accounts"][0]["initialized"])
                self.assertEqual(list(p.iterdir()),[])
                observe("BIST",quote(t),clock=lambda:t)
                request("BIST","buy",clock=lambda:t)
                self.assertEqual(snapshot(clock=lambda:t)["accounts"][0]["fills"],0)
                with self.assertRaises(PilotError):observe("BIST",quote(t),clock=lambda:t)
                t+=timedelta(seconds=1)
                self.assertEqual(observe("BIST",quote(t),clock=lambda:t)["status"],"buy_fill")
                self.assertTrue(snapshot(clock=lambda:t)["accounts"][0]["position_open"])
                request("BIST","sell",clock=lambda:t)
                t+=timedelta(seconds=1)
                self.assertEqual(observe("BIST",quote(t),clock=lambda:t)["status"],"sell_fill")
                self.assertFalse(snapshot(clock=lambda:t)["accounts"][0]["position_open"])
                self.assertIsNone(snapshot(clock=lambda:t+timedelta(seconds=31))["accounts"][0]["equity"])
                self.assertEqual(list(p.iterdir()),[p/"pilot.sqlite3"])
                with patch.dict(os.environ,{"CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED":"0"}):
                    with self.assertRaises(PilotError):request("BIST","buy",clock=lambda:t)
                with patch.dict(os.environ,{"CYBERBOT_PILOT_DB":env["CYBERBOT_DB"]}):
                    with self.assertRaises(PathCollision):checked()
