import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from cyberbot.worker import run_cycle
from cyberbot.capital import Portfolio
from cyberbot.research_pipeline import PipelineJournal

class PipelineTests(unittest.TestCase):
    def test_full_worker_dedup(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            env={"CYBERBOT_DB":str(p/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(p/"learning.sqlite3"),"CYBERBOT_WORKER_DB":str(p/"worker.sqlite3"),"CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":""}
            with patch.dict(os.environ,env):
                portfolio=Portfolio()
                before=portfolio.snapshot()
                first=run_cycle(full_research=True)
                self.assertEqual(first["status"],"ok",first)
                self.assertEqual(len(first["research_pipeline"]),4)
                self.assertTrue(all(x["status"]=="new" for x in first["research_pipeline"]))
                j=PipelineJournal(p/"learning.sqlite3")
                for x in first["research_pipeline"]:
                    d=j.get(x["id"])
                    self.assertEqual(d["summary"]["stages"],7)
                    self.assertFalse(d["paper_orders"])
                    self.assertFalse(d["promotion_enabled"])
                with patch("cyberbot.research_pipeline.robustness",side_effect=AssertionError("must not recompute")):
                    second=run_cycle(full_research=True)
                self.assertEqual(second["status"],"ok")
                self.assertTrue(all(x["status"]=="duplicate" for x in second["research_pipeline"]))
                self.assertEqual(portfolio.snapshot(),before)
    def test_learning_archive_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            with patch.dict(os.environ,{"CYBERBOT_DB":str(p/"paper.sqlite3"),"CYBERBOT_WORKER_DB":str(p/"worker.sqlite3"),"CYBERBOT_LEARNING_DB":str(p/"archive.sqlite3"),"CYBERBOT_EBBOT_DB":str(p/"archive.sqlite3")}):
                with self.assertRaises(ValueError):run_cycle(full_research=True)
                self.assertFalse((p/"archive.sqlite3").exists())
