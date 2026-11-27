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
