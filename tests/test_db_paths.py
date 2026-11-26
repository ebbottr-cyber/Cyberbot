import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from cyberbot.db_paths import checked,PathCollision,layout
from cyberbot.capital import Portfolio
from cyberbot.learning_api import store
from cyberbot.api import ledger
class PathTests(unittest.TestCase):
    def test_archive_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);base=p/"paper.sqlite3";archive=p/"archive.sqlite3";archive.write_bytes(b"protected")
            with patch.dict(os.environ,{"CYBERBOT_DB":str(base),"CYBERBOT_LEARNING_DB":str(p/"learn.sqlite3"),"CYBERBOT_WORKER_DB":str(p/"worker.sqlite3"),"CYBERBOT_EBBOT_DB":str(archive),"CYBERBOT_FX_FILE":""}):
                paths=checked();paths["paper_bist"].parent.mkdir()
                try:os.link(archive,paths["paper_bist"])
                except OSError:self.skipTest("hardlink unavailable")
                for fn in (checked,Portfolio,store,ledger):
                    with self.assertRaises(PathCollision):fn()
                self.assertEqual(archive.read_bytes(),b"protected")
                self.assertFalse(base.exists())
    def test_learning_worker_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);learn=p/"learn.sqlite3"
            with patch.dict(os.environ,{"CYBERBOT_DB":str(p/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(learn),"CYBERBOT_WORKER_DB":str(learn),"CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":""}):
                with self.assertRaises(PathCollision):checked()
                self.assertFalse(learn.exists())
