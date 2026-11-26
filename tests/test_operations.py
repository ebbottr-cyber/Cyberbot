import os
import tempfile
import unittest
import json
import hashlib
from pathlib import Path
from unittest.mock import patch
from cyberbot.engine import Ledger
from cyberbot.learning import Journal
from cyberbot.operations import health,backup

class OpsTests(unittest.TestCase):
    def test_health_and_backup(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            p=root/"paper.sqlite3"; l=root/"learning.sqlite3"
            with patch.dict(os.environ,{"CYBERBOT_DB":str(p),"CYBERBOT_LEARNING_DB":str(l),"CYBERBOT_EBBOT_DB":""}):
                self.assertEqual(health()["databases"]["paper"],"not_initialized")
                ledger=Ledger(p);Journal(l);ledger.buy("DEMO-BIST")
                self.assertEqual(health()["databases"],{"paper":"ok","learning":"ok"})
                before=ledger.snapshot()
                folder=backup(root/"backups")
                m=json.loads((folder/"manifest.json").read_text())
                self.assertEqual(len(m["files"]),2)
                for entry in m["files"]:
                    self.assertEqual(hashlib.sha256((folder/entry["name"]).read_bytes()).hexdigest(),entry["sha256"])
                self.assertEqual(Ledger(folder/"paper.sqlite3").snapshot()["equity"],before["equity"])
                self.assertEqual(ledger.snapshot(),before)
                with patch.dict(os.environ,{"CYBERBOT_EBBOT_DB":str(p)}):
                    with self.assertRaises(ValueError):backup(root/"backups")
    def test_invalid_database(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/"broken.sqlite3";p.write_bytes(b"not sqlite")
            with patch.dict(os.environ,{"CYBERBOT_DB":str(p),"CYBERBOT_LEARNING_DB":str(root/"missing.sqlite3"),"CYBERBOT_EBBOT_DB":""}):
                self.assertEqual(health()["status"],"degraded")
                with self.assertRaises(ValueError):backup(root/"backups")
                self.assertEqual(list((root/"backups").iterdir()),[])
