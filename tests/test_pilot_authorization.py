import os,tempfile,unittest,json
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from cyberbot import observed_pilot as p,pilot_decisions as dec,pilot_outcomes as out
from cyberbot.pilot_authorization import snapshot,evidence
class AuthorizationTests(unittest.TestCase):
    def test_scope_threshold_never_authorizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);now=datetime(2026,1,10,12,tzinfo=timezone.utc)
            env={"CYBERBOT_DB":str(root/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(root/"learn.sqlite3"),"CYBERBOT_WORKER_DB":str(root/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(root/"pilot.sqlite3"),"CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":"","CYBERBOT_OBSERVED_PILOT_ENABLED":"1","CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED":"1","CYBERBOT_PILOT_SHADOW_ENABLED":"1","CYBERBOT_PILOT_KILL_SWITCH":"0"}
            with patch.dict(os.environ,env):
                self.assertEqual(snapshot(clock=lambda:now)["authorization"],"blocked")
                self.assertEqual(list(root.iterdir()),[])
                scope={"policy":dec.VERSION,"market":"BIST","symbol":"THYAO.IS","source":"fixture","venue":"XIST","fx_source":None,"pool":None}
                d={"version":dec.VERSION,"scope":scope,"candidate":"trend","hypothetical_action":"BUY","regime":{"id":"bull"}}
                with p.tx() as db:
                    for i in range(30):
                        start=now-timedelta(days=4-i//10,hours=2)+timedelta(minutes=6*(i%10));end=start+timedelta(seconds=out.WINDOW);key=str(i)
                        prior={**d,"id":key,"as_of":start.isoformat()}
                        x={"version":out.VERSION,"decision_version":dec.VERSION,"scope":scope,"candidate":"trend","direction":"BUY","regime":"bull","decision_id":key,"decision_at":start.isoformat(),"covered_until":end.isoformat(),"status":"measured","net_pct":"1","double_cost_pct":".5"}
                        db.execute("INSERT INTO observed_events(market,at,event,payload) VALUES('BIST',?,'shadow_decision',?)",(start.isoformat(),json.dumps(prior)))
                        db.execute("INSERT INTO observed_events(market,at,event,payload) VALUES('BIST',?,'shadow_outcome',?)",(end.isoformat(),json.dumps(x)))
                    self.assertTrue(evidence(db,"BIST",d,now)["threshold_met"])
                    self.assertFalse(evidence(db,"BIST",{**d,"candidate":"reversion"},now)["threshold_met"])
                with patch("cyberbot.pilot_decisions.evaluate",return_value={**d,"status":"shadow_evaluated"}):
                    result=snapshot(clock=lambda:now)
                self.assertTrue(result["markets"][0]["checks"]["scoped_forward_diagnostics"])
                self.assertFalse(result["markets"][0]["checks"]["same_engine_forward_execution_verified"])
                self.assertFalse(result["automatic_entry_enabled"])
                self.assertEqual(result["markets"][0]["authorization"],"blocked")
    def test_hold_backlog(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);now=datetime(2026,1,10,12,tzinfo=timezone.utc)
            with patch.dict(os.environ,{"CYBERBOT_DB":str(root/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(root/"learn.sqlite3"),"CYBERBOT_WORKER_DB":str(root/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(root/"pilot.sqlite3"),"CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":"","CYBERBOT_OBSERVED_PILOT_ENABLED":"1","CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED":"1","CYBERBOT_PILOT_SHADOW_ENABLED":"1"}):
                with p.tx() as db:
                    for i in range(310):
                        at=(now-timedelta(minutes=400-i)).isoformat()
                        db.execute("INSERT INTO observed_events(market,at,event,payload) VALUES('BIST',?,'shadow_decision',?)",(at,json.dumps({"hypothetical_action":"HOLD"})))
                    at=(now-timedelta(minutes=7)).isoformat()
                    d={"id":"new","as_of":at,"symbol":"THYAO.IS","source":"fixture","hypothetical_action":"BUY"}
                    db.execute("INSERT INTO observed_events(market,at,event,payload) VALUES('BIST',?,'shadow_decision',?)",(at,json.dumps(d)))
                x=out.record("BIST",clock=lambda:now)
                self.assertEqual(x["decision_id"],"new");self.assertEqual(x["status"],"unmeasurable")
