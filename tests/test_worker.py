import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from cyberbot.engine import Ledger
from cyberbot.learning import Journal
from cyberbot.worker import run_cycle,status

class WorkerTests(unittest.TestCase):
    def test_repeat_and_isolation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            p=root/"paper.sqlite3";l=root/"learning.sqlite3";w=root/"worker.sqlite3"
            with patch.dict(os.environ,{"CYBERBOT_DB":str(p),"CYBERBOT_LEARNING_DB":str(l),"CYBERBOT_WORKER_DB":str(w),"CYBERBOT_EBBOT_DB":""}):
                self.assertEqual(status()["status"],"not_started")
                ledger=Ledger(p);before=ledger.snapshot()
                a=run_cycle();b=run_cycle()
                self.assertEqual(a["experiment"],"new")
                self.assertEqual(b["experiment"],"duplicate")
                self.assertEqual(a["experiment_id"],b["experiment_id"])
                self.assertEqual(Journal(l).recent()["counts"],{"synthetic":1})
                self.assertEqual(status()["cycles_recorded"],2)
                self.assertFalse(b["real_orders"])
                self.assertEqual(ledger.snapshot(),before)
    def test_degraded(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/"broken.sqlite3";p.write_bytes(b"bad")
            with patch.dict(os.environ,{"CYBERBOT_DB":str(p),"CYBERBOT_LEARNING_DB":str(root/"learn.sqlite3"),"CYBERBOT_WORKER_DB":str(root/"worker.sqlite3"),"CYBERBOT_EBBOT_DB":""}):
                r=run_cycle()
                self.assertEqual(r["status"],"degraded")
                self.assertEqual(r["experiment"],"not_run")
                self.assertFalse((root/"learn.sqlite3").exists())
    def test_path_collision(self):
        with tempfile.TemporaryDirectory() as d:
            p=str(Path(d)/"paper.sqlite3")
            with patch.dict(os.environ,{"CYBERBOT_DB":p,"CYBERBOT_WORKER_DB":p}):
                with self.assertRaises(ValueError):run_cycle()
