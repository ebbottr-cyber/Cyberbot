import os
import json
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

    def test_recover_without_overwriting_live(self):
        folder=module.backup(self.root)
        with closing(sqlite3.connect(self.source)) as db, db:
            db.execute("INSERT INTO forecasts VALUES ('FUTURES','BTCUSDT','synthetic',3,'test','{}','pending',NULL)")
        before=module.digest(self.source)
        restored=module.recover(self.root,folder)
        self.assertEqual(restored.parent,self.root/"var/ai-recovered")
        self.assertEqual(module.digest(restored/module.NAME),module.verify(folder)["sha256"])
        report=json.loads((restored/"recovery.json").read_text(encoding="utf-8"))
        self.assertFalse(report["activated"])
        self.assertEqual(report["rows"],1)
        self.assertEqual(module.digest(self.source),before)
        with closing(module.connect_readonly(self.source)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0],2)

    def test_recover_rejects_tampering(self):
        folder=module.backup(self.root)
        with (folder/module.NAME).open("ab") as f:
            f.write(b"changed")
        with self.assertRaises(ValueError):
            module.recover(self.root,folder)
        self.assertFalse((self.root/"var/ai-recovered").exists())


    def test_count_budget_preserves_existing_copy(self):
        folder=module.backup(self.root)
        before=module.digest(folder/module.NAME)
        with patch.object(module,"MAX_BACKUPS",1):
            with self.assertRaises(module.BackupCapacityDeferred):
                module.backup(self.root)
        self.assertEqual(list(folder.parent.iterdir()),[folder])
        self.assertEqual(module.verify(folder)["sha256"],before)

    def test_byte_budget_preserves_existing_copy(self):
        folder=module.backup(self.root)
        before=module.verify(folder)
        used=sum(p.stat().st_size for p in folder.iterdir())
        with patch.object(module,"MAX_BACKUP_TOTAL",used+1):
            with self.assertRaises(module.BackupCapacityDeferred):
                module.backup(self.root)
        self.assertEqual(list(folder.parent.iterdir()),[folder])
        self.assertEqual(module.verify(folder),before)

    def test_identical_snapshot_skipped_and_changed_kept(self):
        folder=module.backup(self.root)
        self.assertIsNone(module.backup(self.root,skip_identical=True))
        self.assertEqual(list(folder.parent.iterdir()),[folder])
        with closing(sqlite3.connect(self.source)) as db, db:
            db.execute("UPDATE forecasts SET status='measured',outcome='{}'")
        next_folder=module.backup(self.root,skip_identical=True)
        self.assertIsNotNone(next_folder)
        self.assertNotEqual(module.verify(folder)["sha256"],module.verify(next_folder)["sha256"])

    def test_existing_lock_is_not_removed(self):
        folder=self.root/"var/ai-backups"
        lock=folder/".backup-lock"
        lock.mkdir(parents=True)
        with self.assertRaises(module.BackupCapacityDeferred):
            module.backup(self.root)
        self.assertTrue(lock.is_dir())

    def test_unexpected_partial_requires_review(self):
        folder=self.root/"var/ai-backups"
        partial=folder/".partial-test"
        partial.mkdir(parents=True)
        with self.assertRaises(ValueError):
            module.backup(self.root)
        self.assertEqual(list(folder.iterdir()),[partial])


if __name__=="__main__":
    unittest.main()
