import os,json,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from cyberbot import observed_pilot as p
from cyberbot.pilot_control import change,snapshot
from cyberbot.pilot_outcomes import record,snapshot as outcomes
class PilotControlOutcomeTests(unittest.TestCase):
    def test_halt_and_forward(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);t=datetime(2026,1,2,12,tzinfo=timezone.utc)
            env={"CYBERBOT_DB":str(root/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(root/"learn.sqlite3"),"CYBERBOT_WORKER_DB":str(root/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(root/"pilot.sqlite3"),"CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":"","CYBERBOT_OBSERVED_PILOT_ENABLED":"1","CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED":"1","CYBERBOT_PILOT_SHADOW_ENABLED":"1","CYBERBOT_PILOT_KILL_SWITCH":"0"}
            def q(price="100"):return {"market":"BIST","symbol":"THYAO.IS","currency":"TRY","source":"fixture","source_at":t.isoformat(),"session_open":True,"bid":price,"ask":price,"venue":"XIST","session_reference":"fixture","bid_size":"10","ask_size":"10"}
            def tick(price="100"):return p.observe("BIST",q(price),clock=lambda:t)
            with patch.dict(os.environ,env):
                self.assertFalse(snapshot()["halted"]);self.assertEqual(list(root.iterdir()),[])
                tick();p.request("BIST","buy",clock=lambda:t)
                self.assertEqual(change(True,clock=lambda:t)["cancelled_markets"],["BIST"])
                self.assertTrue(snapshot()["halted"])
                t+=timedelta(seconds=1);tick()
                self.assertFalse(p.snapshot(clock=lambda:t)["accounts"][0]["position_open"])
                with self.assertRaises(p.PilotError):p.request("BIST","buy",clock=lambda:t)
                change(False,clock=lambda:t);p.request("BIST","buy",clock=lambda:t)
                t+=timedelta(seconds=1);tick();change(True,clock=lambda:t)
                p.request("BIST","sell",clock=lambda:t);t+=timedelta(seconds=1);tick()
                self.assertFalse(p.snapshot(clock=lambda:t)["accounts"][0]["position_open"])
                change(False,clock=lambda:t)
                # Fixture decision only, outcome must use subsequent real fixture observations.
                d={"id":"fixture-decision","as_of":t.isoformat(),"symbol":"THYAO.IS","source":"fixture","hypothetical_action":"BUY"}
                with p.tx() as db:db.execute("INSERT INTO observed_events(market,at,event,payload) VALUES('BIST',?,'shadow_decision',?)",(t.isoformat(),json.dumps(d)))
                self.assertEqual(record("BIST",clock=lambda:t)["status"],"no_mature_candidate")
                for i in range(24):
                    t+=timedelta(seconds=15);tick(str(100+i/10))
                x=record("BIST",clock=lambda:t);self.assertEqual(x["status"],"measured")
                self.assertEqual(record("BIST",clock=lambda:t)["status"],"no_mature_candidate")
                a=outcomes()["markets"][0];self.assertEqual(a["measured"],1);self.assertFalse(a["sample_threshold_met"])
                self.assertFalse(outcomes()["automatic_entry_enabled"])
