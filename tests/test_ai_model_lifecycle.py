"""Synthetic lifecycle state and local persistence tests."""
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
from tools.local_research import ai_model_lifecycle as life

CID="a"*64

def trial():
    return {"version":"champion-challenger-1","scope":life.SCOPE,
            "status":"REVIEW_ONLY","candidate":CID,"reference":"chronos",
            "challenger":"lightgbm","production_champion":False,
            "automatic_promotion":False,"real_orders":False,
            "paper_readiness_verified":False,"profitability_verified":False,
            "counts":{"retained":60},"utc_days":10,
            "daily_weighted_mae_pct":{"chronos":.1,"lightgbm":.08,"naive":.2}}


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        (self.root/"var/ai").mkdir(parents=True)
        self.candidates={CID:{"model":"lightgbm","train_samples":100}}
        for p in (patch.object(life,"registry",return_value=self.candidates),
                  patch.object(life,"trial_status",return_value=trial()),
                  patch.dict(os.environ,{"CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED":"1"}),
                  patch.object(life.shutil,"disk_usage",return_value=type("Usage",(),{"free":20*1024**3})())):
            p.start()
            self.addCleanup(p.stop)

    def state(self,report=None):
        return life.status(self.root,trial=report)["candidates"][0]["state"]

    def test_approval_withdrawal_and_no_activation(self):
        self.assertEqual(self.state(),"AWAITING_HUMAN_REVIEW")
        r=life.record(self.root,CID,"APPROVE_RESEARCH",confirmed=True)
        self.assertFalse(r["production_activation"])
        self.assertEqual(self.state(),"RESEARCH_APPROVED")
        self.assertEqual(life.record(self.root,CID,"APPROVE_RESEARCH",confirmed=True)["status"],"UNCHANGED")
        life.record(self.root,CID,"WITHDRAW_RESEARCH",confirmed=True)
        self.assertEqual(self.state(),"RESEARCH_APPROVAL_WITHDRAWN")
        self.assertEqual(life.status(self.root)["event_count"],2)

    def test_changed_evidence_requires_review(self):
        life.record(self.root,CID,"APPROVE_RESEARCH",confirmed=True)
        p=trial()
        p["counts"]["retained"]=61
        self.assertEqual(self.state(p),"REVIEW_REFRESH_REQUIRED")

    def test_explicit_confirmation_required(self):
        with self.assertRaises(RuntimeError):
            life.record(self.root,CID,"APPROVE_RESEARCH")
        self.assertFalse((self.root/"var/ai"/life.NAME).exists())

    def test_insufficient_trial_blocks_approval(self):
        p=trial()
        p["counts"]["retained"]=59
        with patch.object(life,"trial_status",return_value=p):
            with self.assertRaises(ValueError):
                life.record(self.root,CID,"APPROVE_RESEARCH",confirmed=True)

    def test_read_only_status(self):
        self.assertEqual(self.state(),"AWAITING_HUMAN_REVIEW")
        self.assertFalse((self.root/"var/ai"/life.NAME).exists())

    def test_wrong_candidate_and_safety_flags(self):
        self.assertIsNone(life.evidence(trial(),"b"*64))
        p=trial()
        p["real_orders"]=True
        self.assertIsNone(life.evidence(p,CID))

    def test_withdraw_without_approval_rejected(self):
        with self.assertRaises(ValueError):
            life.record(self.root,CID,"WITHDRAW_RESEARCH",confirmed=True)
