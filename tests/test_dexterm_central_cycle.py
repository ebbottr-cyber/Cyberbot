import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from tools.dexterm_central_cycle import run
from cyberbot.integration_api import dexterm_status

MINT="DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
REPORT={"source":"dexterm_screener_query","status":"diagnostic_complete",
        "source_error_count":0,"candidate_count":1,
        "candidates":[{"mint":MINT,"reported":{"priceUsd":1,"liquidityUsd":100000,"ageSec":1,"fetchedAt":100000}}],
        "security_verified":False,"live_data_verified":False,"pilot_applied":False,"real_orders":False}

class CentralDexTermTests(unittest.TestCase):
    def test_disabled_does_not_probe_or_create(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"dex.sqlite3"
            probe=Mock()
            self.assertEqual(run("unused",path,probe_fn=probe)["status"],"disabled")
            probe.assert_not_called()
            self.assertFalse(path.exists())

    def test_cycle_archive_is_visible_to_panel(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); path=root/"dex.sqlite3"
            env={"CYBERBOT_DEXTERM_ARCHIVE":str(path),"CYBERBOT_PILOT_KILL_SWITCH":"1",
                 "CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1","CYBERBOT_DB":str(root/"paper.sqlite3"),
                 "CYBERBOT_LEARNING_DB":str(root/"learning.sqlite3"),"CYBERBOT_WORKER_DB":str(root/"worker.sqlite3")}
            with patch.dict(os.environ,env,clear=True):
                result=run("unused",path,enabled=True,probe_fn=Mock(return_value=REPORT))
                self.assertEqual(result["new_reports"],2)
                self.assertFalse(result["real_orders"])
                self.assertEqual(dexterm_status()["reports"],2)
                self.assertFalse(dexterm_status()["live_data_verified"])
                self.assertFalse((root/"paper.sqlite3").exists())

    def test_collision_or_missing_permission_blocks_probe(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"paper.sqlite3"; probe=Mock()
            with patch.dict(os.environ,{"CYBERBOT_DEXTERM_ARCHIVE":str(path),"CYBERBOT_DB":str(path)},clear=True):
                with self.assertRaises(ValueError):run("unused",path,enabled=True,probe_fn=probe)
            with patch.dict(os.environ,{"CYBERBOT_DEXTERM_ARCHIVE":str(path),"CYBERBOT_DB":str(path),"CYBERBOT_PILOT_KILL_SWITCH":"1","CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1"},clear=True):
                with self.assertRaises(ValueError):run("unused",path,enabled=True,probe_fn=probe)
            probe.assert_not_called()
            self.assertFalse(path.exists())
