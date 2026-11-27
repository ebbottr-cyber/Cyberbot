import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from types import SimpleNamespace
from tools.dexterm_research_archive import archive
from tools.solana_learning_cycle import run
from tools.solana_research_backup import backup,restore,verify,FILES
from tools.solana_paper_replay import FALSE_FLAGS

NOW=datetime(2026,11,27,tzinfo=timezone.utc)

class BackupTests(unittest.TestCase):
    def populate(self,p):
        f=p/"input.json"
        f.write_text(json.dumps({"source":"dexterm_historical_shortlist_exact_mint_lookup",
            "status":"no_eligible_pools","lookups":[],"scan":None,**FALSE_FLAGS}))
        archive(p/"solana-research.sqlite3",[f])
        run(p/"solana-research.sqlite3",p/"solana-model-history.sqlite3")
    def test_backup_and_new_directory_restore(self):
        with tempfile.TemporaryDirectory() as d,patch("tools.solana_research_backup.shutil.disk_usage",return_value=SimpleNamespace(free=10**12)):
            p=Path(d);self.populate(p)
            original={name:(p/name).read_bytes() for name in FILES}
            out=backup(p,now=NOW)
            self.assertEqual(out["status"],"backup_complete")
            self.assertEqual(set(verify(out["backup_directory"])["files"]),set(FILES))
            recovered=restore(out["backup_directory"],p/"restored",confirmed=True)
            self.assertTrue(recovered["stop_marker_created"])
            self.assertFalse(recovered["real_orders"])
            self.assertEqual(original,{name:(p/name).read_bytes() for name in FILES})
            self.assertEqual(backup(p,daily=True,now=NOW+timedelta(hours=1))["status"],"backup_not_due")
            self.assertFalse((p/"solana-research.sqlite3.research.lock").exists())
    def test_changed_backup_rejected_without_restore(self):
        with tempfile.TemporaryDirectory() as d,patch("tools.solana_research_backup.shutil.disk_usage",return_value=SimpleNamespace(free=10**12)):
            p=Path(d);self.populate(p);out=backup(p,now=NOW);folder=Path(out["backup_directory"])
            with (folder/"solana-research.sqlite3").open("ab") as f:f.write(b"tamper")
            with self.assertRaises(ValueError):restore(folder,p/"new",confirmed=True)
            self.assertFalse((p/"new").exists())
    def test_refuses_existing_destination_and_unconfirmed(self):
        with tempfile.TemporaryDirectory() as d,patch("tools.solana_research_backup.shutil.disk_usage",return_value=SimpleNamespace(free=10**12)):
            p=Path(d);self.populate(p);out=backup(p,now=NOW)
            with self.assertRaises(ValueError):restore(out["backup_directory"],p/"new")
            with self.assertRaises(ValueError):restore(out["backup_directory"],p,confirmed=True)
    def test_no_source_and_conflicting_lock(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);self.assertEqual(backup(p)["status"],"no_databases_yet")
            lock=p/"solana-research.sqlite3.research.lock";lock.touch()
            with self.assertRaises(FileExistsError):backup(p)
            self.assertTrue(lock.exists())
    def test_corrupt_payload_fails_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as d,patch("tools.solana_research_backup.shutil.disk_usage",return_value=SimpleNamespace(free=10**12)):
            p=Path(d);self.populate(p)
            with sqlite3.connect(p/"solana-research.sqlite3") as c:c.execute("UPDATE research_reports SET payload='{}'")
            with self.assertRaises(ValueError):backup(p,now=NOW)
            self.assertEqual(list((p/"backups").iterdir()),[])
            self.assertTrue((p/"solana-research.sqlite3").exists())
