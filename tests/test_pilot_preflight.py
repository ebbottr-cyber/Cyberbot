import os,tempfile,unittest,json
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from cyberbot.pilot_preflight import snapshot
class PreflightTests(unittest.TestCase):
    def test_no_mutation_and_local_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);t=datetime(2026,1,2,12,tzinfo=timezone.utc);q=p/"q.json";s=p/"s.json"
            env={"CYBERBOT_DB":str(p/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(p/"learn.sqlite3"),"CYBERBOT_WORKER_DB":str(p/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(p/"pilot.sqlite3"),"CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":"","CYBERBOT_PILOT_LOOP_ENABLED":"1","CYBERBOT_PILOT_LOOP_MARKETS":"BIST","CYBERBOT_PILOT_SUPERVISOR_ENABLED":"1","CYBERBOT_OBSERVED_PILOT_ENABLED":"1","CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED":"1","CYBERBOT_PILOT_SHADOW_ENABLED":"1","CYBERBOT_PILOT_INGRESS_ENABLED":"1","CYBERBOT_EQUITY_OBSERVED_ENABLED":"1","CYBERBOT_EQUITY_QUOTE_RIGHTS_BIST":"1","CYBERBOT_EQUITY_SESSION_REVIEWED_BIST":"1","CYBERBOT_INGRESS_SOURCE_BIST":"fixture","CYBERBOT_LOOP_QUOTE_BIST":str(q),"CYBERBOT_LOOP_SCHEDULE_BIST":str(s)}
            with patch.dict(os.environ,env,clear=False):
                d=snapshot(clock=lambda:t);self.assertEqual(d["status"],"blocked");self.assertEqual(list(p.iterdir()),[])
                self.assertFalse(d["markets"][0]["local_quote_validated"])
                q.write_text(json.dumps({"market":"BIST","symbol":"THYAO.IS","mic":"XIST","currency":"TRY","source":"fixture","source_at":t.isoformat(),"bid":"100","ask":"100","bid_size":"10","ask_size":"10","realtime":True,"continuous_trading":True}))
                s.write_text(json.dumps({"market":"BIST","mic":"XIST","reviewed_at":t.isoformat(),"reference":"fixture","continuous_windows":[{"open":(t-timedelta(hours=1)).isoformat(),"close":(t+timedelta(hours=1)).isoformat()}]}))
                d=snapshot(clock=lambda:t)
                self.assertTrue(d["markets"][0]["local_quote_validated"])
                self.assertFalse(d["markets"][0]["provider_runtime_verified"])
                self.assertFalse(d["automatic_entry_enabled"]);self.assertFalse(d["network_probed"])
                self.assertEqual(set(p.iterdir()),{q,s})
                self.assertFalse(snapshot(clock=lambda:t+timedelta(seconds=31))["markets"][0]["local_quote_validated"])
                with patch.dict(os.environ,{"CYBERBOT_PILOT_DB":str(p/"paper.sqlite3")}):
                    self.assertEqual(snapshot(clock=lambda:t)["database_isolation"],"review_required")
