import os,tempfile,unittest,json
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from cyberbot import futures_health as h,db_paths
AT=datetime(2026,1,1,12,tzinfo=timezone.utc)
SYM="BTCUSDT"
def event(**kw):
    return {**{"version":"futures-supervisor-1","symbol":SYM,"stage":"training_collect","status":"captured","real_orders":False},**kw}
class HealthTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        p=patch.dict(os.environ,{"CYBERBOT_DB":str(self.root/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(self.root/"learn.sqlite3"),
          "CYBERBOT_WORKER_DB":str(self.root/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(self.root/"pilot.sqlite3"),
          "CYBERBOT_FUTURES_DIAGNOSTICS_DB":str(self.root/"diagnostics.sqlite3"),"CYBERBOT_FUTURES_DIAGNOSTICS_ENABLED":"1",
          "CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":""});p.start();self.addCleanup(p.stop)
    def test_read_only_empty_and_disabled(self):
        self.assertEqual(h.journal(SYM,clock=lambda:AT)["retained"],0)
        with patch.dict(os.environ,{"CYBERBOT_FUTURES_DIAGNOSTICS_ENABLED":"0"}):
            with self.assertRaises(ValueError):h.record(event(),clock=lambda:AT)
        self.assertEqual(list(self.root.iterdir()),[])
    def test_redaction_retention_and_symbol_isolation(self):
        with patch.object(h,"KEEP",2):
            for i in range(3):h.record(event(status="rejected",error_type="PilotError",message="secret-key",api_key="secret-key"),clock=lambda:AT+timedelta(seconds=i))
            h.record(event(symbol="ETHUSDT"),clock=lambda:AT)
            d=h.journal(SYM,clock=lambda:AT+timedelta(seconds=3))
            self.assertEqual(d["retained"],2)
            self.assertEqual(d["last_24h_counts"]["training_collect:rejected"],2)
            self.assertNotIn("secret-key",json.dumps(d))
            self.assertEqual(h.journal("ETHUSDT",clock=lambda:AT)["retained"],1)
    def test_restart_history_and_stale(self):
        h.record(event(version="futures-watchdog-1",status="recovery_backoff",seconds=15),clock=lambda:AT)
        d=h.journal(SYM,clock=lambda:AT+timedelta(minutes=3))
        self.assertEqual(d["restart_attempts_24h"],1)
        self.assertEqual(d["activity"],"stale_or_no_events")
        self.assertFalse(d["process_running_verified"])
    def test_collision_rejected(self):
        with patch.dict(os.environ,{"CYBERBOT_FUTURES_DIAGNOSTICS_DB":str(self.root/"pilot.sqlite3")}):
            with self.assertRaises(db_paths.PathCollision):h.record(event(),clock=lambda:AT)
        self.assertEqual(list(self.root.iterdir()),[])
    def test_component_error_and_sink_nonfatal(self):
        with patch.object(h.training,"status",side_effect=ValueError("secret")):
            d=h.health(SYM,clock=lambda:AT)
        self.assertEqual(d["component_errors"]["training"],"ValueError")
        self.assertEqual(d["status"],"degraded")
        with patch.object(h,"record",side_effect=OSError("disk")),patch("builtins.print") as output:
            h.sink(event())
            self.assertEqual(output.call_count,2)
