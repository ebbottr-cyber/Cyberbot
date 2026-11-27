import json,tempfile,unittest
from pathlib import Path
from copy import deepcopy
from tools.solana_paper_replay import replay,observation,fee
from tools.solana_route_preview import inspect,USDC
from tools.dexterm_research_archive import archive

M="1"*31+"2"
P="1"*31+"3"
FLAGS={"security_verified":False,"live_data_verified":False,"pilot_applied":False,"real_orders":False}
STAMP="2026-01-01T00:00:00+00:00"

def route(a,b,n,out):
    return inspect({"inputMint":a,"outputMint":b,"swapMode":"ExactIn","inAmount":str(n),"outAmount":str(out),
        "routePlan":[{"bps":10000,"swapInfo":{"ammKey":P,"inputMint":a,"outputMint":b,"inAmount":str(n),"outAmount":str(out)}}]},a,b,n)

def item():
    q={"status":"route_preview_only","mint":M,"retrieved_at":STAMP,
       "buy":route(USDC,M,100000000,200000),"sell":route(M,USDC,200000,99000000),
       "test_input_usdc":"100","reported_roundtrip_return_usdc":"99",
       "route_integrity_verified":False,"depth_verified":False,"quote_source_timestamp_verified":False,"transport_mocked":False,**FLAGS}
    d={"status":"diagnostic_complete","mint":M,"reference_pool":P,"retrieved_at":STAMP,"stages":{
       "mint":{"status":"ok","data":{"mint_authority_disabled":True,"freeze_authority_disabled":True}},
       "holders":{"status":"ok"},"reference_pool":{"status":"ok"},"route_preview":{"status":"ok","data":q}},**FLAGS}
    return {"candidate":{"mint":M,"pool":P},"diagnostic":d}

def bridge(x,tag):
    return {"source":"dexterm_historical_shortlist_exact_mint_lookup","status":"diagnostic_complete","lookups":[],
            "scan":{"reports":[x],**FLAGS},"tag":tag,**FLAGS}

class PaperReplayTests(unittest.TestCase):
    def test_archive_replay_stress_and_dedup(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);a=p/"a.json";b=p/"b.json";db=p/"r.sqlite3"
            a.write_text(json.dumps(bridge(item(),"one")));b.write_text(json.dumps(bridge(item(),"two")))
            archive(db,[a,b])
            before=db.read_bytes()
            d=replay(db)
            self.assertEqual(d["scenarios_replayed"],1)
            self.assertEqual(d["duplicate_quotes"],1)
            self.assertEqual(d["reported_net_raw"],-1000000)
            self.assertEqual(d["extra_cost_total_raw"],497500)
            self.assertEqual(d["final_balance_raw"],998502500)
            self.assertEqual(d["max_balance_drawdown_raw"],1497500)
            self.assertFalse(d["profitability_verified"])
            self.assertFalse(d["real_orders"])
            self.assertEqual(before,db.read_bytes())
    def test_reject_amount_authority_and_mocked_quotes(self):
        for key,val in (("transport_mocked",True),("reported_roundtrip_return_usdc","98")):
            x=item();x["diagnostic"]["stages"]["route_preview"]["data"][key]=val
            with self.assertRaises(ValueError):observation(x)
        x=item();x["diagnostic"]["stages"]["mint"]["data"]["mint_authority_disabled"]=False
        with self.assertRaises(ValueError):observation(x)
    def test_recompute_route_accounting(self):
        x=item();x["diagnostic"]["stages"]["route_preview"]["data"]["buy"]["legs"][0]["input_raw"]="99999999"
        with self.assertRaises(ValueError):observation(x)
    def test_no_fill_when_capital_insufficient(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);f=p/"a.json";db=p/"r.sqlite3"
            f.write_text(json.dumps(bridge(item(),"one")));archive(db,[f])
            d=replay(db,initial_usdc=100)
            self.assertEqual(d["status"],"no_usable_quotes")
            self.assertEqual(d["insufficient_capital_scenarios"],1)
            self.assertEqual(d["final_balance_raw"],100000000)
    def test_integer_fee_rounds_up(self):
        self.assertEqual(fee(1,1),1)
        self.assertEqual(fee(1,0),0)
