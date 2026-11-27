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
            amount=p["amount"];out="100000000" if p["inputMint"]==USDC else "99000000"
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
                self.assertEqual(d["mint_checks"]["top10_token_account_pct"],"10")
                self.assertFalse(d["mint_checks"]["wallet_concentration_verified"])
                self.assertEqual(calls,["rpc","rpc","pool","quote","quote"])
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
            for name,url in (("official","https://api.mainnet-beta.solana.com"),("publicnode","https://solana-rpc.publicnode.com"),("rpcnode","https://public-solana-mainnet.rpcnode.dev")):
                with patch.dict(os.environ,{"CYBERBOT_SOLANA_RPC_PROVIDER":name}):
                    self.assertEqual(rpc_endpoint(),(name,url))
                    request(c,"rpc",("getAccountInfo",[]),"fixture")
                    self.assertEqual(seen[-1].rstrip("/"),url)
            with patch.dict(os.environ,{"CYBERBOT_SOLANA_RPC_PROVIDER":"https://example.invalid"}):
                with self.assertRaises(PilotError):request(c,"rpc",("getAccountInfo",[]),"fixture")
            with self.assertRaises(PilotError):request(c,"rpc",("getAccountInfo",[]),"fixture",rpc_url="https://example.invalid")
        self.assertEqual(len(seen),3)

    def test_public_holder_reports_are_diagnostic_only(self):
        from cyberbot.providers.solana_observed import reported_holders
        mint="1"*31+"2"
        rows=[{"address":"1"*31+c,"pct":"3"} for c in "3456789ABC"]
        rug={"mint":mint,"topHolders":rows,"totalHolders":100}
        gecko={"data":{"attributes":{"address":mint,"holders":{"count":90,
            "distribution_percentage":{"top_10":"35"},"last_updated":"2026-01-01T00:00:00Z"}}}}
        d=reported_holders(rug,gecko,mint)
        self.assertEqual(d["rugcheck_reported_top10_account_pct"],"30")
        self.assertEqual(d["reported_pct_difference"],"5")
        self.assertFalse(d["wallet_concentration_verified"])
        self.assertFalse(d["token_account_concentration_verified"])
        self.assertNotIn("top10_token_account_pct",d)
        with self.assertRaises(PilotError):
            reported_holders({**rug,"mint":"other"},gecko,mint)
        with self.assertRaises(PilotError):
            reported_holders({**rug,"topHolders":rows[:9]},gecko,mint)
        with self.assertRaises(PilotError):
            reported_holders({**rug,"topHolders":[rows[0]]*10},gecko,mint)
