"""Offline integration of actual AI dashboard readers over one synthetic local store."""
from contextlib import closing
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tools.local_research.ai_dashboard import snapshot,TASKS
from tools.local_research.ai_regime_review import context
from tools.local_research.ai_orchestrator import run


class ResearchIntegrationTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.folder=self.root/"var/ai"
        self.path=self.folder/"forward-models-v2.sqlite3"

    def file_state(self):
        return {str(p.relative_to(self.root)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.root.rglob("*") if p.is_file()}

    def fixture(self):
        self.folder.mkdir(parents=True)
        now=datetime.now(timezone.utc)
        start=now.replace(hour=0,minute=0,second=15,microsecond=0)-timedelta(days=20)
        pred={"naive":0.,"mean":.02,"ar1":.04,"chronos":.08}
        p={"mode":"forward_shadow_research","context_bars":21,"prediction_bars":1,
           "real_orders":False,"automatic_promotion":False,"last_price":100.,
           "predictions":pred,"p10":99.98,"p50":100.08,"p90":100.18,
           "regime_context":context([100+i*.01 for i in range(21)]),
           "quality_context":{"last_observation_age_seconds":15,
                              "mean_abs_context_return_pct":.01}}
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute("""CREATE TABLE forecasts (market TEXT,symbol TEXT,source TEXT,
                target_minute INTEGER,created_at TEXT,payload TEXT,status TEXT,outcome TEXT)""")
            for day in range(20):
                for i in range(24):
                    t=start+timedelta(days=day,minutes=22*i)
                    o={"target_source_at":(t+timedelta(seconds=35)).isoformat(),
                       "actual_return_pct":.1,"interval_covered":True,
                       "execution_verified":False,"real_orders":False,
                       "absolute_errors_pct":{k:abs(.1-v) for k,v in pred.items()}}
                    db.execute("INSERT INTO forecasts VALUES (?,?,?,?,?,?,?,?)",
                               ("FUTURES","BTCUSDT","binance-usdm-public",
                                int(t.timestamp()//60),t.isoformat(),json.dumps(p),"measured",json.dumps(o)))
            # Another instrument must not contaminate the scoped readers.
            db.execute("INSERT INTO forecasts VALUES (?,?,?,?,?,?,?,?)",
                       ("FUTURES","ETHUSDT","binance-usdm-public",1,start.isoformat(),"{}","measured","{}"))
        health=self.root/"var/ai-health/watchdog-history.json"
        health.parent.mkdir()
        health.write_text(json.dumps([{"version":"ai-watchdog-2",
            "checked_at_utc":now.isoformat(),"status":"SCHEDULER_OK",
            "real_orders":False,"task_configuration_modified":False,
            "tasks":[{"name":"Cyberbot-AI-"+n,"status":"EXIT_OK"} for n in sorted(TASKS|{"ResearchReview"})],
            "resources":{"scope":"host_sample_not_process_usage","cpu_load_pct":20,
                "free_ram_bytes":6*1024**3,"total_ram_bytes":16*1024**3,
                "free_disk_bytes":50*1024**3,"total_disk_bytes":100*1024**3}}]),encoding="utf-8")

    def assert_safe(self,value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key in ("real_orders","automatic_promotion","production_activation","paper_readiness_verified"):
                    self.assertIs(item,False,key)
                self.assert_safe(item)
        elif isinstance(value,list):
            for item in value:
                self.assert_safe(item)

    def test_empty_checkout_does_not_create_state(self):
        report=snapshot(self.root)
        self.assertEqual(report["risk_referee"]["status"],"REVIEW_BLOCKED")
        self.assertNotEqual(report["orchestrator"]["status"],"READY_FOR_PAIRED_RESEARCH")
        self.assertEqual(list(self.root.iterdir()),[])
        self.assert_safe(report)
        json.dumps(report,allow_nan=False)

    def test_real_readers_agree_on_scoped_synthetic_data(self):
        self.fixture()
        before=self.file_state()
        report=snapshot(self.root)
        self.assertEqual(report["research"]["models"]["chronos"]["counts"]["measured"],480)
        self.assertEqual(sum(d["measured_forecasts"] for d in report["forward_performance_history"]["days"]),480)
        self.assertEqual(report["error_memory"]["measured_records"],480)
        self.assertEqual(report["regime_review"]["retained_blocks"],480)
        self.assertEqual(report["model_review_history"]["chronos_degradation"]["status"],"NO_THRESHOLD_BREACH")
        self.assertEqual(report["forecast_quality"]["status"],"STALE_FORECAST")
        self.assertEqual(report["risk_referee"]["status"],"REVIEW_BLOCKED")
        self.assertEqual(report["learning_cycle"]["status"],"INITIAL_COMPARISON_REVIEW")
        self.assertEqual(report["orchestrator"]["status"],"READY_FOR_PAIRED_RESEARCH")
        preview=run(self.root,paired_run=lambda _:self.fail("preview must not train"))
        self.assertFalse(preview["executed"])
        self.assertEqual(self.file_state(),before)
        self.assert_safe(report)
        json.dumps(report,allow_nan=False)

    def test_corrupt_measured_row_blocks_training(self):
        self.fixture()
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute("UPDATE forecasts SET outcome='{}' WHERE symbol='BTCUSDT' AND target_minute=(SELECT MAX(target_minute) FROM forecasts WHERE symbol='BTCUSDT')")
        before=self.file_state()
        report=snapshot(self.root)
        for k in ("forward_performance_history","error_memory","regime_review","learning_cycle","orchestrator"):
            self.assertEqual(report[k]["status"],"DATA_REVIEW_REQUIRED",k)
        self.assertEqual(report["risk_referee"]["status"],"REVIEW_BLOCKED")
        result=run(self.root,execute=True,paired_run=lambda _:self.fail("corrupt data must not train"))
        self.assertFalse(result["executed"])
        self.assertEqual(result["status"],"DATA_REVIEW_REQUIRED")
        self.assertEqual(self.file_state(),before)
        self.assert_safe(report)
