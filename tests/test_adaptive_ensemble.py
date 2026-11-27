"""Synthetic tests for the optional regime-weight policy."""
import unittest
from tools.local_research.ensemble_review import (
    choose_regime_weights, adaptive_score, WEIGHTS, regime_key)
import json
from tools.local_research.ai_regime_review import context


class AdaptiveEnsembleTests(unittest.TestCase):
    def calibration(self):
        # Opposite component biases across regimes; the general blend is
        # deliberately not optimal for either subgroup.
        records,keys=[],[]
        for day in range(5):
            for i in range(6):
                records.append((str(day),.2,(.2,.1,.1),{}))
                keys.append("bull/normal")
                records.append((str(day),.2,(.1,.2,.1),{}))
                keys.append("bear/normal")
        return records,keys

    def test_calibration_selects_regime_specific_weights(self):
        records,keys=self.calibration()
        policies=choose_regime_weights(records,keys,WEIGHTS[0])
        self.assertEqual(policies["bull/normal"],(.6,.2,.2))
        self.assertEqual(policies["bear/normal"],(.2,.6,.2))
        self.assertNotIn("sideways/normal",policies)

    def test_small_group_uses_global_fallback(self):
        records,keys=self.calibration()
        policies=choose_regime_weights(records[:20],keys[:20],WEIGHTS[0])
        self.assertEqual(policies,{})
        error,usage=adaptive_score(records[:20],keys[:20],WEIGHTS[0],policies)
        self.assertEqual(usage,{"global_fallback":20})
        self.assertGreater(error,0)

    def test_holdout_changes_do_not_modify_calibration_weights(self):
        records,keys=self.calibration()
        policies=choose_regime_weights(records,keys,WEIGHTS[0])
        before=policies.copy()
        a,usage=adaptive_score(records,keys,WEIGHTS[0],policies)
        b,_=adaptive_score([(d,-y,p,e) for d,y,p,e in records],keys,WEIGHTS[0],policies)
        self.assertNotEqual(a,b)
        self.assertEqual(policies,before)
        self.assertEqual(sum(usage.values()),60)

    def test_missing_and_inconsistent_regime(self):
        self.assertIsNone(regime_key("{}"))
        p=context([100]*21)
        self.assertEqual(regime_key(json.dumps({"regime_context":p})),"sideways/normal")
        p["direction"]="bull"
        with self.assertRaises(ValueError):
            regime_key(json.dumps({"regime_context":p}))

    def test_mismatched_alignment_rejected(self):
        with self.assertRaises(ValueError):
            adaptive_score([("d",.2,(.1,.2,.3),{})],[],WEIGHTS[0],{})
