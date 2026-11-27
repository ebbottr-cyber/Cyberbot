import os,unittest
from unittest.mock import patch
import httpx
from tools.dexterm_pool_bridge import match_pool,run
from cyberbot.providers.solana_observed import USDC
from tools.solana_public_scan import REFERENCE_MINTS
from cyberbot.solana_pilot import ALPHABET

def addr(i):return "1"*31+ALPHABET[i]
def pair(m,p,q=USDC,liq=200000):
    return {"chainId":"solana","baseToken":{"address":m,"symbol":"X"},"quoteToken":{"address":q},"pairAddress":p,"liquidity":{"usd":liq}}
def report(mints):
    return {"source":"dexterm_screener_query","status":"diagnostic_complete","source_error_count":0,
            "candidate_count":len(mints),"candidates":[{"mint":m,"reported":{"priceUsd":1,"liquidityUsd":200000,"ageSec":3,"fetchedAt":100000}} for m in mints],
            "security_verified":False,"live_data_verified":False,"pilot_applied":False,"real_orders":False}

class DexTermPoolBridgeTests(unittest.TestCase):
    def test_exact_mint_direct_usdc_and_liquidity(self):
        m=addr(1)
        raw={"pairs":[pair(addr(2),addr(10),liq=999999),pair(m,addr(11),q=addr(3)),pair(m,addr(12),liq=99999),pair(m,addr(13))]}
        self.assertEqual(match_pool(raw,m)["pool"],addr(13))
        self.assertIsNone(match_pool({"pairs":raw["pairs"][:3]},m))
    def test_bounded_novel_candidates(self):
        mints=[REFERENCE_MINTS["BONK"],addr(1),addr(2),addr(3),addr(4)]
        calls=[];inspected=[]
        def look(c,m):
            calls.append(m)
            return None if m==addr(1) else match_pool({"pairs":[pair(m,addr(10))]},m)
        def inspect(m,p):
            inspected.append(m)
            return {"status":"diagnostic_complete"}
        with patch.dict(os.environ,{"CYBERBOT_PILOT_KILL_SWITCH":"1","CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1"}):
            d=run(report(mints),lookup_fn=look,inspect=inspect,sleep=lambda n:None)
        self.assertEqual(calls,mints[1:4])
        self.assertEqual(inspected,[addr(2)])
        self.assertEqual(d["remaining_mints"],[addr(4)])
        self.assertEqual(d["matched_pool_count"],2)
        self.assertFalse(d["security_verified"])
    def test_provider_failure_stops_before_snapshot(self):
        calls=[]
        def look(c,m):
            calls.append(m)
            if m==addr(1):return match_pool({"pairs":[pair(m,addr(10))]},m)
            raise httpx.HTTPStatusError("rate",request=httpx.Request("GET","https://example.invalid"),response=httpx.Response(429))
        with patch.dict(os.environ,{"CYBERBOT_PILOT_KILL_SWITCH":"1","CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1"}):
            d=run(report([addr(1),addr(2),addr(3)]),lookup_fn=look,inspect=lambda *a:self.fail("snapshot"),sleep=lambda n:None)
        self.assertEqual(calls,[addr(1),addr(2)])
        self.assertEqual(d["status"],"lookup_partial")
        self.assertEqual(d["matched_pool_count"],1)
        self.assertIsNone(d["scan"])
        self.assertFalse(d["real_orders"])
    def test_no_matching_pool_is_not_success(self):
        with patch.dict(os.environ,{"CYBERBOT_PILOT_KILL_SWITCH":"1","CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1"}):
            d=run(report([addr(1)]),lookup_fn=lambda *a:None,inspect=lambda *a:self.fail("snapshot"),sleep=lambda n:None)
        self.assertEqual(d["status"],"no_eligible_pools")
