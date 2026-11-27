import os,unittest
from unittest.mock import patch
from tools.solana_size_probe import run,PilotError

M="1"*31+"2"
class SizeProbeTests(unittest.TestCase):
    def test_stop_after_failure_without_retry(self):
        calls=[];sleeps=[]
        def probe(mint,*,amount):
            calls.append(amount)
            raise PilotError("quote: HTTP 429; no_retry")
        with patch.dict(os.environ,{"CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1"}):
            d=run(M,probe=probe,sleep=sleeps.append)
        self.assertEqual(calls,[25000000]);self.assertEqual(sleeps,[])
        self.assertEqual(d["status"],"probe_partial")
        self.assertFalse(d["real_orders"]);self.assertFalse(d["depth_verified"])
    def test_three_bounded_sequential_sizes(self):
        calls=[];sleeps=[]
        def probe(mint,*,amount):
            calls.append(amount)
            route={"route_kind":"single_direct","accounting":{},"reported_fee_bps":None,"reported_fee_mint":None}
            return {"retrieved_at":"fixture","reported_roundtrip_return_usdc":"24.9","reported_roundtrip_pct":"-0.4","buy":route,"sell":route}
        with patch.dict(os.environ,{"CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1"}):
            d=run(M,probe=probe,sleep=sleeps.append)
        self.assertEqual(calls,[25000000,50000000,100000000])
        self.assertEqual(sleeps,[5,5]);self.assertEqual(d["status"],"probe_complete")
        self.assertFalse(d["pilot_applied"])
