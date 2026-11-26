import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from cyberbot.capital import Portfolio
from cyberbot.learning import Journal
from cyberbot.operations import backup
from cyberbot.recovery import recover
class RecoveryTests(unittest.TestCase):
    def test_verified_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);base=p/"paper.sqlite3";learn=p/"learning.sqlite3"
            with patch.dict(os.environ,{"CYBERBOT_DB":str(base),"CYBERBOT_LEARNING_DB":str(learn),"CYBERBOT_WORKER_DB":str(p/"worker.sqlite3"),"CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":""}):
                portfolio=Portfolio(base);Journal(learn)
                portfolio.futures.open("BTCUSDT","LONG");portfolio.futures.advance()
                original=portfolio.futures.snapshot()
                folder=backup(p/"backups")
                restored=recover(folder,p/"recovered")
                report=json.loads((restored/"recovery.json").read_text())
                self.assertEqual(report["status"],"verified_copy")
                self.assertFalse(report["activated"])
                self.assertEqual(len(report["restored"]),6)
                self.assertEqual(Portfolio(restored/"paper.sqlite3").futures.snapshot()["equity_history"],original["equity_history"])
                self.assertEqual(portfolio.futures.snapshot(),original)
                (folder/"learning.sqlite3").write_bytes(b"corrupt")
                with self.assertRaises(ValueError):recover(folder,p/"recovered")
                self.assertEqual(len(list((p/"recovered").iterdir())),1)
    def test_manifest_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);folder=p/"bad";folder.mkdir()
            (folder/"manifest.json").write_text(json.dumps({"scope":"cyberbot_only","files":[{"name":"../paper.sqlite3","bytes":1,"sha256":"a"*64}]}))
            with self.assertRaises(ValueError):recover(folder,p/"out")
            self.assertFalse((p/"out").exists())
