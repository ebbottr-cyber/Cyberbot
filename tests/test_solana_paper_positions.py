import unittest
from tools.solana_paper_positions import simulate

M="1"*31+"2"
N="1"*31+"3"
def row(stamp,qty=200,returned=99000000,mint=M,index=0):
    return {"mint":mint,"timestamp":"2026-01-01T00:"+stamp+"+00:00",
            "input_raw":100000000,"token_amount_raw":qty,"return_raw":returned,
            "source_digest":"fixture","source_index":index}

class PaperPositionTests(unittest.TestCase):
    def test_later_exact_quantity_exit_and_cash(self):
        d=simulate([row("03:00",returned=110000000),row("00:00")])
        self.assertEqual(d["closed_positions"],1)
        self.assertEqual(d["open_positions"],0)
        self.assertEqual(d["realized_net_raw"],9475000)
        self.assertEqual(d["available_cash_raw"],1009475000)
        self.assertFalse(d["real_orders"])
        self.assertFalse(d["profitability_verified"])
    def test_mismatch_remains_open_not_rescaled(self):
        d=simulate([row("00:00"),row("03:00",qty=201)])
        self.assertEqual(d["closed_positions"],0)
        self.assertEqual(d["open_positions"],1)
        self.assertEqual(d["skips"]["exit_quantity_mismatch"],1)
        self.assertIsNone(d["final_equity_raw"])
        self.assertEqual(d["open_cost_basis_raw"],100250000)
        self.assertEqual(d["available_cash_raw"],899750000)
    def test_hold_and_no_same_batch_reentry(self):
        d=simulate([row("00:00"),row("01:00",returned=120000000),row("03:00")])
        self.assertEqual(len(d["events"]),2)
        self.assertEqual(d["closed"][0]["holding_seconds"],180)
    def test_simultaneous_conflicts_do_not_choose_best(self):
        d=simulate([row("00:00"),row("00:00",returned=120000000,index=1)])
        self.assertEqual(d["status"],"no_position_observations")
        self.assertEqual(d["skips"]["ambiguous_same_time_observation"],1)
    def test_capital_and_position_limit(self):
        d=simulate([row("00:00"),row("00:00",mint=N)],max_positions=1)
        self.assertEqual(d["open_positions"],1)
        self.assertEqual(d["skips"]["position_limit"],1)
        d=simulate([row("00:00")],initial_usdc=100)
        self.assertEqual(d["skips"]["insufficient_cash"],1)
        with self.assertRaises(ValueError):simulate([],hold_seconds=0)
    def test_prefix_does_not_depend_on_future_return(self):
        prefix=[row("00:00"),row("01:00")]
        a=simulate(prefix)
        b=simulate(prefix+[row("03:00",returned=150000000)])
        self.assertEqual(a["events"],b["events"][:len(a["events"])])

    def test_risk_stop_before_time_and_take_profit(self):
        for returned,reason in ((95000000,"stop_loss_observed"),(110000000,"take_profit_observed")):
            d=simulate([row("00:00"),row("01:00",returned=returned)],risk_mode=True,hold_seconds=900)
            self.assertEqual(d["closed_positions"],1)
            self.assertEqual(d["closed"][0]["exit_reason"],reason)
            self.assertEqual(d["closed"][0]["holding_seconds"],60)
            self.assertFalse(d["loss_budget_is_guaranteed"])
    def test_risk_time_exit_and_no_fabricated_stop_fill(self):
        d=simulate([row("00:00"),row("01:00",returned=100000000),row("03:00",returned=100000000)],risk_mode=True)
        self.assertEqual(d["closed"][0]["exit_reason"],"time_exit")
        d=simulate([row("00:00"),row("03:00",qty=201,returned=1000000)],risk_mode=True)
        self.assertEqual(d["open_positions"],1)
        self.assertIsNone(d["final_equity_raw"])
    def test_loss_budget_halts_new_entries_but_not_existing_exits(self):
        d=simulate([row("00:00"),row("00:00",mint=N),row("01:00",returned=50000000),
                    row("02:00"),row("03:00",mint=N,returned=110000000)],
                   risk_mode=True,hold_seconds=900,loss_budget_bps=400)
        self.assertTrue(d["entry_halted"])
        self.assertEqual(d["skips"]["realized_loss_budget_reached"],1)
        self.assertEqual(d["closed_positions"],2)
        self.assertEqual(d["open_positions"],0)
        self.assertEqual(d["gross_realized_loss_raw"],50375000)
    def test_exposure_and_position_cost_caps_include_stress(self):
        d=simulate([row("00:00"),row("00:00",mint=N)],risk_mode=True,exposure_bps=2000,position_bps=1500)
        self.assertEqual(d["open_positions"],1)
        self.assertEqual(d["skips"]["portfolio_cost_cap"],1)
        d=simulate([row("00:00")],risk_mode=True,position_bps=1000)
        self.assertEqual(d["skips"]["position_cost_cap"],1)
        with self.assertRaises(ValueError):simulate([],risk_mode=True,position_bps=4000)
    def test_risk_mode_no_future_price_dependency(self):
        prefix=[row("00:00"),row("01:00",returned=95000000)]
        a=simulate(prefix,risk_mode=True)
        b=simulate(prefix+[row("03:00",returned=200000000)],risk_mode=True)
        self.assertEqual(a["events"],b["events"][:len(a["events"])])
        self.assertFalse(b["intraperiod_risk_verified"])
