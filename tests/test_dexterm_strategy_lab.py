import unittest
from tools.dexterm_strategy_lab import compare,POLICIES

M="1"*31+"2"
N="1"*31+"3"
def row(minute,mint=M,returned=99000000,index=0):
    return {"mint":mint,"timestamp":f"2026-01-01T00:{minute:02d}:00+00:00",
            "input_raw":100000000,"token_amount_raw":200,"return_raw":returned,
            "source_digest":"fixture","source_index":index}

class StrategyLabTests(unittest.TestCase):
    def test_independent_balances_and_no_winner(self):
        d=compare([row(0)])
        self.assertEqual(len(d["policies"]),len(POLICIES))
        for r in d["policies"]:
            self.assertEqual(r["full_history"]["available_cash_raw"],899750000)
            self.assertIsNone(r["full_history"]["final_equity_raw"])
        self.assertIsNone(d["winner"])
        self.assertFalse(d["automatic_model_selection"])
        self.assertFalse(d["sample_gate_met"])
    def test_split_never_divides_timestamp_batch(self):
        rows=[row(i) for i in range(10)]+[row(7,mint=N)]
        d=compare(rows)
        self.assertEqual(d["split_timestamp"],"2026-01-01T00:07:00+00:00")
        self.assertEqual((d["earlier_observations"],d["later_observations"]),(7,4))
        self.assertEqual(d["evidence_status"],"insufficient_comparable_evidence")
    def test_later_window_cannot_change_earlier_metrics(self):
        rows=[row(i) for i in range(10)]
        a=compare(rows)
        b=compare(rows[:7]+[row(i,returned=150000000) for i in range(7,10)])
        self.assertNotEqual(a["dataset_sha256"],b["dataset_sha256"])
        self.assertEqual([r["earlier_window"] for r in a["policies"]],
                         [r["earlier_window"] for r in b["policies"]])
        self.assertFalse(b["profitability_verified"])
        self.assertFalse(b["real_orders"])
    def test_input_order_deterministic_and_empty(self):
        rows=[row(0),row(3),row(6)]
        self.assertEqual(compare(rows),compare(list(reversed(rows))))
        d=compare([])
        self.assertEqual(d["status"],"no_usable_quotes")
        self.assertIsNone(d["split_timestamp"])
        self.assertIsNone(d["winner"])
        self.assertFalse(d["weights_updated"])
