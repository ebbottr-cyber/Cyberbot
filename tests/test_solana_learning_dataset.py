import unittest
from datetime import datetime,timezone,timedelta
from tools.solana_learning_dataset import build,FEATURE_NAMES

M="1"*31+"2"
N="1"*31+"3"
def row(s,qty=200,mint=M,ret=99000000,index=0):
    return {"mint":mint,"timestamp":(datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(seconds=s)).isoformat(),
            "input_raw":100000000,"token_amount_raw":qty,"return_raw":ret,
            "source_digest":"fixture","source_index":index}
def history():
    return [row(i*180,index=i) for i in range(100)]

class LearningDatasetTests(unittest.TestCase):
    def test_features_and_labels_separate(self):
        d=build(history())
        self.assertGreater(d["example_count"],0)
        r=d["examples"][0]
        self.assertEqual(set(r["features"]),set(FEATURE_NAMES))
        self.assertEqual(r["label"]["quote_net_raw"],-1497500)
        self.assertFalse(r["label"]["positive_quote_net"])
        self.assertFalse(d["training_allowed"])
        self.assertFalse(d["real_orders"])
    def test_purge_and_no_future_feature_change(self):
        rows=history()
        a=build(rows)
        b=build([dict(r,return_raw=150000000) if i==2 else r for i,r in enumerate(rows)])
        x=a["examples"][0];y=b["examples"][0]
        self.assertEqual(x["features"],y["features"])
        self.assertNotEqual(x["label"],y["label"])
        self.assertGreater(a["skipped"]["split_boundary_purged"],0)
        for r in a["examples"]:
            if r["partition"]=="earlier":self.assertLess(r["label_at"],a["split_timestamp"])
    def test_quantity_mismatch_not_labeled(self):
        rows=[row(i*180,qty=200+i,index=i) for i in range(100)]
        d=build(rows)
        self.assertEqual(d["example_count"],0)
        self.assertGreater(d["skipped"]["no_exact_quantity_exit"],0)
    def test_determinism_and_censoring(self):
        rows=history()
        self.assertEqual(build(rows),build(list(reversed(rows))))
        self.assertGreater(build(rows)["skipped"]["right_censored"],0)
        self.assertEqual(build([])["status"],"no_labeled_examples")
    def test_ambiguous_rows_and_invalid_cost(self):
        d=build(history()+[row(180,qty=201,index=999)])
        self.assertEqual(d["ambiguous_observations"],2)
        with self.assertRaises(ValueError):build([],stress_bps=-1)
