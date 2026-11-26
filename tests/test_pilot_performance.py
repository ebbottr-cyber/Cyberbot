import os,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from cyberbot import observed_pilot as p
from cyberbot.pilot_performance import snapshot
class PilotReportTests(unittest.TestCase):
    def test_empty_then_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);t=datetime(2026,1,1,12,tzinfo=timezone.utc)
            env={"CYBERBOT_DB":str(root/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(root/"learning.sqlite3"),"CYBERBOT_WORKER_DB":str(root/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(root/"pilot.sqlite3"),"CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":"","CYBERBOT_OBSERVED_PILOT_ENABLED":"1","CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED":"1","CYBERBOT_OBSERVED_FX_RIGHTS_CONFIRMED":"0","CYBERBOT_SOLANA_PILOT_ENABLED":"0","CYBERBOT_FUTURES_PILOT_ENABLED":"0"}
            def q(price):return {"market":"BIST","symbol":"THYAO.IS","currency":"TRY","source":"fixture","source_at":t.isoformat(),"session_open":True,"bid":price,"ask":price}
            def report():return snapshot(clock=lambda:t)
            with patch.dict(os.environ,env):
                self.assertEqual(len(report()["markets"]),5);self.assertEqual(list(root.iterdir()),[])
                p.observe("BIST",q("100"),clock=lambda:t);p.request("BIST","buy",clock=lambda:t)
                t+=timedelta(seconds=1);p.observe("BIST",q("100"),clock=lambda:t)
                p.request("BIST","sell",clock=lambda:t)
                t+=timedelta(seconds=1);p.observe("BIST",q("101"),clock=lambda:t)
                before=(root/"pilot.sqlite3").read_bytes();d=report();a=d["markets"][0]
                self.assertEqual(a["statistics"]["closed"],1);self.assertEqual(len(a["recent"]),2)
                self.assertIsNotNone(a["equity"]);self.assertIsNone(d["combined_equity"])
                self.assertEqual((root/"pilot.sqlite3").read_bytes(),before)
                t+=timedelta(seconds=31);self.assertIsNone(report()["markets"][0]["equity"])
                self.assertEqual(report()["markets"][0]["statistics"]["closed"],1)
                with patch.dict(os.environ,{"CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED":"0"}):
                    self.assertIsNone(report()["markets"][0]["statistics"])
