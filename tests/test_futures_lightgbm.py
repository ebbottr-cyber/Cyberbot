"""Offline LightGBM Futures protocol tests; optional real estimator smoke test."""
import unittest,tempfile,json,importlib.util
from datetime import datetime,timezone,timedelta
from pathlib import Path
from cyberbot import futures_lightgbm as m
START=datetime(2026,1,1,tzinfo=timezone.utc)
NOW=START+timedelta(days=10)
def sample(n=300):
    return [{"at":(START+i*m.STEP).isoformat(),"symbol":"BTCUSDT","source":"binance-usdm-public",
             "mid":100+(i%31)*.07+i*.01,"spread_bps":1,"funding_rate":.0001,
             "mark_index_basis_pct":.01,"open_interest":500+i,"book_imbalance":.2,
             "taker_imbalance":.1,"atr_1m_pct":.2,"atr_5m_pct":.5} for i in range(n)]
class Fake:
    def fit(self,x,y):self.x=x;self.y=y
    def predict(self,x):return [0.0]*len(x)
class LightGBMTests(unittest.TestCase):
    def test_split_and_no_future_features(self):
        raw=sample()
        rows=m.validate(raw,"BTCUSDT",NOW)
        train,test,purged=m.split(m.build(rows))
        self.assertEqual(purged,5)
        self.assertLess(train[-1][0]+m.HORIZON,test[0][0])
        i=40;original=m.features(rows,i)
        raw[i+1]["mid"]*=1.05
        modified=m.validate(raw,"BTCUSDT",NOW)
        self.assertEqual(m.features(modified,i),original)
        self.assertNotEqual(m.build(modified),m.build(rows))
    def test_offline_report_and_baselines(self):
        fake=Fake()
        d=m.evaluate(sample(),symbol="BTCUSDT",as_of=NOW,model_factory=lambda:fake)
        self.assertEqual(len(fake.x),d["training_examples"])
        self.assertEqual(len(fake.x[0]),len(m.FEATURES))
        self.assertEqual(d["metrics"]["lightgbm"],d["metrics"]["zero"])
        self.assertFalse(d["model_mae_below_both_baselines"])
        self.assertLess(d["training_last_target_at"],d["test_first_feature_at"])
        self.assertTrue(d["estimator_injected"])
        for flag in ("runtime_verified","profitability_verified","promotion_enabled",
                     "model_saved","paper_orders","real_orders","feature_provenance_verified"):
            self.assertIs(d[flag],False)
        self.assertEqual(d["actual_action"],"HOLD")
    def test_reject_bad_records(self):
        for change in ({"symbol":"ETHUSDT"},{"source":"unknown"},{"mid":"NaN"},
                       {"book_imbalance":2},{"open_interest":0},{"atr_1m_pct":True},
                       {"at":(START+timedelta(days=20)).isoformat()},{"future_price":100}):
            raw=sample();raw[25].update(change)
            with self.subTest(change=change),self.assertRaises(m.ResearchError):
                m.validate(raw,"BTCUSDT",NOW)
        raw=sample();del raw[50]
        with self.assertRaises(m.ResearchError):m.validate(raw,"BTCUSDT",NOW)
        with self.assertRaises(m.ResearchError):m.validate(sample(239),"BTCUSDT",NOW)
        with self.assertRaises(m.ResearchError):m.validate(sample(),"BTCUSDT",START)
    def test_file_limit_and_target_deadband(self):
        self.assertEqual([m.direction(x) for x in (-.005,-.004,0,.004,.005)],
                         ["DOWN","HOLD","HOLD","HOLD","UP"])
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/"data.json";p.write_text(json.dumps(sample()),encoding="utf-8")
            self.assertEqual(m.read_local(p),sample())
            p.write_bytes(b" "*(m.MAX_BYTES+1))
            with self.assertRaises(m.ResearchError):m.read_local(p)
    @unittest.skipUnless(importlib.util.find_spec("lightgbm") is not None,"optional LightGBM not installed")
    def test_real_lightgbm_smoke(self):
        d=m.evaluate(sample(),symbol="BTCUSDT",as_of=NOW)
        self.assertTrue(d["runtime_verified"])
        self.assertFalse(d["estimator_injected"])
        self.assertFalse(d["promotion_enabled"])
