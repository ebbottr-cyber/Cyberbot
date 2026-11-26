import os,tempfile,unittest,sqlite3
from pathlib import Path
from datetime import datetime,timezone,timedelta
from contextlib import closing
from unittest.mock import patch
from cyberbot import observed_pilot as p
from cyberbot.pilot_decisions import record,snapshot,PilotError
class ShadowDecisionTests(unittest.TestCase):
    def test_causal_and_no_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);t=datetime(2026,1,1,12,0,55,tzinfo=timezone.utc)
            env={"CYBERBOT_DB":str(root/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(root/"learn.sqlite3"),"CYBERBOT_WORKER_DB":str(root/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(root/"pilot.sqlite3"),"CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":"","CYBERBOT_OBSERVED_PILOT_ENABLED":"1","CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED":"1","CYBERBOT_PILOT_SHADOW_ENABLED":"1"}
            def quote(i):
                v=str(100+i)
                return {"market":"BIST","symbol":"THYAO.IS","currency":"TRY","source":"fixture","source_at":t.isoformat(),"session_open":True,"bid":v,"ask":v,"venue":"XIST","session_reference":"fixture","bid_size":"10","ask_size":"10"}
            with patch.dict(os.environ,env):
                self.assertEqual(len(snapshot(clock=lambda:t)["markets"]),5);self.assertEqual(list(root.iterdir()),[])
                for i in range(22):
                    if i:t+=timedelta(minutes=1)
                    p.observe("BIST",quote(i),clock=lambda:t)
                    if i==0:self.assertEqual(record("BIST",clock=lambda:t)["status"],"insufficient_contiguous_minutes")
                before=p.snapshot(clock=lambda:t);d=record("BIST",clock=lambda:t)
                self.assertEqual(d["observations"],21);self.assertEqual(d["regime"]["id"],"bull")
                self.assertEqual(d["hypothetical_action"],"BUY");self.assertEqual(d["actual_action"],"HOLD")
                self.assertFalse(d["paper_order_created"]);self.assertEqual(p.snapshot(clock=lambda:t),before)
                self.assertTrue(record("BIST",clock=lambda:t)["duplicate"])
                self.assertEqual(snapshot(clock=lambda:t)["markets"][0]["latest"]["id"],d["id"])
                with closing(sqlite3.connect(root/"pilot.sqlite3")) as db:self.assertEqual(db.execute("SELECT count(*) FROM observed_events WHERE event='request'").fetchone()[0],0)
                t+=timedelta(minutes=2)
                self.assertEqual(record("BIST",clock=lambda:t)["status"],"stale_or_funding_missing")
                with patch.dict(os.environ,{"CYBERBOT_PILOT_SHADOW_ENABLED":"0"}):
                    with self.assertRaises(PilotError):record("BIST",clock=lambda:t)
                self.assertEqual(list(root.iterdir()),[root/"pilot.sqlite3"])
