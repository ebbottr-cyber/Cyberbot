import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cyberbot.dexterm_replay_status import FALSE_FLAGS, read, summarize


def fixture(*, opened=False):
    return {"status":"position_replay_complete","research_only":True,"paper_position_replay_only":True,
            "network_requests":False,**dict.fromkeys(FALSE_FLAGS,False),
            "initial_balance_raw":1_000_000_000,"available_cash_raw":902_000_000 if opened else 1_002_000_000,
            "open_cost_basis_raw":100_000_000 if opened else 0,"realized_net_raw":2_000_000,
            "closed":[{"realized_net_raw":2_000_000}],"open":[{"entry_total_raw":100_000_000,"market_value_raw":None}] if opened else [],
            "closed_positions":1,"open_positions":int(opened),"positive_closed_positions":1,
            "final_equity_raw":None if opened else 1_002_000_000,"unrealized_net_raw":None if opened else 0,
            "entry_halted":False,"risk_mode":True,"gross_realized_loss_raw":0}


class DexTermReplayPanelTests(unittest.TestCase):
    def test_closed_replay_is_distinct_from_live(self):
        result=summarize(fixture())
        self.assertEqual(result["realized_pnl"],"2.000000")
        self.assertEqual(result["final_equity"],"1002.000000")
        self.assertEqual(result["mode"],"historical_replay_only")
        self.assertFalse(result["paper_execution_verified"])

    def test_open_replay_is_not_marked_to_market(self):
        report=fixture(opened=True)
        self.assertIsNone(summarize(report)["final_equity"])
        report["final_equity_raw"]=1_002_000_000
        with self.assertRaises(ValueError):summarize(report)

    def test_authority_accounting_and_counts(self):
        for field,value in (("real_orders",True),("available_cash_raw",0),
                            ("realized_net_raw",1),("closed_positions",2),
                            ("gross_realized_loss_raw",5),("positive_closed_positions",False)):
            with self.subTest(field=field):
                report=fixture();report[field]=value
                with self.assertRaises(ValueError):summarize(report)

    def test_missing_and_malformed_report(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"replay.json"
            self.assertEqual(read(path)["status"],"report_missing")
            self.assertFalse(path.exists())
            path.write_bytes(b"not json")
            self.assertEqual(read(path)["status"],"report_unavailable")
            raw=json.dumps(fixture()).encode("utf-8-sig")
            path.write_bytes(raw)
            self.assertEqual(read(path)["cash"],"1002.000000")
            self.assertEqual(path.read_bytes(),raw)

    @patch("cyberbot.integration_api.pilot_control_snapshot",return_value={"halted":True})
    @patch("cyberbot.integration_api.pilot_performance_snapshot",return_value={"mode":"operator_observed_unverified","real_orders":False,"markets":[],"as_of":None})
    @patch("cyberbot.integration_api.dexterm_replay_status")
    def test_central_portfolio_never_counts_replay_as_observed(self, replay, performance, control):
        from cyberbot.integration_api import portfolio_risk_status
        replay.return_value=summarize(fixture())
        data=portfolio_risk_status()
        sol=next(r for r in data["markets"] if r["market"]=="SOLANA")
        self.assertIsNone(sol["cash"])
        self.assertIsNone(sol["equity"])
        self.assertIsNone(sol["risk_gate"])
        self.assertEqual(sol["historical_replay"]["cash"],"1002.000000")
        self.assertIsNone(data["combined_equity"])
