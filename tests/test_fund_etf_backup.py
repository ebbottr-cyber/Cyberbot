"""Offline backup/restore regression tests; includes WAL and corrupted files."""
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from tools.fund_etf_backup import backup,daily_backup,restore,verify,sources,FILES


class BackupTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root=Path(folder.name)
        self.db=self.root/"prices.sqlite3"
        self.dest=self.root/"backups"
        with closing(sqlite3.connect(self.db)) as db,db:
            db.execute("CREATE TABLE fund_prices (symbol TEXT,close TEXT)")
            db.execute("INSERT INTO fund_prices VALUES ('AAA','100')")

    def add_development(self):
        with closing(sqlite3.connect(sources(self.db)["development"])) as db,db:
            db.execute("CREATE TABLE fund_development (id TEXT)")
            db.execute("INSERT INTO fund_development VALUES ('evidence')")

    def test_all_roles_and_wal(self):
        self.add_development()
        with closing(sqlite3.connect(sources(self.db)["paper"])) as db,db:
            for table in ("fund_auto_accounts","fund_auto_orders","fund_auto_prices","fund_auto_journal"):
                db.execute("CREATE TABLE "+table+" (id TEXT)")
            db.execute("INSERT INTO fund_auto_orders VALUES ('paper-order')")
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("INSERT INTO fund_prices VALUES ('BBB','200')")
            db.commit()
            result=backup(self.db,self.dest)
        self.assertEqual(set(result["roles"]),set(FILES))
        recovered=self.root/"recovered"
        self.assertEqual(restore(result["bundle"],recovered)["status"],"recovered")
        with closing(sqlite3.connect(recovered/FILES["prices"])) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM fund_prices").fetchone()[0],2)
        with closing(sqlite3.connect(recovered/FILES["paper"])) as db:
            self.assertEqual(db.execute("SELECT id FROM fund_auto_orders").fetchone()[0],"paper-order")
        self.assertFalse(verify(recovered)["real_orders"])

    def test_no_overwrite_and_missing_optional(self):
        result=backup(self.db,self.dest)
        self.assertEqual(result["missing_optional"],["development","paper"])
        with self.assertRaises(FileExistsError):
            restore(result["bundle"],self.root)
        self.assertTrue(self.db.is_file())

    def test_corruption_blocked(self):
        result=backup(self.db,self.dest)
        p=Path(result["bundle"])/FILES["prices"]
        with p.open("ab") as f:
            f.write(b"bad")
        with self.assertRaises(ValueError):
            verify(result["bundle"])
        with self.assertRaises(ValueError):
            restore(result["bundle"],self.root/"recovered")
        self.assertFalse((self.root/"recovered").exists())

    def test_daily_reuse_and_new_optional_role(self):
        first=daily_backup(self.db,self.dest)
        second=daily_backup(self.db,self.dest)
        self.assertEqual(first["bundle"],second["bundle"])
        self.add_development()
        third=daily_backup(self.db,self.dest)
        self.assertNotEqual(first["bundle"],third["bundle"])
        self.assertIn("development",third["roles"])


if __name__=="__main__":
    unittest.main()
