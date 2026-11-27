import os,unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
from tools.dexterm_research_cycle import run,cycle,priority
from tools.dexterm_research_archive import archive
from cyberbot.solana_pilot import ALPHABET
M="1"*31+ALPHABET[1]
N="1"*31+ALPHABET[2]
FLAGS={"security_verified":False,"live_data_verified":False,"pilot_applied":False,"real_orders":False}
ENV={"CYBERBOT_PILOT_KILL_SWITCH":"1","CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1"}

class DexTermCycleTests(unittest.TestCase):
    def test_rotation_prefers_unqueried(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);f=p/"r.json";db=p/"r.sqlite3"
            f.write_text(json.dumps({"source":"dexterm_historical_shortlist_exact_mint_lookup","status":"no_eligible_pools",
                "lookups":[{"mint":M,"status":"no_eligible_direct_usdc_pool","pool":None}],"scan":None,**FLAGS}))
            archive(db,[f])
            self.assertEqual(priority(db,[M,N]),[N,M])
    def test_partial_screener_archived_without_bridge(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,ENV):
            p=Path(d);db=p/"r.sqlite3"
            raw={"source":"dexterm_screener_query","status":"diagnostic_partial","candidate_count":0,"candidates":[],**FLAGS}
            r=cycle("unused",db,p,probe_fn=lambda *a:raw,bridge_fn=lambda *a,**k:self.fail("bridge"))
            self.assertEqual(r["status"],"cycle_partial")
            self.assertEqual(r["archive"]["total_reports"],1)
    def test_loop_stops_on_partial(self):
        calls=[]
        def step(*args):
            calls.append(1)
            return {"status":"cycle_partial"}
        with patch.dict(os.environ,ENV):
            r=run("x","y","z",cycles=3,cycle_fn=step,sleep=lambda n:self.fail("retry"))
        self.assertEqual(len(calls),1)
        self.assertEqual(r["status"],"research_run_partial")
    def test_bounded_cycle_and_permission(self):
        with patch.dict(os.environ,ENV):
            with self.assertRaises(ValueError):run("x","y","z",cycles=4)
        with patch.dict(os.environ,{"CYBERBOT_PILOT_KILL_SWITCH":"0"}):
            with self.assertRaises(ValueError):run("x","y","z")
