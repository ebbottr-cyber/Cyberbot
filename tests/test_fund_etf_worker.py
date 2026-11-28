"""Offline tests for worker status, failure handling and lock."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools import fund_etf_worker as worker


class WorkerTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root=Path(folder.name)
        self.db=self.root/"fund.sqlite3"
        self.config=self.root/"config.json"
        self.config.write_text("{}",encoding="utf-8")
        self.output=self.root/"snapshot.json"
        self.status=self.root/"status.json"

    def test_missing_archive_blocks(self):
        result=worker.run_once(self.db,self.config,self.output,self.status)
        self.assertEqual(result["status"],"blocked")
        self.assertFalse(json.loads(self.output.read_text())["real_orders"])

    def test_failed_cycle_replaces_old_signals(self):
        self.output.write_text('{"status":"research_only"}',encoding="utf-8")
        with patch.object(worker,"cycle",side_effect=RuntimeError):
            result=worker.run_once(self.db,self.config,self.output,self.status)
        self.assertEqual(result["status"],"failed")
        self.assertEqual(json.loads(self.output.read_text())["status"],"blocked")
        self.assertFalse(json.loads(self.status.read_text())["execution_allowed"])

    def test_lock_rejects_second_owner(self):
        path=self.root/"lock"
        with worker.exclusive(path):
            with self.assertRaises(OSError):
                with worker.exclusive(path):
                    self.fail("duplicate owner")
        with worker.exclusive(path):
            pass

    def test_success_status(self):
        report=dict(schema_version=1,status="research_only",counts={"ranked":5},real_orders=False)
        with patch.object(worker,"cycle",return_value=report):
            result=worker.run_once(self.db,self.config,self.output,self.status)
        self.assertEqual(result["counts"]["ranked"],5)
        self.assertIn("finished_at",result)


if __name__=="__main__":
    unittest.main()
