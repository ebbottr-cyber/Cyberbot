"""Verify local file separation and import safety without provider access."""
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from tools.fund_etf_safety import archive_paths,check_paths,exclusive
from tools.fund_etf_import import ingest


class SafetyTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root=Path(folder.name)
        self.db=self.root/"archive.sqlite3"
        self.cfg=self.root/"config.json"
        self.output=self.root/"snapshot.json"
        self.status=self.root/"status.json"
        self.cfg.write_text("{}",encoding="utf-8")

    def test_derived_database_and_config_collisions(self):
        for path in (self.db,self.cfg,self.db.with_name(self.db.name+".auto-paper.sqlite3"),
                     self.db.with_name(self.db.name+".development.sqlite3")):
            with self.subTest(path=path),self.assertRaises(ValueError):
                check_paths(self.db,self.cfg,path,self.status)

    def test_foreign_database_not_modified(self):
        with closing(sqlite3.connect(self.db)) as db,db:
            db.execute("CREATE TABLE other_market (id TEXT)")
        before=self.db.read_bytes()
        with self.assertRaises(ValueError):
            archive_paths(self.db)
        self.assertEqual(self.db.read_bytes(),before)

    def test_protected_other_market(self):
        with patch.dict("os.environ",{"CYBERBOT_EBBOT_DB":str(self.db)}):
            with self.assertRaises(ValueError):
                archive_paths(self.db)
        self.assertFalse(self.db.exists())

    def test_sqlite_disguised_as_json(self):
        with closing(sqlite3.connect(self.output)) as db,db:
            db.execute("CREATE TABLE test (id TEXT)")
        with self.assertRaises(ValueError):
            check_paths(self.db,self.cfg,self.output,self.status)

    def test_shared_archive_lock_different_output(self):
        a=check_paths(self.db,self.cfg,self.output,self.status)
        b=check_paths(self.db,self.cfg,self.root/"other.json",self.root/"other-status.json")
        self.assertEqual(a[0],b[0])
        self.assertNotEqual(a[1],b[1])
        with exclusive(a[0]):
            with self.assertRaises(OSError):
                with exclusive(b[0]):
                    self.fail("second writer acquired same archive")

    def test_direct_import_rejects_duplicate_and_revision(self):
        csv=self.root/"prices.csv"
        def write(data):
            csv.write_text("symbol,date,close\n"+data,encoding="utf-8")
        write("AAA,2025-01-02,100\nAAA,2025-01-02,101\n")
        with self.assertRaises(ValueError):
            ingest(self.db,csv,"ETF","fixture","USD")
        self.assertFalse(self.db.exists())
        write("AAA,2025-01-02,100\n")
        ingest(self.db,csv,"ETF","fixture","USD")
        ingest(self.db,csv,"ETF","fixture","USD")
        write("AAA,2025-01-02,101\nAAA,2025-01-03,102\n")
        with self.assertRaises(ValueError):
            ingest(self.db,csv,"ETF","fixture","USD")
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT close FROM fund_prices").fetchall(),[("100",)])


if __name__=="__main__":
    unittest.main()
