"""Synthetic decision transition tests; no market or order access."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch
from tools.local_research import ai_decision_memory as m
from tools.local_research.ai_risk_referee import SCOPE


class DecisionMemoryTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        (self.root/"var/ai").mkdir(parents=True)
        self.path=self.root/"var/ai"/m.NAME
        self.now=datetime(2020,1,1,tzinfo=timezone.utc)
        rights=patch.dict(os.environ,{"CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED":"1"})
        rights.start()
        self.addCleanup(rights.stop)
        disk=patch.object(m.shutil,"disk_usage",return_value=type("Usage",(),{"free":20*1024**3})())
        disk.start()
        self.addCleanup(disk.stop)

    def packet(self,blocked=False):
        checks={k:True for k in m.CHECKS}
        if blocked:
            checks["forecast_quality"]=False
        return {"model_referee":{"review_candidate":"chronos"},"risk_referee":{
            "version":"ai-risk-referee-1","scope":SCOPE,
            "status":"REVIEW_BLOCKED" if blocked else "HUMAN_REVIEW_ONLY",
            "review_candidate":None if blocked else "chronos",
            "checks":checks,"failed_checks":["forecast_quality"] if blocked else [],
            "real_orders":False,"automatic_promotion":False,
            "paper_readiness_verified":False,"execution_risk_verified":False}}

    def test_transitions_and_deduplication(self):
        for i,blocked in enumerate((True,True,False,True)):
            r=m.record(self.root,self.packet(blocked),now=self.now+timedelta(seconds=i))
            self.assertEqual(r["recorded"],i!=1)
        h=m.history(self.root)
        self.assertEqual(h["total_records"],3)
        self.assertEqual(h["records"][0]["failed_checks"],["forecast_quality"])
        self.assertIsNone(h["records"][0]["review_candidate"])
        self.assertEqual(h["records"][0]["proposed_candidate"],"chronos")

    def test_read_only_missing(self):
        self.assertEqual(m.history(self.root)["status"],"NOT_AVAILABLE")
        self.assertFalse(self.path.exists())

    def test_rights_required(self):
        with patch.dict(os.environ,{"CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED":"0"}):
            with self.assertRaises(RuntimeError):
                m.record(self.root,self.packet(),now=self.now)
        self.assertFalse(self.path.exists())

    def test_capacity_preserves_existing_record(self):
        m.record(self.root,self.packet(),now=self.now)
        with patch.object(m,"MAX_ROWS",1):
            self.assertEqual(m.record(self.root,self.packet(True),now=self.now)["status"],
                             "WAIT_DECISION_CAPACITY")
        self.assertEqual(m.history(self.root)["total_records"],1)

    def test_tampered_payload(self):
        m.record(self.root,self.packet(),now=self.now)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute("UPDATE decisions SET payload='{}'")
        self.assertEqual(m.history(self.root)["status"],"DATA_REVIEW_REQUIRED")
        with self.assertRaises(ValueError):
            m.record(self.root,self.packet(True),now=self.now)

    def test_reject_inconsistent_decision(self):
        p=self.packet(True)
        p["risk_referee"]["failed_checks"]=[]
        with self.assertRaises(ValueError):
            m.record(self.root,p,now=self.now)
        self.assertFalse(self.path.exists())
