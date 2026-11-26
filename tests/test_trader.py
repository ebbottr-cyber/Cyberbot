import unittest
from cyberbot.providers.wallet import WalletFeed,WalletError
from cyberbot.trader import evaluate,demo,ResearchError

class TraderTests(unittest.TestCase):
    def test_wallet_cache_and_quota(self):
        calls=[]
        def transport(address,limit):
            calls.append(address)
            return [{"signature":"a"*88,"slot":1,"blockTime":None,"err":None}]
        f=WalletFeed(transport,lambda:10)
        addr="1"*32
        self.assertFalse(f.observe(addr)["swap_verified"])
        self.assertTrue(f.observe(addr)["cached"])
        self.assertEqual(len(calls),1)
        with self.assertRaises(WalletError): f.observe("2"*32)
        with self.assertRaises(WalletError): f.observe("bad")

    def test_demo_not_qualified(self):
        self.assertTrue(all(x["status"]=="yetersiz_ornek" for x in demo()))

    def test_cost_and_duplicate(self):
        r={"wallet":"demo","event":"1","signal_at":"2020-01-01T00:00:00Z","entry_at":"2020-01-01T00:01:00Z","exit_at":"2020-01-01T00:02:00Z","entry_price":"1","exit_price":"1","fee_bps":"30","slippage_bps":"75"}
        self.assertLess(float(evaluate([r])[0]["mean_net_pct"]),0)
        with self.assertRaises(ResearchError): evaluate([r,r])
        with self.assertRaises(ResearchError): evaluate([{**r,"entry_at":r["signal_at"]}])
        with self.assertRaises(ResearchError): evaluate([{**r,"entry_price":"NaN"}])
