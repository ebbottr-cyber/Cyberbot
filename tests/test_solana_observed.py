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
