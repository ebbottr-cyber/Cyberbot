"""Offline persistence and path isolation regression tests."""
import os,unittest,tempfile
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from cyberbot import futures_ai_memory as m,futures_ai_consensus as ai,db_paths

NOW=datetime(2026,11,27,tzinfo=timezone.utc)
START=datetime(2026,1,1,tzinfo=timezone.utc)
def report(start=START,symbol="BTCUSDT",good=False,drift=False):
    n=150;end=start+timedelta(minutes=n-1+5)
    metric=lambda error:{"mae_pct":error,"direction_accuracy_pct":60}
    return {"version":ai.VERSION,"status":"offline_common_window_research","symbol":symbol,
            "data_mode":"local_observations_unverified","horizon_minutes":5,"same_test_window":True,
            "actual_action":"HOLD","real_orders":False,"paper_orders":False,"promotion_enabled":False,
            "profitability_verified":False,"feature_provenance_verified":False,"estimator_injected":False,
            "runtime_verified":True,"training_last_target_at":(start-timedelta(minutes=1)).isoformat(),
            "test_first_feature_at":start.isoformat(),"test_last_target_at":end.isoformat(),
            "all_test":{"examples":n},"nonoverlapping_test":{"examples":30,"metrics":{
                "lightgbm":metric(.1 if good else .4),"river":metric(.1 if good else .4),
                "zero":metric(.2),"trailing_momentum":metric(.3)}},
            "drift_events":[{"prediction_at":start.isoformat(),
                 "detected_at":(start+timedelta(minutes=5)).isoformat()}] if drift else []}
class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.env={"CYBERBOT_DB":str(self.root/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(self.root/"learning.sqlite3"),
                  "CYBERBOT_WORKER_DB":str(self.root/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(self.root/"pilot.sqlite3"),
                  "CYBERBOT_FUTURES_AI_MEMORY_DB":str(self.root/"ai.sqlite3"),"CYBERBOT_FUTURES_AI_MEMORY_ENABLED":"1",
                  "CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":""}
        p=patch.dict(os.environ,self.env);p.start();self.addCleanup(p.stop)
    def save(self,*args,**kwargs):return m.record(report(*args,**kwargs),clock=lambda:NOW)
    def test_persistence_duplicate_and_symbol_isolation(self):
        self.assertEqual(m.snapshot("BTCUSDT")["status"],"empty")
        self.assertEqual(list(self.root.iterdir()),[])
        self.assertTrue(self.save()["recorded"])
        self.assertFalse(self.save()["recorded"])
        self.assertFalse(self.save(START+timedelta(minutes=100))["recorded"])
        self.assertTrue(self.save(symbol="ETHUSDT")["recorded"])
        self.assertEqual(m.snapshot("BTCUSDT")["states"]["river"]["runs"],1)
        self.assertEqual(m.snapshot("ETHUSDT")["states"]["river"]["runs"],1)
        self.assertEqual(list(self.root.iterdir()),[self.root/"ai.sqlite3"])
    def test_quarantine_recovery_weighted_metrics(self):
        self.save()
        d=self.save(START+timedelta(days=1))
        self.assertEqual(d["states"]["lightgbm"]["status"],"quarantined")
        for i in (2,3,4):d=self.save(START+timedelta(days=i),good=True)
        s=d["states"]["lightgbm"]
        self.assertEqual(s["status"],"observing")
        self.assertEqual(s["examples"],150)
        self.assertAlmostEqual(s["mae_pct"],.22)
        self.assertFalse(d["promotion_enabled"])
        self.assertFalse(d["real_orders"])
    def test_drift_only_affects_river(self):
        d=self.save(good=True,drift=True)
        self.assertEqual(d["states"]["river"]["reason"],"drift_alarm")
        self.assertEqual(d["states"]["lightgbm"]["status"],"observing")
    def test_reject_bad_evidence_without_files(self):
        for changes in ({"estimator_injected":True},{"runtime_verified":False},
                        {"real_orders":True},{"test_last_target_at":NOW.isoformat()},
                        {"nonoverlapping_test":{"examples":29}}):
            with self.assertRaises(ValueError):m.record({**report(),**changes},clock=lambda:NOW)
        with patch.dict(os.environ,{"CYBERBOT_FUTURES_AI_MEMORY_ENABLED":"0"}):
            with self.assertRaises(ValueError):self.save()
        self.assertEqual(list(self.root.iterdir()),[])
    def test_collision_both_directions(self):
        with patch.dict(os.environ,{"CYBERBOT_FUTURES_AI_MEMORY_DB":self.env["CYBERBOT_PILOT_DB"]}):
            with self.assertRaises(db_paths.PathCollision):self.save()
            with self.assertRaises(db_paths.PathCollision):db_paths.checked()
        self.assertEqual(list(self.root.iterdir()),[])
    def test_retention_does_not_erase_high_watermark(self):
        with patch.object(m,"KEEP",2):
            for i in range(4):self.save(START+timedelta(days=i),good=True)
        d=m.snapshot("BTCUSDT")
        self.assertEqual(len(d["recent"]),2)
        self.assertEqual(d["states"]["river"]["runs"],4)
        self.assertFalse(self.save()["recorded"])
