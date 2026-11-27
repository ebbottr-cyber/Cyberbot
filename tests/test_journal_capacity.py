import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools.local_research import journal_capacity as jc


class JournalCapacityTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.folder=self.root/"var/ai"
        self.folder.mkdir(parents=True)
        self.name=jc.MODES["Chronos"]

    def test_sidecars_included(self):
        (self.folder/self.name).write_bytes(b"abc")
        (self.folder/(self.name+"-wal")).write_bytes(b"defg")
        (self.folder/(self.name+"-shm")).write_bytes(b"hi")
        self.assertEqual(jc.inventory(self.root)["journals"][self.name]["bytes"],9)

    def test_individual_limit_preserves_files(self):
        path=self.folder/self.name
        path.write_bytes(b"test")
        with patch.dict(jc.LIMITS,{self.name:4}):
            with self.assertRaises(SystemExit) as error:
                jc.require_capacity(self.root,"Chronos")
            self.assertEqual(error.exception.code,75)
            jc.require_capacity(self.root,"RiverLive")
        self.assertEqual(path.read_bytes(),b"test")

    def test_total_limit(self):
        (self.folder/self.name).write_bytes(b"test")
        with patch.object(jc,"TOTAL_LIMIT",4):
            with self.assertRaises(SystemExit) as error:
                jc.require_capacity(self.root,"LightGBM")
            self.assertEqual(error.exception.code,75)

    def test_directory_not_accepted_as_journal(self):
        (self.folder/self.name).mkdir()
        with self.assertRaises(ValueError):
            jc.inventory(self.root)

    def test_no_directory_creation(self):
        missing=self.root/"missing"
        self.assertEqual(jc.inventory(missing)["status"],"NOT_AVAILABLE")
        self.assertFalse(missing.exists())
