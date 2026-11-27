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

    def test_extended_budget_counts_completed_not_skips(self):
        rows=[candidate(str(i),"p") for i in range(6)]
        calls=[]
        def inspect(m,p):
            calls.append(m)
            return {"status":"diagnostic_unsupported_mint" if m in ("0","1") else "diagnostic_complete"}
        with patch.dict(os.environ,{"CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1"}):
            d=run(limit=2,max_candidates=5,discoverer=lambda:rows,inspect=inspect,sleep=lambda n:None)
            self.assertEqual(calls,["0","1","2","3"])
            self.assertTrue(d["target_reached"])
            self.assertEqual(d["status"],"scan_complete_with_skips")
            self.assertEqual(d["completed_mints"],2)
            with self.assertRaises(PilotError):run(limit=2,max_candidates=9,discoverer=lambda:self.fail("network"))
    def test_discovery_uses_bounded_sources_and_stops_on_rate_limit(self):
        import httpx
        from tools.solana_public_scan import discover
        from tools.solana_pool_discovery import QUERIES
        urls=[];waits=[]
        def fetch(c,url):
            urls.append(url)
            return {"data":[]} if "geckoterminal" in url else {"pairs":[]}
        with patch("tools.solana_public_scan.fetch",side_effect=fetch):
            self.assertEqual(discover(sleep=waits.append),[])
        self.assertEqual(len(urls),2+len(QUERIES))
        self.assertEqual(waits,[2]*(len(urls)-1))
        error=httpx.HTTPStatusError("rate",request=httpx.Request("GET","https://example.invalid"),response=httpx.Response(429))
        with patch("tools.solana_public_scan.fetch",side_effect=error) as mocked:
            with self.assertRaisesRegex(PilotError,"HTTP 429"):discover(sleep=lambda n:self.fail("continued"))
            mocked.assert_called_once()

    def test_single_sell_400_skips_distinct_candidate_but_second_stops(self):
        rows=[candidate(str(i),"p") for i in range(4)]
        calls=[]
        def inspect(m,p):
            calls.append(m)
            return {"status":"diagnostic_sell_quote_rejected" if m=="0" else "diagnostic_complete"}
        with patch.dict(os.environ,{"CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1"}):
            d=run(limit=2,max_candidates=4,discoverer=lambda:rows,inspect=inspect,sleep=lambda n:None)
            self.assertEqual(calls,["0","1","2"])
            self.assertEqual(d["status"],"scan_complete_with_skips")
            self.assertEqual(d["sell_quote_rejected_mints"],1)
            self.assertTrue(d["target_reached"])
            calls.clear()
            def rejected(m,p):
                calls.append(m);return {"status":"diagnostic_sell_quote_rejected"}
            d=run(limit=2,max_candidates=4,discoverer=lambda:rows,inspect=rejected,sleep=lambda n:None)
            self.assertEqual(calls,["0","1"])
            self.assertEqual(d["status"],"scan_partial")
            self.assertEqual(d["stop_reason"],"repeated_sell_quote_http_400")
            self.assertFalse(d["security_verified"])
            self.assertFalse(d["pilot_applied"])

    def test_only_sell_http_400_has_special_classification(self):
        import httpx
        from cyberbot.providers.solana_observed import request,USDC,SellQuoteRejected
        mint="1"*31+"2"
        for status in (400,429,503):
            with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(status,text="private"))) as c:
                for inp,out in ((mint,USDC),(USDC,mint)):
                    with self.assertRaises(PilotError) as ctx:
                        request(c,"quote",{"inputMint":inp,"outputMint":out,"amount":"1"},"")
                    self.assertEqual(isinstance(ctx.exception,SellQuoteRejected),status==400 and inp==mint)
                    self.assertNotIn("private",str(ctx.exception))

    def test_known_symbol_collision_skipped_before_network(self):
        from tools.solana_public_scan import REFERENCE_MINTS
        wrong={"mint":"6RLhPtPZGED9sdiwCKzhug6rej2tsL69rcPh4JHKK7cY","pool":"p","label":"POPCAT / USDC"}
        right={"mint":REFERENCE_MINTS["POPCAT"],"pool":"q","label":"Popcat"}
        unknown={"mint":"x","pool":"r","label":"OTHER"}
        calls=[]
        def inspect(m,p):
            calls.append(m);return {"status":"diagnostic_complete"}
        with patch.dict(os.environ,{"CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1"}):
            d=run(discoverer=lambda:[wrong,right,unknown],inspect=inspect,sleep=lambda n:None)
        self.assertEqual(calls,[right["mint"],"x"])
        self.assertEqual(d["identity_conflict_count"],1)
        self.assertEqual(d["identity_conflicts"][0]["mint"],wrong["mint"])
        self.assertFalse(d["token_identity_verified"])
        self.assertFalse(d["security_verified"])

    def test_reference_first_keeps_unknown_diagnostics_separate(self):
        from tools.solana_public_scan import REFERENCE_MINTS
        refs=list(REFERENCE_MINTS.values())
        rows=[candidate("unknown1","p"),candidate(refs[0],"q"),candidate("unknown2","r"),candidate(refs[1],"s")]
        calls=[]
        def inspect(m,p):
            calls.append(m)
            return {"status":"diagnostic_complete" if m in refs else "diagnostic_sell_quote_rejected"}
        with patch.dict(os.environ,{"CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1"}):
            d=run(limit=3,max_candidates=4,reference_first=True,discoverer=lambda:rows,inspect=inspect,sleep=lambda n:None)
        self.assertEqual(calls,refs+["unknown1","unknown2"])
        self.assertEqual(d["reference_completed_mints"],2)
        self.assertEqual(d["nonreference_completed_mints"],0)
        self.assertEqual(d["stop_reason"],"repeated_sell_quote_http_400")
        self.assertFalse(d["target_reached"])
        self.assertFalse(d["security_verified"])
        self.assertFalse(d["pilot_applied"])

    def test_discovery_retains_reference_outside_general_cap(self):
        from tools.solana_public_scan import discover,REFERENCE_MINTS
        mint=REFERENCE_MINTS["BONK"]
        from cyberbot.solana_pilot import address,ALPHABET
        def addr(i):
            # 31 leading zero bytes plus one nonzero byte; valid 32-byte base58 fixtures.
            value="1"*31+ALPHABET[i+1]
            self.assertTrue(address(value),value)
            return value
        from cyberbot.providers.solana_observed import USDC
        pairs=[{"chainId":"solana","baseToken":{"address":addr(i),"symbol":"X"},
                "quoteToken":{"address":USDC},"pairAddress":addr(i+25),"liquidity":{"usd":200000}}
               for i in range(21)]
        pairs.append({"chainId":"solana","baseToken":{"address":mint,"symbol":"BONK"},
                      "quoteToken":{"address":USDC},"pairAddress":addr(50),"liquidity":{"usd":100001}})
        with patch("tools.solana_public_scan.fetch",side_effect=lambda c,u:{"data":[]} if "geckoterminal" in u else {"pairs":pairs}):
            d=discover(sleep=lambda n:None)
        self.assertEqual(len(d),21)
        self.assertTrue(any(r["mint"]==mint for r in d))

    def test_temporary_exclusions_do_not_hide_reference_or_bypass_stop(self):
        from tools.solana_public_scan import REFERENCE_MINTS
        dos="4QenztDMzbG4vhCGayZpLD9WVoUtbDgFVEq29vETtx8B"
        iost="8ZFVUDYarzS4sUpDgnqAARtKzKQWifFzFHxPE2BZoQbF"
        rows=[candidate(dos,"p"),candidate(iost,"q"),candidate("new1","r"),candidate("new2","s"),candidate("new3","t")]
        calls=[]
        def inspect(m,p):
            calls.append(m);return {"status":"diagnostic_sell_quote_rejected"}
        with patch.dict(os.environ,{"CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1"}):
            d=run(limit=2,max_candidates=5,exclude_mints=[dos,iost],discoverer=lambda:rows,inspect=inspect,sleep=lambda n:None)
            self.assertEqual(calls,["new1","new2"])
            self.assertEqual(set(d["excluded_mints_found"]),{dos,iost})
            self.assertEqual(d["stop_reason"],"repeated_sell_quote_http_400")
            self.assertFalse(d["target_reached"])
            with self.assertRaises(PilotError):
                run(exclude_mints=[REFERENCE_MINTS["BONK"]],discoverer=lambda:self.fail("network"))
            with self.assertRaises(PilotError):
                run(exclude_mints=["bad"],discoverer=lambda:self.fail("network"))
        self.assertFalse(d["pilot_applied"])
