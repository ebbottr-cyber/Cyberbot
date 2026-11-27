import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from tools.solana_exact_exit_quotes import run,select,validate_report
from tools.dexterm_research_archive import extract
from tools.solana_paper_replay import FALSE_FLAGS
from cyberbot.providers.solana_observed import USDC

M="1"*31+"2"
P="1"*31+"3"
NOW=datetime(2026,1,1,1,tzinfo=timezone.utc)
def row(age,qty=200,index=0):
    return {"mint":M,"timestamp":(NOW-timedelta(seconds=age)).isoformat(),
            "token_amount_raw":qty,"source_digest":"a"*64,"source_index":index}
def quote(params):
    return {"inputMint":params["inputMint"],"outputMint":USDC,"swapMode":"ExactIn",
            "inAmount":params["amount"],"outAmount":"99000000",
            "routePlan":[{"bps":10000,"swapInfo":{"ammKey":P,"inputMint":params["inputMint"],
                         "outputMint":USDC,"inAmount":params["amount"],"outAmount":"99000000"}}]}

class ExactExitQuoteTests(unittest.TestCase):
    def test_select_bounded_age_and_quantity_dedup(self):
        rows=[row(3601),row(179),row(300),row(200),row(250,201,1)]
        self.assertEqual([r["token_amount_raw"] for r in select(rows,NOW,3)],[200,201])
    def test_wallet_free_exact_quantity_and_mock_rejected(self):
        with patch("tools.solana_exact_exit_quotes.permissions"),patch("tools.solana_exact_exit_quotes.collect",return_value=([row(300)],{})):
            seen=[]
            def transport(p):seen.append(p);return quote(p)
            d=run("unused",transport=transport,clock=lambda:NOW)
        self.assertEqual(seen,[{"inputMint":M,"outputMint":USDC,"amount":"200"}])
        self.assertEqual(d["status"],"exit_quotes_complete")
        self.assertFalse(d["real_orders"])
        with self.assertRaises(ValueError):validate_report(d)
    def test_valid_report_and_archive_kind(self):
        with patch("tools.solana_exact_exit_quotes.permissions"),patch("tools.solana_exact_exit_quotes.collect",return_value=([row(300)],{})),patch("tools.solana_exact_exit_quotes.request",side_effect=lambda c,k,p,key:quote(p)):
            d=run("unused",clock=lambda:NOW)
        self.assertEqual(extract(d)[0],"exit_quote")
        self.assertEqual(validate_report(d)[0]["quantity_raw"],"200")
        d["quotes"][0]["quantity_raw"]="201"
        with self.assertRaises(ValueError):validate_report(d)
    def test_stop_on_first_failed_quote(self):
        with patch("tools.solana_exact_exit_quotes.permissions"),patch("tools.solana_exact_exit_quotes.collect",return_value=([row(300),row(250,201,1)],{})):
            d=run("unused",transport=lambda p:{"error":"unavailable"},clock=lambda:NOW,sleep=lambda s:None)
        self.assertEqual(d["attempted_quotes"],1)
        self.assertEqual(d["status"],"exit_quotes_partial")
        self.assertEqual(d["quotes"],[])
    def test_no_due_entries_and_permission_gate(self):
        with patch("tools.solana_exact_exit_quotes.permissions"),patch("tools.solana_exact_exit_quotes.collect",return_value=([row(20)],{})):
            d=run("unused",clock=lambda:NOW)
        self.assertEqual(d["status"],"no_due_entries")
        with patch("tools.solana_exact_exit_quotes.permissions",side_effect=ValueError("denied")),patch("tools.solana_exact_exit_quotes.collect") as c:
            with self.assertRaises(ValueError):run("unused")
            c.assert_not_called()
