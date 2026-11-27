import os,unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
from tools.dexterm_research_cycle import run,cycle,priority,unsupported_only
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

    def test_only_exhausted_unsupported_mints_are_continuable(self):
        s={"status":"scan_no_supported_candidates","stop_reason":None,"target_reached":False,
           "completed_mints":0,"unsupported_mints":1,"inspected_mints":1,"selected_mints":1,
           "reports":[{"diagnostic":{"status":"diagnostic_unsupported_mint"}}]}
        d={"status":"diagnostic_partial","scan":s}
        self.assertTrue(unsupported_only(d))
        for change in ({"stop_reason":"diagnostic_failure"},{"selected_mints":2},{"status":"scan_partial"},
                       {"reports":[{"diagnostic":{"status":"diagnostic_sell_quote_rejected"}}]}):
            self.assertFalse(unsupported_only({"status":"diagnostic_partial","scan":{**s,**change}}))
    def test_unsupported_cycle_can_continue_but_never_counts_as_diagnostic(self):
        states=iter([{"status":"cycle_no_supported_candidates","completed_mints":0,"unsupported_mints":3},
                     {"status":"cycle_complete","completed_mints":1}])
        waits=[]
        with patch.dict(os.environ,ENV):
            r=run("x","y","z",cycles=2,cycle_fn=lambda *a:next(states),sleep=waits.append)
        self.assertEqual(waits,[180])
        self.assertEqual(r["status"],"research_run_complete")
        self.assertEqual(r["successful_diagnostics"],1)
        self.assertEqual(r["unsupported_mint_observations"],3)
        self.assertEqual(r["unsupported_only_cycles"],1)
        self.assertFalse(r["security_verified"])
    def test_policy_exhaustion_is_not_provider_failure(self):
        from tools.dexterm_research_cycle import authority_exhausted
        s={"status":"scan_no_policy_candidates","stop_reason":None,"target_reached":False,
           "completed_mints":0,"authority_excluded_mints":1,"inspected_mints":2,"selected_mints":2,
           "reports":[{"diagnostic":{"status":"diagnostic_authority_policy_excluded"}},
                      {"diagnostic":{"status":"diagnostic_unsupported_mint"}}]}
        self.assertTrue(authority_exhausted({"status":"diagnostic_partial","scan":s}))
        self.assertFalse(authority_exhausted({"status":"diagnostic_partial","scan":{**s,"stop_reason":"diagnostic_failure"}}))
