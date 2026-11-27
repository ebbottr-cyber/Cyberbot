import unittest
from tools.solana_pool_discovery import candidates,gecko_rows,dex_rows,USDC
class DiscoveryTests(unittest.TestCase):
    def test_filter_and_deduplicate(self):
        mint="1"*31+"2";pool="1"*31+"3";other="1"*31+"4"
        rows=[(mint,USDC,pool,"150000","test","gecko"),(mint,USDC,pool,"120000","test","dex"),(mint,other,other,"900000","wrong quote","dex"),(mint,USDC,other,"99999","small","dex"),(mint,USDC,other,"NaN","bad","dex")]
        d=candidates(rows)
        self.assertEqual(len(d),1)
        self.assertEqual(d[0]["reported_liquidity_usd"],"120000")
        self.assertFalse(d[0]["security_verified"])
    def test_parsers(self):
        mint="1"*31+"2";pool="1"*31+"3"
        raw={"data":[{"id":"solana_"+pool,"attributes":{"reserve_in_usd":"200000","name":"test"},"relationships":{"base_token":{"data":{"id":"solana_"+mint}},"quote_token":{"data":{"id":"solana_"+USDC}}}}]}
        self.assertEqual(len(candidates(gecko_rows(raw))),1)
        raw={"pairs":[{"chainId":"solana","baseToken":{"address":mint},"quoteToken":{"address":USDC},"pairAddress":pool,"liquidity":{"usd":200000}}]}
        self.assertEqual(len(candidates(dex_rows(raw))),1)
