import os,unittest
from unittest.mock import patch
from tools.solana_public_scan import run,PilotError

def candidate(m,p):return {"mint":m,"pool":p,"security_verified":False}
class PublicScanTests(unittest.TestCase):
    def test_permission_and_limit(self):
        with patch.dict(os.environ,{"CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"0"}):
            with self.assertRaises(PilotError):run(discoverer=lambda:self.fail("network"))
        with patch.dict(os.environ,{"CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1"}):
            with self.assertRaises(PilotError):run(limit=4,discoverer=lambda:self.fail("network"))
    def test_distinct_mints_and_bounded_scan(self):
        calls=[];waits=[]
        def inspect(m,p):
            calls.append((m,p));return {"status":"diagnostic_complete"}
        rows=[candidate("a","p"),candidate("a","q"),candidate("b","r"),candidate("c","s")]
        with patch.dict(os.environ,{"CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1"}):
            d=run(discoverer=lambda:rows,inspect=inspect,sleep=waits.append)
        self.assertEqual(calls,[("a","p"),("b","r")]);self.assertEqual(waits,[10])
        self.assertEqual(d["status"],"scan_complete")
        for k in ("pilot_applied","real_orders","security_verified","depth_verified","live_data_verified"):
            self.assertFalse(d[k])
    def test_partial_stops_and_empty_is_not_success(self):
        calls=[]
        def inspect(m,p):
            calls.append(m);return {"status":"diagnostic_partial"}
        with patch.dict(os.environ,{"CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1"}):
            d=run(discoverer=lambda:[candidate("a","p"),candidate("b","q")],inspect=inspect,sleep=lambda n:self.fail("continued"))
            empty=run(discoverer=lambda:[],inspect=inspect)
        self.assertEqual(calls,["a"]);self.assertEqual(d["status"],"scan_partial")
        self.assertEqual(empty["status"],"scan_no_candidates")

    def test_unsupported_mint_skipped_but_provider_failure_stops(self):
        rows=[candidate("a","p"),candidate("b","q"),candidate("c","r")]
        calls=[]
        def inspect(m,p):
            calls.append(m)
            return {"status":{"a":"diagnostic_unsupported_mint","b":"diagnostic_complete","c":"diagnostic_partial"}[m]}
        with patch.dict(os.environ,{"CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1"}):
            d=run(discoverer=lambda:rows,inspect=inspect,sleep=lambda n:None)
            self.assertEqual(d["status"],"scan_complete_with_skips")
            self.assertEqual((d["completed_mints"],d["unsupported_mints"]),(1,1))
            d=run(limit=3,discoverer=lambda:rows,inspect=inspect,sleep=lambda n:None)
            self.assertEqual(d["status"],"scan_partial")
            d=run(discoverer=lambda:rows,inspect=lambda m,p:{"status":"diagnostic_unsupported_mint"},sleep=lambda n:None)
            self.assertEqual(d["status"],"scan_no_supported_candidates")
            self.assertEqual(d["completed_mints"],0)

    def test_snapshot_mint_rejection_short_circuits(self):
        from tools.solana_public_snapshot import run as snapshot
        mint="1"*31+"2";pool="1"*31+"3"
        def raw(v):return {"jsonrpc":"2.0","id":1,"result":{"context":{"slot":100},"value":v}}
        account={"owner":"1"*31+"4","executable":False}
        with patch.dict(os.environ,{"CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1"}):
            with patch("tools.solana_public_snapshot.request",return_value=raw(account)) as req:
                d=snapshot(mint,pool)
                self.assertEqual(d["status"],"diagnostic_unsupported_mint")
                self.assertEqual(set(d["stages"]),{"mint"})
                self.assertFalse(d["security_verified"]);req.assert_called_once()
            with patch("tools.solana_public_snapshot.request",side_effect=PilotError("RPC HTTP 429")) as req:
                d=snapshot(mint,pool)
                self.assertEqual(d["status"],"diagnostic_partial")
                req.assert_called_once()
            with patch("tools.solana_public_snapshot.request",return_value=raw({})) as req:
                self.assertEqual(snapshot(mint,pool)["status"],"diagnostic_partial")
                req.assert_called_once()
