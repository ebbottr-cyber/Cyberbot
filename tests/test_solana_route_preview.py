import os,unittest
from datetime import datetime,timezone
from unittest.mock import patch
from tools.solana_route_preview import inspect,run,USDC,AMOUNT,PilotError

M="1"*31+"2"
P="1"*31+"3"
Q="1"*31+"4"
def fixture(a,b,n,out,split=False):
    def leg(pool,u,v,bps):
        return {"bps":bps,"swapInfo":{"ammKey":pool,"inputMint":a,"outputMint":b,"inAmount":str(u),"outAmount":str(v)}}
    routes=[leg(P,n,out,10000)] if not split else [leg(P,n//2,out//2,5000),leg(Q,n-n//2,out-out//2,5000)]
    return {"inputMint":a,"outputMint":b,"swapMode":"ExactIn","inAmount":str(n),"outAmount":str(out),"transaction":None,"routePlan":routes}

class RoutePreviewTests(unittest.TestCase):
    def test_split_is_observed_not_verified(self):
        d=inspect(fixture(M,USDC,100,90,True),M,USDC,100)
        self.assertEqual(d["route_kind"],"split_direct")
        self.assertEqual(d["direct_bps_sum"],10000)
        self.assertEqual(d["direct_input_delta_raw"],"0")
        self.assertFalse(d["route_integrity_verified"])
    def test_invalid_quote_rejected(self):
        raw=fixture(M,USDC,100,90)
        for change in ({"transaction":"encoded"},{"inAmount":"99"},{"routePlan":[]},{"taker":P}):
            with self.assertRaises(PilotError):inspect({**raw,**change},M,USDC,100)
    def test_roundtrip_has_no_pilot_or_security_promotion(self):
        calls=[]
        def mock(p):
            calls.append(p)
            n=int(p["amount"])
            return fixture(p["inputMint"],p["outputMint"],n,200 if len(calls)==1 else 99000000,len(calls)>1)
        with patch.dict(os.environ,{"CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"0"}):
            with self.assertRaises(PilotError):run(M,transport=mock)
        self.assertEqual(calls,[])
        with patch.dict(os.environ,{"CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1"}):
            d=run(M,transport=mock,clock=lambda:datetime(2026,1,1,tzinfo=timezone.utc))
        self.assertEqual(calls[1]["amount"],"200")
        self.assertEqual(d["reported_roundtrip_return_usdc"],"99")
        for flag in ("pilot_applied","real_orders","security_verified","route_integrity_verified","api_key_used","live_data_verified"):
            self.assertFalse(d[flag])

    def test_multihop_arithmetic_matches_observed_shape(self):
        from tools.solana_route_preview import accounting
        mid="So11111111111111111111111111111111111111112"
        def leg(a,b,u,v,bps):
            return {"input_mint":a,"output_mint":b,"input_raw":str(u),"output_raw":str(v),"bps":bps}
        legs=[leg(M,USDC,2711611170118,59180900,5926),
              leg(M,mid,1346978549306,405512258,2944),
              leg(M,mid,516905519949,155622097,1130),
              leg(mid,USDC,561134355,40682720,10000)]
        d=accounting(legs,M,USDC,4575495239373,99763757)
        self.assertTrue(d["reported_input_and_intermediate_balanced"])
        self.assertEqual(d["source_bps_sum"],10000)
        self.assertEqual(d["terminal_gross_minus_reported_raw"],"99863")
        self.assertFalse(d["terminal_output_exact_match"])
        self.assertFalse(d["fee_semantics_verified"])
        legs[-1]["input_raw"]="561134356"
        self.assertFalse(accounting(legs,M,USDC,4575495239373,99763757)["reported_input_and_intermediate_balanced"])
        legs.append(leg(mid,M,1,1,1))
        self.assertFalse(accounting(legs,M,USDC,4575495239373,99763757)["graph_connected_acyclic"])

    def test_custom_probe_amount_and_bounds(self):
        calls=[]
        def mock(p):
            calls.append(p)
            n=int(p["amount"])
            return fixture(p["inputMint"],p["outputMint"],n,200 if len(calls)==1 else 24900000)
        with patch.dict(os.environ,{"CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1"}):
            for invalid in (0,100000001,True):
                with self.assertRaises(PilotError):run(M,amount=invalid,transport=mock)
            self.assertEqual(calls,[])
            d=run(M,amount=25000000,transport=mock,clock=lambda:datetime(2026,1,1,tzinfo=timezone.utc))
        self.assertEqual(calls[0]["amount"],"25000000")
        self.assertEqual(d["test_input_usdc"],"25")
        self.assertEqual(d["reported_roundtrip_pct"],"-0.400")
        self.assertFalse(d["depth_verified"])
