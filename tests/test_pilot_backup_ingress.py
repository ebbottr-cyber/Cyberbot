import json,os,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from cyberbot import observed_pilot as p
from cyberbot.pilot_ingress import ingest,read_file,PilotError
from cyberbot.operations import health,backup
from cyberbot.recovery import recover

class PilotBackupIngressTests(unittest.TestCase):
    def test_ingress_backup_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);t=datetime(2026,1,1,12,tzinfo=timezone.utc)
            env={"CYBERBOT_DB":str(root/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(root/"learning.sqlite3"),"CYBERBOT_WORKER_DB":str(root/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(root/"pilot.sqlite3"),"CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":"","CYBERBOT_OBSERVED_PILOT_ENABLED":"1","CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED":"1","CYBERBOT_PILOT_BACKUP_RIGHTS_CONFIRMED":"0","CYBERBOT_PILOT_INGRESS_ENABLED":"1","CYBERBOT_INGRESS_SOURCE_BIST":"fixture"}
            q={"market":"BIST","symbol":"THYAO.IS","currency":"TRY","source":"fixture","source_at":t.isoformat(),"session_open":True,"bid":"100","ask":"100"}
            envelope={"schema":"cyberbot-quote-1","market":"BIST","quote":q}
            with patch.dict(os.environ,env):
                with self.assertRaises(PilotError):ingest({**envelope,"quote":{**q,"source":"other"}},clock=lambda:t)
                self.assertFalse((root/"pilot.sqlite3").exists())
                self.assertEqual(ingest(envelope,clock=lambda:t)["status"],"observation")
                with self.assertRaises(PilotError):ingest(envelope,clock=lambda:t)
                p.request("BIST","buy",clock=lambda:t)
                before=p.snapshot(clock=lambda:t)
                self.assertEqual(health()["databases"]["observed_pilot"],"ok")
                with self.assertRaises(ValueError):backup(root/"backups")
                with patch.dict(os.environ,{"CYBERBOT_PILOT_BACKUP_RIGHTS_CONFIRMED":"1"}):
                    folder=backup(root/"backups")
                    self.assertTrue((folder/"observed_pilot.sqlite3").is_file())
                    dest=recover(folder,root/"recovery")
                    report=json.loads((dest/"recovery.json").read_text())
                    self.assertTrue(report["pilot_included"])
                    self.assertFalse(report["activated"])
                    with patch.dict(os.environ,{"CYBERBOT_PILOT_DB":str(dest/"paper-observed-pilot.sqlite3")}):
                        self.assertEqual(p.snapshot(clock=lambda:t),before)
                    self.assertEqual(p.snapshot(clock=lambda:t),before)
                    self.assertFalse((root/"paper.sqlite3").exists())
                with self.assertRaises(ValueError):recover(folder,root/"recovery")
                bad=root/"quote.json";bad.write_text('{"schema":"a","schema":"b"}',encoding="utf-8")
                with self.assertRaises(PilotError):read_file(bad,clock=lambda:t)
                with patch.dict(os.environ,{"CYBERBOT_PILOT_INGRESS_ENABLED":"0"}):
                    with self.assertRaises(PilotError):ingest(envelope,clock=lambda:t)
