import os,sqlite3,json,tempfile,unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from cyberbot import futures_backup as b, futures_pilot as pilot,db_paths
class BackupTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)
        self.env={"CYBERBOT_DB":str(self.root/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(self.root/"learn.sqlite3"),
                  "CYBERBOT_WORKER_DB":str(self.root/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(self.root/"pilot.sqlite3"),
                  "CYBERBOT_FUTURES_BACKUP_RIGHTS_CONFIRMED":"1","CYBERBOT_PILOT_BACKUP_RIGHTS_CONFIRMED":"1",
                  "CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":""}
        p=patch.dict(os.environ,self.env);p.start();self.addCleanup(p.stop)
    def fixture(self):
        p=db_paths.pilot_path()
        with closing(sqlite3.connect(p)) as db:
            db.execute("CREATE TABLE observed_accounts(market TEXT PRIMARY KEY,payload TEXT NOT NULL)")
            db.execute("CREATE TABLE observed_events(id INTEGER PRIMARY KEY,market TEXT NOT NULL,at TEXT NOT NULL,event TEXT NOT NULL,payload TEXT NOT NULL)")
            s=pilot.initial("BTCUSDT");s["pending"]={"side":"LONG","reason":"manual"}
            db.execute("INSERT INTO observed_accounts VALUES('FUTURES',?)",(json.dumps(s),))
            db.execute("INSERT INTO observed_accounts VALUES('BIST','{}')")
            db.execute("INSERT INTO observed_events VALUES(1,'BIST','2026-01-01','observation','{}')")
            db.execute("INSERT INTO observed_events VALUES(2,'FUTURES','2026-01-01','observation','{}')")
            db.commit()
        with closing(sqlite3.connect(db_paths.futures_training_path())) as db:
            b.training.schema(db,True);db.commit()
    def backup(self):
        return Path(b.backup(self.root/"backups",offline_confirmed=True)["directory"])
    def test_backup_and_recovery_isolation(self):
        self.fixture();before=db_paths.pilot_path().read_bytes()
        directory=self.backup();m=b.verify(directory)
        self.assertEqual({e["name"] for e in m["files"]},{"pilot","training"})
        with closing(sqlite3.connect(directory/"pilot.sqlite3")) as db:
            self.assertEqual(db.execute("SELECT market FROM observed_accounts").fetchall(),[("FUTURES",)])
            self.assertEqual(db.execute("SELECT market FROM observed_events").fetchall(),[("FUTURES",)])
        d=b.stage_recovery(directory,self.root/"recoveries");p=Path(d["directory"])
        self.assertFalse(d["active_paths_changed"])
        with closing(sqlite3.connect(p/"pilot.sqlite3")) as db:
            s=json.loads(db.execute("SELECT payload FROM observed_accounts").fetchone()[0]);self.assertIsNone(s["pending"])
            self.assertTrue(json.loads(db.execute("SELECT payload FROM observed_events WHERE market='CONTROL'").fetchone()[0])["halted"])
        self.assertEqual(db_paths.pilot_path().read_bytes(),before);b.verify(directory)
    def test_permission_and_offline_confirmation(self):
        self.fixture()
        with self.assertRaises(ValueError):b.backup(self.root/"backups")
        for flag in ("CYBERBOT_FUTURES_BACKUP_RIGHTS_CONFIRMED","CYBERBOT_PILOT_BACKUP_RIGHTS_CONFIRMED"):
            with patch.dict(os.environ,{flag:"0"}):
                with self.assertRaises(ValueError):self.backup()
        self.assertFalse((self.root/"backups").exists())
    def test_tamper_detection(self):
        self.fixture();directory=self.backup()
        with (directory/"training.sqlite3").open("ab") as f:f.write(b"x")
        with self.assertRaises(ValueError):b.verify(directory)
        with self.assertRaises(ValueError):b.stage_recovery(directory,self.root/"recovery")
        self.assertFalse((self.root/"recovery").exists())
    def test_manifest_traversal_and_extra_file(self):
        self.fixture();directory=self.backup()
        (directory/"extra.txt").write_text("x")
        with self.assertRaises(ValueError):b.verify(directory)
        (directory/"extra.txt").unlink()
        p=directory/"manifest.json";m=json.loads(p.read_text());m["files"][0]["file"]="../outside.sqlite3";p.write_text(json.dumps(m))
        with self.assertRaises(ValueError):b.verify(directory)
    def test_empty_and_collision(self):
        with self.assertRaises(ValueError):self.backup()
        self.assertEqual(list((self.root/"backups").iterdir()),[])
        with patch.dict(os.environ,{"CYBERBOT_FUTURES_TRAINING_DB":self.env["CYBERBOT_PILOT_DB"]}):
            with self.assertRaises(db_paths.PathCollision):self.backup()
