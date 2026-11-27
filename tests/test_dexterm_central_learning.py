import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools.dexterm_central_learning import run
from cyberbot.integration_api import dexterm_learning_status
from tools.dexterm_research_archive import archive
import json

class DexTermCentralLearningTests(unittest.TestCase):
    def test_disabled_and_empty_data_do_not_fit(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/"research.sqlite3"; target=root/"history.sqlite3"
            report=root/"scan.json"
            report.write_text(json.dumps({"source":"dexterm_screener_query","status":"diagnostic_partial","candidate_count":0,"candidates":[],"security_verified":False,"live_data_verified":False,"pilot_applied":False,"real_orders":False}),encoding="utf-8")
            archive(source,[report])
            env={"CYBERBOT_DEXTERM_ARCHIVE":str(source),"CYBERBOT_DEXTERM_MODEL_HISTORY":str(target),
                 "CYBERBOT_PILOT_KILL_SWITCH":"1","CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1",
                 "CYBERBOT_DB":str(root/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(root/"learning.sqlite3"),"CYBERBOT_WORKER_DB":str(root/"worker.sqlite3")}
            with patch.dict(os.environ,env,clear=True):
                self.assertEqual(run()["status"],"disabled")
                self.assertFalse(target.exists())
                self.assertEqual(dexterm_learning_status()["status"],"not_initialized")
                result=run(enabled=True,allow_experiment=True)
                self.assertEqual(result["status"],"experiment_blocked")
                self.assertFalse(result["experimental_fit_performed"])
                self.assertEqual(result["example_count"],0)
                self.assertEqual(dexterm_learning_status()["latest_status"],"experiment_blocked")
                self.assertEqual(dexterm_learning_status()["total_experiments"],1)
                self.assertFalse(dexterm_learning_status()["forward_live_performance_verified"])

    def test_history_collision_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"same.sqlite3"
            with patch.dict(os.environ,{"CYBERBOT_DEXTERM_ARCHIVE":str(path),"CYBERBOT_DEXTERM_MODEL_HISTORY":str(path),
                "CYBERBOT_PILOT_KILL_SWITCH":"1","CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1"},clear=True):
                with self.assertRaises(ValueError):run(enabled=True)
                self.assertFalse(path.exists())
