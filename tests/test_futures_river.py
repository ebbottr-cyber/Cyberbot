import unittest,importlib.util
from datetime import datetime,timezone,timedelta
from cyberbot import futures_river as r,futures_lightgbm as b
START=datetime(2026,1,1,tzinfo=timezone.utc)
NOW=START+timedelta(days=10)
def sample():
    return [{"at":(START+i*b.STEP).isoformat(),"symbol":"BTCUSDT","source":"binance-usdm-public",
             "mid":100+i*.01,"spread_bps":1,"funding_rate":.0001,
             "mark_index_basis_pct":.01,"open_interest":500+i,"book_imbalance":.2,
             "taker_imbalance":.1,"atr_1m_pct":.2,"atr_5m_pct":.5} for i in range(300)]
class Model:
    def __init__(self):self.events=[]
    def predict_one(self,x):self.events.append("predict");return 0.0
    def learn_one(self,x,y):self.events.append("learn")
class Detector:
    drift_detected=False
    def update(self,error):self.drift_detected=True

class RiverTests(unittest.TestCase):
    def test_delayed_labels_and_unresolved_tail(self):
        model=Model()
        d=r.evaluate(sample(),symbol="BTCUSDT",as_of=NOW,
                     model_factory=lambda:model,detector_factory=Detector)
        self.assertEqual(model.events[:6],["predict"]*5+["learn"])
        self.assertEqual(d["learned_labels"],275)
        self.assertEqual(d["unresolved_predictions"],5)
        self.assertEqual(d["scored_predictions"],171)
        self.assertEqual(d["first_scored_prediction_at"],(START+124*b.STEP).isoformat())
        self.assertEqual(d["metrics"]["river"],d["metrics"]["zero"])
        self.assertEqual(len(d["drift_events"]),171)
        for item in d["drift_events"]:
            self.assertEqual(datetime.fromisoformat(item["detected_at"])-datetime.fromisoformat(item["prediction_at"]),5*b.STEP)
        for flag in ("runtime_verified","automatic_model_reset","live_learning_enabled","real_orders","paper_orders","promotion_enabled"):
            self.assertIs(d[flag],False)
        self.assertEqual(d["actual_action"],"HOLD")
    def test_reject_bad_data_and_partial_injection(self):
        raw=sample();del raw[50]
        with self.assertRaises(b.ResearchError):r.evaluate(raw,symbol="BTCUSDT",as_of=NOW,model_factory=Model,detector_factory=Detector)
        with self.assertRaises(b.ResearchError):r.evaluate(sample(),symbol="BTCUSDT",as_of=NOW,model_factory=Model)
    @unittest.skipUnless(importlib.util.find_spec("river") is not None,"optional River not installed")
    def test_real_river_smoke(self):
        d=r.evaluate(sample(),symbol="BTCUSDT",as_of=NOW)
        self.assertTrue(d["runtime_verified"])
        self.assertFalse(d["real_orders"])
