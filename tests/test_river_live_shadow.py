"""Synthetic in-memory forward journal tests, no River dependency."""
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import unittest

from tools.local_research.river_live_shadow import tick, status, SCOPE


class Model:
    def __init__(self):
        self.labels=[]
    def learn_one(self,x,y):
        self.labels.append(y)
    def predict_one(self,x):
        return self.labels[-1] if self.labels else 0.


class ShadowTests(unittest.TestCase):
    def setUp(self):
        self.source=sqlite3.connect(":memory:")
        self.db=sqlite3.connect(":memory:")
        self.addCleanup(self.source.close)
        self.addCleanup(self.db.close)
        self.t=datetime(2020,1,1,0,0,20,tzinfo=timezone.utc)
        self.models=[]
        self.source.execute("""CREATE TABLE forecasts (
            market TEXT,symbol TEXT,source TEXT,target_minute INTEGER,
            created_at TEXT,payload TEXT,status TEXT,outcome TEXT)""")

    def factory(self):
        m=Model()
        self.models.append(m)
        return m

    def target(self):
        return int(self.t.timestamp()//60)

    def add(self):
        p={"mode":"forward_shadow_research","context_bars":21,
           "prediction_bars":1,"real_orders":False,"automatic_promotion":False,
           "last_price":100,"predictions":{"naive":0,"mean":.2,"ar1":.3,"chronos":.4}}
        self.source.execute("INSERT INTO forecasts VALUES (?,?,?,?,?,?,?,?)",
            (*SCOPE,self.target(),(self.t-timedelta(seconds=5)).isoformat(),
             json.dumps(p),"pending",None))
        self.source.commit()

    def settle(self,target):
        row=self.source.execute("SELECT payload FROM forecasts WHERE target_minute=?",(target,)).fetchone()
        predictions=json.loads(row[0])["predictions"]
        o={"actual_return_pct":1.0,
           "absolute_errors_pct":{n:abs(1-v) for n,v in predictions.items()},
           "target_source_at":datetime.fromtimestamp(target*60+50,timezone.utc).isoformat(),
           "execution_verified":False,"real_orders":False}
        self.source.execute("UPDATE forecasts SET status='measured',outcome=? WHERE target_minute=?",
                            (json.dumps(o),target))
        self.source.commit()

    def tick(self,version="1.0"):
        return tick(self.source,self.db,library_version=version,
                    factory=self.factory,clock=lambda:self.t)

    def test_predict_then_learn_and_restart(self):
        self.add()
        first=self.target()
        self.assertEqual(self.tick(),"FORECAST_RECORDED")
        self.assertEqual(self.models[-1].labels,[])
        self.assertEqual(self.tick(),"ALREADY_RECORDED")
        self.settle(first)
        self.t+=timedelta(minutes=1)
        self.add()
        self.assertEqual(self.tick(),"FORECAST_RECORDED")
        self.assertEqual(self.models[-1].labels,[1.0])
        row=self.db.execute("SELECT prediction,training_count FROM river_shadow WHERE target=?",
                            (self.target(),)).fetchone()
        self.assertEqual(row,(1.0,1))
        self.assertEqual(status(self.db)["counts"],{"measured":1,"pending":1})
        self.assertEqual(status(self.db)["scored_after_warmup"],0)

    def test_late_window(self):
        self.add()
        self.t+=timedelta(seconds=20)
        self.assertEqual(self.tick(),"WAIT_WINDOW")
        self.assertEqual(status(self.db)["counts"],{})

    def test_no_retroactive_prediction(self):
        self.add()
        self.settle(self.target())
        self.assertEqual(self.tick(),"WAIT_SOURCE")

    def test_pending_blocks_next(self):
        self.add()
        self.assertEqual(self.tick(),"FORECAST_RECORDED")
        self.t+=timedelta(minutes=1)
        self.add()
        self.assertEqual(self.tick(),"WAIT_PRIOR_OUTCOME")

    def test_library_change_blocks(self):
        self.add()
        first=self.target()
        self.assertEqual(self.tick(),"FORECAST_RECORDED")
        self.settle(first)
        self.t+=timedelta(minutes=1)
        self.add()
        self.assertEqual(self.tick("2.0"),"LIBRARY_REVIEW_REQUIRED")

    def test_changed_source_not_learned(self):
        self.add()
        first=self.target()
        self.assertEqual(self.tick(),"FORECAST_RECORDED")
        self.source.execute("UPDATE forecasts SET payload=payload||' '")
        self.settle(first)
        self.t+=timedelta(minutes=1)
        self.add()
        self.assertEqual(self.tick(),"FORECAST_RECORDED")
        self.assertEqual(self.models[-1].labels,[])
        self.assertEqual(status(self.db)["counts"],{"unmeasurable":1,"pending":1})


if __name__=="__main__":
    unittest.main()
