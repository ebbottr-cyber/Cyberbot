import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from tools.dexterm_publish_replay import publish
from tools.dexterm_paper_positions import simulate
from cyberbot.dexterm_replay_status import read

class ReplayPublicationTests(unittest.TestCase):
    def test_publication_rejects_truncation_and_unrelated_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/"archive.sqlite3";source.touch()
            target=root/"report.json"
            env={"CYBERBOT_DEXTERM_ARCHIVE":str(source),"CYBERBOT_DEXTERM_REPLAY_REPORT":str(target),
                 "CYBERBOT_PILOT_KILL_SWITCH":"1","CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1",
                 "CYBERBOT_DB":str(root/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(root/"learning.sqlite3"),
                 "CYBERBOT_WORKER_DB":str(root/"worker.sqlite3")}
            replay=Mock(return_value=dict(simulate([],risk_mode=True),bridge_history_truncated=False,exit_history_truncated=False))
            with patch.dict(os.environ,env,clear=True):
                self.assertEqual(publish(replay_fn=replay)["status"],"disabled")
                replay.assert_not_called()
                self.assertEqual(publish(enabled=True,replay_fn=replay)["status"],"replay_published")
                self.assertEqual(read(target)["status"],"no_position_observations")
                before=target.read_bytes()
                replay.return_value["exit_history_truncated"]=True
                with self.assertRaises(ValueError):publish(enabled=True,replay_fn=replay)
                self.assertEqual(target.read_bytes(),before)
                target.write_text("unrelated",encoding="utf-8")
                with self.assertRaises(ValueError):publish(enabled=True,replay_fn=replay)
                self.assertEqual(target.read_text(encoding="utf-8"),"unrelated")

    def test_source_target_collision(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"same.json";path.touch()
            with patch.dict(os.environ,{"CYBERBOT_DEXTERM_ARCHIVE":str(path),"CYBERBOT_DEXTERM_REPLAY_REPORT":str(path),
                "CYBERBOT_PILOT_KILL_SWITCH":"1","CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1"},clear=True):
                replay=Mock()
                with self.assertRaises(ValueError):publish(enabled=True,replay_fn=replay)
                replay.assert_not_called()
