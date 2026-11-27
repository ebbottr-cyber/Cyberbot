import sqlite3
import tempfile
import unittest
from pathlib import Path
from tools.dexterm_model_history import archive,history,normalize
from tools.dexterm_paper_replay import FALSE_FLAGS

def report():
    return {"status":"experiment_blocked","research_only":True,"training_allowed":False,
            "model_promoted":False,"model_saved":False,"weights_updated":False,
            "independent_holdout_verified":False,"blockers":["earlier_sample_count"],"results":[],
            "dataset_sha256":"a"*64,"lightgbm_status":"not_requested","river_status":"not_requested",
            "consensus":{"status":"blocked_by_experiment_gate","trade_eligible":False},
            "secret":"do-not-store",**FALSE_FLAGS}

class ModelHistoryTests(unittest.TestCase):
    def test_dedup_and_distinct_datasets(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"history.db"
            self.assertEqual(archive(path,report())["status"],"experiment_archived")
            self.assertEqual(archive(path,report())["status"],"duplicate_ignored")
            archive(path,dict(report(),dataset_sha256="b"*64))
            out=history(path)
            self.assertEqual(out["total_experiments"],2)
            self.assertEqual(out["distinct_dataset_digests"],2)
            self.assertFalse(out["independent_datasets_verified"])
            self.assertNotIn("do-not-store",str(out))
    def test_same_dataset_changed_run_not_independent_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"history.db"
            archive(path,report())
            archive(path,dict(report(),blockers=["later_sample_count"]))
            out=history(path,limit=1)
            self.assertEqual(out["total_experiments"],2)
            self.assertEqual(out["distinct_dataset_digests"],1)
            self.assertTrue(out["history_truncated"])
            self.assertFalse(out["performance_improvement_verified"])
    def test_unrelated_database_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"other.db"
            con=sqlite3.connect(path)
            con.execute("CREATE TABLE existing (x INTEGER)")
            con.commit();con.close()
            before=path.read_bytes()
            with self.assertRaises(ValueError):archive(path,report())
            self.assertEqual(before,path.read_bytes())
    def test_flags_and_digest_validation(self):
        with self.assertRaises(ValueError):normalize(dict(report(),real_orders=True))
        with self.assertRaises(ValueError):normalize(dict(report(),dataset_sha256="invalid"))
    def test_tampered_history_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"history.db"
            archive(path,report())
            con=sqlite3.connect(path)
            con.execute("UPDATE experiments SET payload='{}'")
            con.commit();con.close()
            with self.assertRaises(ValueError):history(path)

    def test_adaptive_status_is_preserved_without_trace(self):
        r=report();r["adaptive_weights"]={"status":"blocked_by_experiment_gate","trade_eligible":False,"weight_trace":["private"]}
        d=normalize(r)
        self.assertEqual(d["adaptive"],{"status":"blocked_by_experiment_gate"})
        r["adaptive_weights"]["trade_eligible"]=True
        with self.assertRaises(ValueError):normalize(r)
    def test_adaptive_aggregate_validation(self):
        r=report();r.update(status="experiment_complete",blockers=[],lightgbm_status="experiment_complete")
        m={"samples":50,"true_positive":20,"true_negative":20,"false_positive":5,"false_negative":5,
           "accuracy":.8,"balanced_accuracy":.8,"brier_score":.2,"log_loss":.5}
        r["results"]=[{"model":name,"later_window":m} for name in ("constant_training_prior","logistic_baseline","lightgbm")]
        r["adaptive_weights"]={"status":"adaptive_weights_diagnostic_complete","trade_eligible":False,
                               "weights_updated":False,"model_promoted":False,"sample_count":50,"adaptive_samples":25,
                               "adaptive_brier":.19,"equal_weight_brier":.2,"weight_trace":["private"]}
        d=normalize(r)
        self.assertEqual(d["adaptive"]["adaptive_samples"],25)
        self.assertNotIn("weight_trace",d["adaptive"])
        r["adaptive_weights"]["adaptive_samples"]=51
        with self.assertRaises(ValueError):normalize(r)
