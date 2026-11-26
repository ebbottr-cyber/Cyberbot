import os,json,tempfile,unittest,sqlite3
from pathlib import Path
from datetime import datetime,timezone,timedelta
from contextlib import closing
from unittest.mock import patch
from cyberbot.pilot_loop import run_cycle,snapshot,PilotError
from cyberbot import observed_pilot as p
from cyberbot.worker import status as research_status
class PilotLoopTests(unittest.TestCase):
    def test_restart_duplicate_failure_backoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);t=datetime(2026,1,2,12,0,50,tzinfo=timezone.utc)
            q=root/"quote.json";schedule=root/"schedule.json"
            env={"CYBERBOT_DB":str(root/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(root/"learn.sqlite3"),"CYBERBOT_WORKER_DB":str(root/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(root/"pilot.sqlite3"),"CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":"","CYBERBOT_PILOT_LOOP_ENABLED":"1","CYBERBOT_PILOT_LOOP_MARKETS":"BIST","CYBERBOT_LOOP_QUOTE_BIST":str(q),"CYBERBOT_LOOP_SCHEDULE_BIST":str(schedule),"CYBERBOT_EQUITY_OBSERVED_ENABLED":"1","CYBERBOT_EQUITY_QUOTE_RIGHTS_BIST":"1","CYBERBOT_EQUITY_SESSION_REVIEWED_BIST":"1","CYBERBOT_INGRESS_SOURCE_BIST":"fixture","CYBERBOT_OBSERVED_PILOT_ENABLED":"1","CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED":"1","CYBERBOT_PILOT_SHADOW_ENABLED":"1","CYBERBOT_PILOT_INGRESS_ENABLED":"1"}
            def write():
                q.write_text(json.dumps({"market":"BIST","symbol":"THYAO.IS","mic":"XIST","currency":"TRY","source":"fixture","source_at":t.isoformat(),"bid":"100","ask":"100","bid_size":"10","ask_size":"10","realtime":True,"continuous_trading":True}))
            def cycle():return run_cycle(clock=lambda:t)
            with patch.dict(os.environ,env):
                self.assertEqual(snapshot(clock=lambda:t)["status"],"not_started")
                with patch.dict(os.environ,{"CYBERBOT_PILOT_LOOP_ENABLED":"0"}):
                    with self.assertRaises(PilotError):cycle()
                self.assertEqual(list(root.iterdir()),[])
                schedule.write_text(json.dumps({"market":"BIST","mic":"XIST","reviewed_at":t.isoformat(),"reference":"fixture","continuous_windows":[{"open":(t-timedelta(hours=1)).isoformat(),"close":(t+timedelta(hours=1)).isoformat()}]}))
                write();self.assertEqual(cycle()["status"],"ok")
                self.assertEqual(cycle()["status"],"throttled")
                self.assertEqual(research_status()["status"],"not_started")
                with closing(sqlite3.connect(root/"worker.sqlite3",isolation_level=None)) as db:
                    db.execute("BEGIN IMMEDIATE");self.assertEqual(cycle()["status"],"busy");db.rollback()
                t+=timedelta(seconds=15)
                self.assertEqual(cycle()["markets"][0]["status"],"awaiting_new_quote")
                t+=timedelta(seconds=20)
                self.assertEqual(cycle()["markets"][0]["status"],"failed")
                t+=timedelta(seconds=15);write()
                self.assertEqual(cycle()["markets"][0]["status"],"backoff")
                t+=timedelta(seconds=60);write()
                self.assertEqual(cycle()["status"],"ok")
                self.assertTrue(snapshot(clock=lambda:t)["heartbeat_fresh"])
                self.assertFalse(snapshot(clock=lambda:t)["running_verified"])
                self.assertFalse(p.snapshot(clock=lambda:t)["accounts"][0]["position_open"])
                with closing(sqlite3.connect(root/"pilot.sqlite3")) as db:
                    self.assertEqual(db.execute("SELECT count(*) FROM observed_events WHERE event='request'").fetchone()[0],0)
                    self.assertEqual(db.execute("SELECT count(*) FROM observed_events WHERE event='observation'").fetchone()[0],2)
                self.assertFalse((root/"paper.sqlite3").exists())
    def test_solana_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.dict(os.environ,{"CYBERBOT_DB":str(root/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(root/"learn.sqlite3"),"CYBERBOT_WORKER_DB":str(root/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(root/"pilot.sqlite3"),"CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":"","CYBERBOT_PILOT_LOOP_ENABLED":"1","CYBERBOT_PILOT_LOOP_MARKETS":"SOLANA","CYBERBOT_OBSERVED_PILOT_ENABLED":"1","CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED":"1","CYBERBOT_PILOT_SHADOW_ENABLED":"1","CYBERBOT_PILOT_INGRESS_ENABLED":"1","CYBERBOT_SOLANA_PILOT_ENABLED":"1"}):
                self.assertEqual(run_cycle()["markets"][0]["status"],"provider_blocked")
                self.assertFalse((root/"pilot.sqlite3").exists())
