"""Offline synthetic CPMM pool/vault fixtures; no RPC or execution."""
import base64
import hashlib
import unittest
from copy import deepcopy
from cyberbot.providers.solana_observed import CPMM,LEGACY,USDC,cpmm_state,pool_probe,PilotError
from cyberbot.solana_pilot import ALPHABET

def key(n):return "1"*31+ALPHABET[n]
def decode(address):
    n=0
    for c in address:n=n*58+ALPHABET.index(c)
    return n.to_bytes(32,"big")
def rpc(value,slot=100):
    return {"jsonrpc":"2.0","id":1,"result":{"context":{"slot":slot},"value":value}}
MINT=key(1);POOL=key(2);LP=key(3);AUTH=key(4)
VAULTS=[key(5),key(6)]
INFO={"slot":100,"decimals":6,"supply":1000000000}
def state():
    data=bytearray(637)
    data[:8]=hashlib.sha256(b"account:PoolState").digest()[:8]
    keys=[key(7),key(8),*VAULTS,LP,MINT,USDC,LEGACY,LEGACY,key(9)]
    for i,address in enumerate(keys):data[8+32*i:40+32*i]=decode(address)
    data[330:333]=bytes([9,6,6])
    data[333:341]=(1000).to_bytes(8,"little")
    return rpc({"owner":CPMM,"executable":False,"data":[base64.b64encode(data).decode(),"base64"]})
def token(kind,info):
    return {"owner":LEGACY,"executable":False,"data":{"program":"spl-token","parsed":{"type":kind,"info":info}}}
def vault(mint,amount):
    return token("account",{"mint":mint,"owner":AUTH,"state":"initialized",
                            "tokenAmount":{"amount":str(amount),"decimals":6}})
def rows():
    return [vault(MINT,100000000),vault(USDC,500000000),
            token("mint",{"decimals":9,"supply":"1000","isInitialized":True,
                          "mintAuthority":AUTH,"freezeAuthority":None})]

class CPMMProbeTests(unittest.TestCase):
    def test_state_and_program(self):
        result=cpmm_state(state(),MINT,POOL,INFO)
        self.assertEqual(result["vaults"],VAULTS)
        self.assertEqual(result["lp_mint"],LP)
        raw=state();raw["result"]["value"]["owner"]=LEGACY
        self.assertIsNone(cpmm_state(raw,MINT,POOL,INFO))
        with self.assertRaises(PilotError):cpmm_state(state(),key(10),POOL,INFO)
        raw=state();raw["result"]["value"]["data"]=["AAAA","base64"]
        with self.assertRaises(PilotError):cpmm_state(raw,MINT,POOL,INFO)

    def test_vault_and_lp_sample(self):
        calls=[]
        def get(kind,params):
            method,args=params;calls.append(method)
            if method=="getAccountInfo":return state()
            if method=="getMultipleAccounts":
                self.assertEqual(args[0],VAULTS+[LP])
                return rpc(rows())
            self.assertEqual(args[0],LP)
            return rpc([{"address":key(11),"amount":"400","decimals":9}])
        result=pool_probe(get,MINT,POOL,INFO)
        self.assertEqual(calls,["getAccountInfo","getMultipleAccounts","getTokenLargestAccounts"])
        self.assertEqual(result["usdc_vault_balance"],"500")
        self.assertIn("lp_account_concentration_above_30pct",result["risk_flags"])
        for flag in ("lp_lock_verified","lp_burn_verified","vault_pda_verified",
                     "security_verified","depth_verified","trade_eligible","real_orders",
                     "rug_pull_risk_resolved"):
            self.assertIs(result[flag],False)

    def test_mismatched_vault_rejected(self):
        bad=rows();bad[0]["data"]["parsed"]["info"]["mint"]=USDC
        def get(kind,params):
            if params[0]=="getAccountInfo":return state()
            return rpc(bad)
        with self.assertRaises(PilotError):pool_probe(get,MINT,POOL,INFO)

    def test_unsupported_program_no_followup(self):
        raw=state();raw["result"]["value"]["owner"]=LEGACY
        calls=[]
        def get(kind,params):
            calls.append(params[0]);return raw
        result=pool_probe(get,MINT,POOL,INFO)
        self.assertEqual(calls,["getAccountInfo"])
        self.assertEqual(result["status"],"unsupported_pool_program")
        self.assertFalse(result["trade_eligible"])
