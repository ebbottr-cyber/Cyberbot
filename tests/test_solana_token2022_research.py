import os,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tools.solana_token2022_research import classify,run,archived_mints,TOKEN2022
from tools.dexterm_research_archive import archive
from cyberbot.providers.solana_observed import mint_info,UnsupportedMint

M="1"*31+"2"
P="1"*31+"3"
N="1"*31+"4"
FLAGS={"security_verified":False,"live_data_verified":False,"pilot_applied":False,"real_orders":False}
ENV={"CYBERBOT_PILOT_KILL_SWITCH":"1","CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"1"}
def raw(extensions=None,owner=TOKEN2022):
    info={"decimals":6,"supply":"1000000","isInitialized":True,"mintAuthority":None,"freezeAuthority":None}
    if extensions is not None:info["extensions"]=extensions
    return {"jsonrpc":"2.0","id":1,"result":{"context":{"slot":100},"value":{"owner":owner,"executable":False,
            "data":{"program":"spl-token-2022","parsed":{"type":"mint","info":info}}}}}

class Token2022ResearchTests(unittest.TestCase):
    def test_extensions_are_observations_only(self):
        r=raw([{"extension":"transferHook","state":{}},{"extension":"permanentDelegate"},{"extension":"futureExtension"}])
        d=classify(r)
        self.assertEqual(d["status"],"token2022_observed")
        self.assertEqual(d["reported_extensions"],["permanentDelegate","transferHook"])
        self.assertEqual(d["unknown_extension_count"],1)
        self.assertFalse(d["extensions_verified"])
        self.assertFalse(d["trade_eligible"])
        with self.assertRaises(UnsupportedMint):mint_info(r)
    def test_missing_extensions_not_clearance(self):
        d=classify(raw())
        self.assertFalse(d["extension_list_reported"])
        self.assertIsNone(d["unknown_extension_count"])
        self.assertFalse(d["trade_eligible"])
        self.assertEqual(classify(raw(owner=N))["status"],"other_program")
        with self.assertRaises(ValueError):classify(raw([{"extension":123}]))
    def test_archive_selection_and_provider_failure(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,ENV):
            p=Path(folder);f=p/"report.json";db=p/"archive.sqlite3"
            f.write_text(json.dumps({"source":"dexterm_historical_shortlist_exact_mint_lookup","status":"diagnostic_partial",
                "lookups":[],"scan":{"reports":[{"candidate":{"mint":m,"pool":P},"diagnostic":{"status":"diagnostic_unsupported_mint"}} for m in (M,N)],**FLAGS},**FLAGS}))
            archive(db,[f])
            self.assertEqual(archived_mints(db,3),[M,N])
            def fail(*a,**k):raise ValueError("provider")
            d=run(db,request_fn=fail,sleep=lambda n:self.fail("continued"))
            self.assertEqual(d["status"],"research_partial")
            self.assertEqual(len(d["observations"]),1)
            self.assertFalse(d["real_orders"])
