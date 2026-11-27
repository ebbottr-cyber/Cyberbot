"""Synthetic registry and round-trip tests; no native model or real data."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from contextlib import closing
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from tools.local_research.train_candidate import build
from tools.local_research.model_registry import save, read, path_for


def records(days=12, per_day=6, degrade=False, spacing=22):
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    for day in range(days):
        for i in range(per_day):
            t = start + timedelta(days=day, minutes=i*spacing)
            prediction = -0.5 if degrade and day >= 8 else 0.9
            pred = {"naive": 0.0, "mean": 0.2, "ar1": 0.3, "chronos": prediction}
            actual = 1.0
            p = {"mode": "forward_shadow_research", "context_bars": 21,
                 "prediction_bars": 1, "automatic_promotion": False,
                 "real_orders": False, "last_price": 100, "predictions": pred}
            o = {"target_source_at": (t+timedelta(seconds=50)).isoformat(),
                 "actual_return_pct": actual, "execution_verified": False,
                 "real_orders": False,
                 "absolute_errors_pct": {n: abs(actual-x) for n,x in pred.items()}}
            yield (int(t.timestamp()//60), (t+timedelta(seconds=15)).isoformat(),
                   json.dumps(p), json.dumps(o))


class FakeModel:
    def predict(self, x, num_threads=2):
        return [.8]*len(x)
    def model_to_string(self):
        return "tree\nsynthetic stub"


class CandidateTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        env=patch.dict(os.environ,{"CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED":"1"})
        env.start()
        self.addCleanup(env.stop)

    def build(self, rows=None, loader=lambda s:FakeModel()):
        return build(list(records(days=20)) if rows is None else rows,
                     train_model=lambda x,y:FakeModel(),reload_model=loader,
                     library_version="1.0")

    def test_roundtrip_and_idempotency(self):
        meta,text=self.build()
        key=save(self.root,meta,text)
        self.assertEqual(save(self.root,meta,text),key)
        self.assertEqual(read(self.root,key,"1.0"),(meta,text))
        self.assertFalse(meta["automatic_promotion"])
        with closing(sqlite3.connect(path_for(self.root))) as db, db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM model_candidates").fetchone()[0],1)

    def test_insufficient(self):
        self.assertEqual(self.build(list(records(days=1))),(None,None))

    def test_changed_prediction(self):
        class Bad(FakeModel):
            def predict(self,x,num_threads=2):
                return [.1]*len(x)
        with self.assertRaises(ValueError):
            self.build(loader=lambda s:Bad())

    def test_corrupt_model(self):
        meta,text=self.build()
        key=save(self.root,meta,text)
        with closing(sqlite3.connect(path_for(self.root))) as db, db:
            db.execute("UPDATE model_candidates SET model_text=? WHERE candidate=?",
                       (text+"corrupt",key))
        with self.assertRaises(ValueError):
            read(self.root,key,"1.0")

    def test_library_mismatch(self):
        meta,text=self.build()
        key=save(self.root,meta,text)
        with self.assertRaises(ValueError):
            read(self.root,key,"2.0")

    def test_no_promotion(self):
        meta,text=self.build()
        meta["automatic_promotion"]=True
        with self.assertRaises(ValueError):
            save(self.root,meta,text)

    def test_protected_path(self):
        meta,text=self.build()
        with patch.dict(os.environ,{"CYBERBOT_LEARNING_DB":str(self.root/"var/ai/candidate-models.sqlite3")}):
            with self.assertRaises(ValueError):
                save(self.root,meta,text)

    def test_rights_gate(self):
        meta,text=self.build()
        with patch.dict(os.environ,{"CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED":"0"}):
            with self.assertRaises(RuntimeError):
                save(self.root,meta,text)


if __name__=="__main__":
    unittest.main()
