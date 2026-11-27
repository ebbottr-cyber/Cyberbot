import os,unittest,tempfile
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from cyberbot.providers.solana_observed import run,USDC,LEGACY,PilotError
class SolanaObservedTests(unittest.TestCase):
    def test_diagnostics_only(self):
        mint="1"*31+"2";pool="1"*31+"3";holder="1"*31+"4"
        t=datetime(2026,1,1,tzinfo=timezone.utc);calls=[];wrong=False
        def rpc(v):return {"jsonrpc":"2.0","id":1,"result":{"context":{"slot":100},"value":v}}
        def mock(kind,p):
            calls.append(kind)
            if kind=="rpc":
                if p[0]=="getAccountInfo":return rpc({"owner":LEGACY,"executable":False,"data":{"program":"spl-token","parsed":{"type":"mint","info":{"decimals":6,"supply":"1000000000","isInitialized":True,"mintAuthority":None,"freezeAuthority":None}}}})
                return rpc([{"address":holder,"amount":"100000000","decimals":6}])
            if kind=="pool":return {"pairs":[{"chainId":"solana","pairAddress":pool,"baseToken":{"address":mint},"quoteToken":{"address":USDC},"liquidity":{"usd":"200000"},"priceUsd":"1"}]}
            amount=p["amount"];out=amount if p["inputMint"]==USDC else str(int(amount)*99//100)
            return {"inputMint":p["inputMint"],"outputMint":p["outputMint"],"swapMode":"ExactIn","inAmount":amount,"outAmount":out,"transaction":None,"routePlan":[{"percent":100,"swapInfo":{"ammKey":holder if wrong else pool,"inputMint":p["inputMint"],"outputMint":p["outputMint"],"inAmount":amount,"outAmount":out}}]}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.dict(os.environ,{"CYBERBOT_SOLANA_OBSERVED_ENABLED":"1","CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1","CYBERBOT_JUPITER_KEY":"fixture","CYBERBOT_SOLANA_PILOT_MINT":mint,"CYBERBOT_SOLANA_PILOT_POOL":pool,"CYBERBOT_PILOT_DB":str(root/"pilot.sqlite3")}):
                with patch.dict(os.environ,{"CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"0"}):
                    with self.assertRaises(PilotError):run(transport=mock,clock=lambda:t)
                    self.assertEqual(calls,[])
                d=run(transport=mock,clock=lambda:t)
                self.assertEqual(d["indicative_ask_usdc"],"1")
                self.assertEqual(d["indicative_bid_usdc"],"0.99")
                self.assertFalse(d["pilot_applied"]);self.assertFalse(d["security_verified"])
                self.assertEqual(d["risk_screen"]["status"],"reported_checks_passed_unverified")
                self.assertFalse(d["risk_screen"]["trade_eligible"])
                self.assertFalse(d["risk_screen"]["execution_slippage_verified"])
                self.assertEqual(d["mint_checks"]["top10_token_account_pct"],"10")
                self.assertFalse(d["mint_checks"]["wallet_concentration_verified"])
                self.assertEqual(calls,["rpc","rpc","pool","quote","quote"])
                self.assertIsNone(d["depth_probe"])
                calls.clear()
                probe=run(transport=mock,clock=lambda:t,depth_probe=True)["depth_probe"]
                self.assertEqual(calls,["rpc","rpc","pool"]+["quote"]*6)
                self.assertEqual([row["input_usdc"] for row in probe["samples"]],["25","50","100"])
                self.assertFalse(probe["depth_verified"])
                self.assertFalse(probe["trade_eligible"])
                self.assertFalse(probe["real_orders"])
                wrong=True
                with self.assertRaises(PilotError):run(transport=mock,clock=lambda:t)
                self.assertEqual(list(root.iterdir()),[])

    def test_anonymous_opt_in_and_net_output(self):
        from cyberbot.providers.solana_observed import configured,quote
        inp=USDC;out="1"*31+"2";pool="1"*31+"3"
        with patch.dict(os.environ,{"CYBERBOT_SOLANA_OBSERVED_ENABLED":"1","CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1","CYBERBOT_JUPITER_KEY":"","CYBERBOT_JUPITER_ANONYMOUS_ENABLED":"0"}):
            self.assertFalse(configured())
            with patch.dict(os.environ,{"CYBERBOT_JUPITER_ANONYMOUS_ENABLED":"1"}):
                self.assertTrue(configured())
                with patch.dict(os.environ,{"CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"0"}):self.assertFalse(configured())
        raw={"inputMint":inp,"outputMint":out,"swapMode":"ExactIn","inAmount":"100000000","outAmount":"7281385","transaction":None,"taker":None,"feeBps":2,"feeMint":inp,"platformFee":{"feeBps":2,"feeMint":inp},"routePlan":[{"bps":10000,"swapInfo":{"ammKey":pool,"inputMint":inp,"outputMint":out,"inAmount":"100000000","outAmount":"7282841"}}]}
        self.assertEqual(quote(raw,inp,out,100000000,pool),7281385)
        raw["outAmount"]="7280000"
        with self.assertRaises(PilotError):quote(raw,inp,out,100000000,pool)

    def test_provider_failure_identifies_stage_without_secret(self):
        import httpx
        from cyberbot.providers.solana_observed import request
        def rate_limit(req):
            return httpx.Response(429,text="private response")
        with httpx.Client(transport=httpx.MockTransport(rate_limit)) as c:
            for kind,params,stage in (
                ("rpc",("getTokenLargestAccounts",[]),"solana_rpc.getTokenLargestAccounts"),
                ("pool","1"*31+"3","dexscreener.pool"),
                ("quote",{"inputMint":USDC},"jupiter.buy"),
                ("quote",{"inputMint":"1"*31+"2"},"jupiter.sell"),
            ):
                with self.assertRaises(PilotError) as ctx:request(c,kind,params,"secret-fixture")
                self.assertEqual(str(ctx.exception),stage+": HTTP 429; no_retry")
        def rpc_error(req):
            return httpx.Response(200,json={"jsonrpc":"2.0","id":1,"error":{"code":-32005,"message":"private"}})
        with httpx.Client(transport=httpx.MockTransport(rpc_error)) as c:
            with self.assertRaises(PilotError) as ctx:request(c,"rpc",("getAccountInfo",[]),"")
            self.assertEqual(str(ctx.exception),"solana_rpc.getAccountInfo: RPC -32005; no_retry")

    def test_rpc_provider_allowlist(self):
        import httpx
        from cyberbot.providers.solana_observed import request,rpc_endpoint
        seen=[]
        def transport(req):
            seen.append(str(req.url))
            self.assertNotIn("x-api-key",req.headers)
            return httpx.Response(200,json={"jsonrpc":"2.0","id":1,"result":{}})
        with httpx.Client(transport=httpx.MockTransport(transport)) as c:
            for name,url in (("official","https://api.mainnet-beta.solana.com"),("publicnode","https://solana-rpc.publicnode.com")):
                with patch.dict(os.environ,{"CYBERBOT_SOLANA_RPC_PROVIDER":name}):
                    self.assertEqual(rpc_endpoint(),(name,url))
                    request(c,"rpc",("getAccountInfo",[]),"fixture")
                    self.assertEqual(seen[-1].rstrip("/"),url)
            with patch.dict(os.environ,{"CYBERBOT_SOLANA_RPC_PROVIDER":"https://example.invalid"}):
                with self.assertRaises(PilotError):request(c,"rpc",("getAccountInfo",[]),"fixture")
            with self.assertRaises(PilotError):request(c,"rpc",("getAccountInfo",[]),"fixture",rpc_url="https://example.invalid")
        self.assertEqual(len(seen),2)

    def test_risk_screen_reports_all_failures_without_execution(self):
        from cyberbot.providers.solana_observed import risk_screen
        info={"mint_authority_disabled":False,"freeze_authority_disabled":False}
        holders={"top10_token_account_pct":"31"}
        pool={"liquidity_usd_reported":"99999"}
        result=risk_screen(info,holders,pool,"1.03","1")
        self.assertEqual(result["status"],"reported_risk_detected")
        self.assertEqual(len(result["failed_checks"]),5)
        for name in ("trade_eligible","pilot_applied","security_verified","depth_verified",
                     "real_orders","wallet_concentration_verified","execution_slippage_verified"):
            self.assertIs(result[name],False)

    def test_risk_screen_boundaries_and_crossed_quotes(self):
        from cyberbot.providers.solana_observed import risk_screen
        info={"mint_authority_disabled":True,"freeze_authority_disabled":True}
        holders={"top10_token_account_pct":"30"}
        pool={"liquidity_usd_reported":"100000"}
        good=risk_screen(info,holders,pool,"1.02","1")
        self.assertEqual(good["failed_checks"],[])
        self.assertEqual(good["status"],"reported_checks_passed_unverified")
        self.assertFalse(good["trade_eligible"])
        crossed=risk_screen(info,holders,pool,"1","1.01")
        self.assertEqual(crossed["failed_checks"],["indicative_spread_at_most_2pct"])
        with self.assertRaises(PilotError):risk_screen(info,holders,pool,"1","0")
        with self.assertRaises(PilotError):risk_screen(info,{"top10_token_account_pct":"NaN"},pool,"1","1")

    def test_quote_ladder_adverse_price_change(self):
        from decimal import Decimal
        from cyberbot.providers.solana_observed import quote_ladder
        probe=quote_ladder([(25,25000000,24750000),(50,49000000,48000000),
                            (100,95000000,90000000)],6)
        rows=probe["samples"]
        self.assertEqual(Decimal(rows[0]["ask_change_vs_smallest_pct"]),0)
        self.assertGreater(Decimal(rows[2]["ask_change_vs_smallest_pct"]),
                           Decimal(rows[1]["ask_change_vs_smallest_pct"]))
        self.assertGreater(Decimal(rows[2]["bid_deterioration_vs_smallest_pct"]),0)
        self.assertEqual(Decimal(rows[2]["roundtrip_loss_pct"]),10)
        self.assertFalse(probe["source_synchronization_verified"])
        self.assertFalse(probe["execution_slippage_verified"])

    def test_quote_ladder_crossed_quote_not_execution_evidence(self):
        from cyberbot.providers.solana_observed import quote_ladder
        probe=quote_ladder([(25,25000000,26000000)],6)
        self.assertTrue(probe["samples"][0]["crossed_quote"])
        self.assertFalse(probe["trade_eligible"])
        self.assertFalse(probe["pilot_applied"])
