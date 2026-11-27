"""Coordinator tests: explicit execution, no model or scheduler side effects."""
from pathlib import Path
from unittest.mock import patch
import os
import unittest
from tools.local_research import ai_orchestrator as orch


def snapshot(status="INITIAL_COMPARISON_REVIEW"):
    return {"real_orders":False,"automatic_promotion":False,
            "learning_cycle":{"scope":orch.SCOPE,"status":status,
                "training_started":False,"automatic_promotion":False,
                "real_orders":False,"next_review":"PAIRED_LIGHTGBM_RIVER_RESEARCH"},
            "journal_capacity":{"status":"BELOW_LIMIT"}}


class OrchestratorTests(unittest.TestCase):
    def test_preview_never_executes(self):
        r=orch.run(Path.cwd(),snapshot_factory=lambda _:snapshot(),
                   paired_run=lambda _:self.fail("unexpected training"))
        self.assertEqual(r["status"],"READY_FOR_PAIRED_RESEARCH")
        self.assertFalse(r["executed"])

    def test_wait_new_evidence(self):
        r=orch.run(Path.cwd(),execute=True,snapshot_factory=lambda _:snapshot("WAIT_NEW_DATA"),
                   paired_run=lambda _:self.fail("unexpected training"))
        self.assertFalse(r["executed"])
        self.assertEqual(r["status"],"WAIT_LEARNING_REVIEW")

    def test_missing_rights(self):
        with patch.dict(os.environ,{"CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED":"0"}):
            r=orch.run(Path.cwd(),execute=True,snapshot_factory=lambda _:snapshot())
        self.assertEqual(r["status"],"WAIT_RIGHTS")

    def test_capacity_defers(self):
        with patch.dict(os.environ,{"CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED":"1"}), patch.object(orch,"check_paths",return_value=False):
            r=orch.run(Path.cwd(),execute=True,snapshot_factory=lambda _:snapshot(),
                       paired_run=lambda _:self.fail("unexpected training"))
        self.assertEqual(r["status"],"WAIT_CAPACITY")

    def test_execution_only_comparison(self):
        with patch.dict(os.environ,{"CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED":"1"}), patch.object(orch,"check_paths",return_value=True):
            r=orch.run(Path.cwd(),execute=True,snapshot_factory=lambda _:snapshot(),
                paired_run=lambda _:{"status":"RESEARCH_MEASURED","real_orders":False,
                                     "automatic_promotion":False,"cached":False})
        self.assertTrue(r["executed"])
        self.assertTrue(r["training_started"])
        self.assertFalse(r["candidate_activated"])
        self.assertFalse(r["real_orders"])

    def test_invalid_state_fails_closed(self):
        p=snapshot()
        p["real_orders"]=True
        self.assertEqual(orch.admission(p)["status"],"DATA_REVIEW_REQUIRED")
