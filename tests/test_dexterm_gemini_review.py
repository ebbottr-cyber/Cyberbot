import unittest
from tools.dexterm_gemini_review import prepare,validate
from tools.dexterm_paper_replay import FALSE_FLAGS

def report():
    return {"status":"experiment_blocked","research_only":True,"training_allowed":False,
            "model_promoted":False,"model_saved":False,"weights_updated":False,
            "independent_holdout_verified":False,"blockers":["earlier_sample_count"],
            "results":[],"api_key":"secret","path":"private",**FALSE_FLAGS}

class GeminiReviewTests(unittest.TestCase):
    def test_allowlist_never_exports_secrets(self):
        p=prepare(report())
        self.assertNotIn("secret",str(p))
        self.assertNotIn("private",str(p))
        self.assertFalse(p["api_called"])
        self.assertFalse(p["network_requests"])
    def test_valid_review_never_changes_config(self):
        p=prepare(report())
        d=validate(p,{"packet_id":p["packet_id"],"findings":["insufficient_samples"],"next_checks":["collect_more_observations"]})
        self.assertFalse(d["configuration_changed"])
        self.assertFalse(d["model_promoted"])
        self.assertFalse(d["real_orders"])
    def test_reject_free_text_order_and_wrong_packet(self):
        p=prepare(report())
        base={"packet_id":p["packet_id"],"findings":[],"next_checks":[]}
        for change in ({"order":"buy"},{"findings":["buy"]},{"packet_id":"wrong"}):
            with self.assertRaises(ValueError):validate(p,{**base,**change})
    def test_metric_allowlist_and_online_mode(self):
        r=report();r["status"]="experiment_complete";r["blockers"]=[]
        m={"samples":50,"true_positive":20,"true_negative":20,"false_positive":5,"false_negative":5,
           "accuracy":0.8,"balanced_accuracy":0.8,"brier_score":0.2,"log_loss":0.5}
        r["results"]=[{"model":name,"later_window":m,"private":"secret"} for name in ("constant_training_prior","logistic_baseline","river_logistic")]
        p=prepare(r)
        self.assertEqual(p["summary"]["models"][-1]["evaluation_mode"],"delayed_prequential")
        self.assertNotIn("secret",str(p))
        m["log_loss"]=float("nan")
        with self.assertRaises(ValueError):prepare(r)
    def test_integrity_and_flags(self):
        r=report();r["real_orders"]=True
        with self.assertRaises(ValueError):prepare(r)
        p=prepare(report());p["summary"]["blockers"]=[]
        with self.assertRaises(ValueError):validate(p,{"packet_id":p["packet_id"],"findings":[],"next_checks":[]})
