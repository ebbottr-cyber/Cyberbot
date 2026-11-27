import os,tempfile,unittest,sqlite3,json
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from cyberbot import futures_forward_memory as f,db_paths,futures_lightgbm as b
AT=datetime(2026,1,1,12,tzinfo=timezone.utc)
SYM="BTCUSDT"
def rows():
    return [{"at":(AT-timedelta(minutes=1199-i)).isoformat(),"symbol":SYM,"source":"binance-usdm-public","mid":100,
             "spread_bps":1,"funding_rate":0,"mark_index_basis_pct":0,"open_interest":500,"book_imbalance":0,
             "taker_imbalance":0,"atr_1m_pct":.1,"atr_5m_pct":.2} for i in range(1200)]
def forecast(r):
    return {"feature_at":r[-1]["at"].isoformat(),"feature_mid":100,"lightgbm_return":.01,"river_return":0,"estimator_injected":False}
def outcomes():
    return [{"row":{"at":(AT+i*b.STEP).isoformat(),"mid":100+i*.2},
             "started_at":(AT+i*b.STEP-timedelta(seconds=20)).isoformat(),
             "received_at":(AT+i*b.STEP-timedelta(seconds=5)).isoformat()} for i in range(6)]
class ForwardTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.env={**{k:"1" for k in f.FLAGS},"CYBERBOT_BINANCE_OBSERVED_ENABLED":"1","CYBERBOT_BINANCE_DATA_RIGHTS_CONFIRMED":"1","CYBERBOT_FUTURES_TRAINING_ENABLED":"1",
                  "CYBERBOT_DB":str(self.root/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(self.root/"learn.sqlite3"),"CYBERBOT_WORKER_DB":str(self.root/"worker.sqlite3"),
                  "CYBERBOT_PILOT_DB":str(self.root/"pilot.sqlite3"),"CYBERBOT_FUTURES_TRAINING_DB":str(self.root/"train.sqlite3"),
                  "CYBERBOT_FUTURES_AI_MEMORY_DB":str(self.root/"ai.sqlite3"),"CYBERBOT_FUTURES_FORWARD_DB":str(self.root/"forward.sqlite3"),
                  "CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":""}
        p=patch.dict(os.environ,self.env);p.start();self.addCleanup(p.stop)
        self.now=AT+timedelta(seconds=5)
    def clock(self):return self.now
    def issue(self):
        with patch.object(f.training,"recent",return_value=rows()),patch.object(f.bridge,"forecast",side_effect=forecast):
            return f.tick(SYM,clock=self.clock)
    def test_issue_once_and_score_only_after_target(self):
        self.assertEqual(f.snapshot(SYM)["retained_predictions"],0);self.assertEqual(list(self.root.iterdir()),[])
        d=self.issue();self.assertEqual(d["status"],"recorded")
        self.assertEqual(self.issue()["status"],"waiting_for_target")
        self.now=AT+timedelta(minutes=4)
        with patch.object(f,"exact_window",side_effect=AssertionError("premature outcome")):
            self.assertEqual(self.issue()["status"],"waiting_for_target")
        self.now=AT+timedelta(minutes=5)
        with patch.object(f,"exact_window",return_value=outcomes()):
            self.issue();self.issue()
        s=f.snapshot(SYM)
        self.assertEqual(s["counts"],{"scored":1,"pending":0,"missing":0})
        self.assertAlmostEqual(s["metrics"]["lightgbm"]["mae_pct"],0)
        self.assertAlmostEqual(s["metrics"]["river"]["mae_pct"],1)
        self.assertEqual(s["outcome_coverage_pct"],100)
        self.assertEqual(f.snapshot("ETHUSDT")["retained_predictions"],0)
        self.assertFalse(s["real_orders"])
    def test_missing_not_scored_or_backfilled(self):
        self.issue();self.now=AT+timedelta(minutes=5)
        with patch.object(f,"exact_window",return_value=[]):self.issue()
        self.assertEqual(f.snapshot(SYM)["counts"]["pending"],1)
        self.now+=timedelta(seconds=f.GRACE)
        with patch.object(f,"exact_window",return_value=[]):self.issue()
        self.assertEqual(f.snapshot(SYM)["counts"]["missing"],1)
        with patch.object(f,"exact_window",return_value=outcomes()):self.issue()
        self.assertEqual(f.snapshot(SYM)["counts"]["scored"],0)
    def test_late_or_injected_forecast_rejected(self):
        def slow(r):
            self.now+=timedelta(seconds=40);return forecast(r)
        with patch.object(f.training,"recent",return_value=rows()),patch.object(f.bridge,"forecast",side_effect=slow):
            self.assertEqual(f.tick(SYM,clock=self.clock)["status"],"forecast_expired")
        self.assertEqual(f.snapshot(SYM)["retained_predictions"],0)
        self.now=AT+timedelta(seconds=5)
        with patch.object(f.training,"recent",return_value=rows()),patch.object(f.bridge,"forecast",side_effect=lambda r:{**forecast(r),"estimator_injected":True}):
            with self.assertRaises(ValueError):f.tick(SYM,clock=self.clock)
    def test_collision_and_permission(self):
        with patch.dict(os.environ,{"CYBERBOT_FUTURES_FORWARD_DB":self.env["CYBERBOT_PILOT_DB"]}):
            with self.assertRaises(db_paths.PathCollision):self.issue()
        with patch.dict(os.environ,{"CYBERBOT_FUTURES_FORWARD_MEMORY_ENABLED":"0"}):
            with self.assertRaises(ValueError):self.issue()
        self.assertEqual(list(self.root.iterdir()),[])
