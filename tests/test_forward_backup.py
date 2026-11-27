import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from collections import namedtuple
from tools.local_research import forward_backup as module


class ForwardBackupTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()
        folder=self.root/"var/ai"
        folder.mkdir(parents=True)
        self.source=folder/module.NAME
        with closing(sqlite3.connect(self.source)) as db, db:
            db.execute("CREATE TABLE forecasts (market TEXT,symbol TEXT,source TEXT,target_minute INTEGER,created_at TEXT,payload TEXT,status TEXT,outcome TEXT)")
            db.execute("INSERT INTO forecasts VALUES ('FUTURES','BTCUSDT','synthetic',1,'test','{}','pending',NULL)")
        rights=patch.dict(os.environ,{"CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED":"1"})
        rights.start()
        self.addCleanup(rights.stop)
        usage=namedtuple("Usage","total used free")
        disk=patch.object(module.shutil,"disk_usage",return_value=usage(20*1024**3,0,20*1024**3))
        disk.start()
        self.addCleanup(disk.stop)

    def test_snapshot_and_tampering(self):
        with closing(sqlite3.connect(self.source)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("INSERT INTO forecasts VALUES ('FUTURES','BTCUSDT','synthetic',2,'test','{}','pending',NULL)")
            db.commit()
            folder=module.backup(self.root)
            self.assertEqual(module.verify(folder)["rows"],2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0],2)
        self.assertFalse(module.verify(folder)["activated"])
        with (folder/module.NAME).open("ab") as f:
            f.write(b"changed")
        with self.assertRaises(ValueError):
            module.verify(folder)

    def test_rights_gate(self):
        with patch.dict(os.environ,{"CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED":"0"}):
            with self.assertRaises(RuntimeError):
                module.backup(self.root)
        self.assertFalse((self.root/"var/ai-backups").exists())

    def test_disk_gate_and_cleanup(self):
        with patch.object(module.shutil,"disk_usage",return_value=type("Usage",(),{"free":0})()):
            with self.assertRaises(RuntimeError):
                module.backup(self.root)
        self.assertEqual(list((self.root/"var/ai-backups").iterdir()),[])

    def test_protected_db_rejected(self):
        with patch.object(module,"checked",return_value={"learning":self.source}):
            with self.assertRaises(ValueError):
                module.backup(self.root)


if __name__=="__main__":
    unittest.main()
