import unittest
from cyberbot.adaptive import decide,evaluate,CANDIDATES
from cyberbot.regimes import demo_rows

class AdaptiveTests(unittest.TestCase):
    def test_default_and_risk_gate(self):
        evidence={k:[] for k in CANDIDATES}
        self.assertEqual(decide("bull",evidence)["strategy"],"cash")
        evidence["trend"]=[{"closed":10,"observations":[("bull",.001,.0005)]*20} for _ in range(2)]
        self.assertEqual(decide("bull",evidence)["strategy"],"trend")
        evidence["trend"].append({"closed":1,"observations":[("bull",-.2,-.2)]*20})
        self.assertEqual(decide("bull",evidence)["strategy"],"cash")
    def test_causal_and_capital(self):
        rows=demo_rows("BIST")
        a=evaluate(rows,mode="synthetic",market="BIST",symbol="demo")
        changed=rows[:340]+[{"open":"100","close":"90"} for _ in range(20)]
        b=evaluate(changed,mode="synthetic",market="BIST",symbol="demo")
        self.assertEqual(a["decisions"][:-1],b["decisions"][:-1])
        for key in ("regime","selected","window","ranking"):
            self.assertEqual(a["decisions"][-1][key],b["decisions"][-1][key])
        self.assertEqual(a["initial_capital"],"45000")
        self.assertFalse(a["paper_orders"])
        self.assertFalse(a["promotion_enabled"])
        self.assertEqual(a["decisions"][0]["selected"],"cash")
        self.assertEqual(sum(a["selection_counts"].values()),a["completed_blocks"])
    def test_flat(self):
        d=evaluate([{"open":"100","close":"100"}]*240,mode="synthetic",market="SOLANA",symbol="demo")
        self.assertEqual(d["shadow"]["ending_capital"],"1000.00")
        self.assertEqual(d["selection_counts"]["cash"],d["completed_blocks"])
        self.assertEqual(d["next_research_candidate"]["strategy"],"cash")
