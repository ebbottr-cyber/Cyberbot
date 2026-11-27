import json,tempfile,unittest
from pathlib import Path
from tools.solana_token2022_risk_review import review
from tools.solana_token2022_research import TOKEN2022
from tools.dexterm_research_archive import archive

M="1"*31+"2"
FLAGS={"security_verified":False,"live_data_verified":False,"pilot_applied":False,"real_orders":False}
def report(names,**kw):
    row={"mint":M,"status":"token2022_observed","program_owner":TOKEN2022,
         "extensions_verified":False,"trade_eligible":False,"mint_authority":"disabled",
         "freeze_authority":"disabled","extension_list_reported":True,
         "reported_extensions":names,"unknown_extension_count":0,**kw}
    return {"status":"research_complete","research_only":True,"extensions_verified":False,
            "selected_mints":1,"token2022_count":1,"observations":[row],**FLAGS}

class Token2022RiskReviewTests(unittest.TestCase):
    def test_hook_not_clearance(self):
        d=review(report(["transferHook"]))
        self.assertEqual(d["additional_controls_count"],1)
        self.assertIn("transfer_control:transferHook",d["observations"][0]["reasons"])
        self.assertFalse(d["trade_eligible"])
    def test_metadata_only_still_not_clearance(self):
        d=review(report(["metadataPointer","tokenMetadata"]))
        self.assertEqual(d["metadata_or_empty_count"],1)
        self.assertFalse(d["extensions_verified"])
        self.assertFalse(d["observations"][0]["trade_eligible"])
    def test_unknown_missing_authority_and_list(self):
        self.assertEqual(review(report([],unknown_extension_count=1))["additional_controls_count"],1)
        self.assertEqual(review(report([],mint_authority="present"))["additional_controls_count"],1)
        self.assertEqual(review(report([],extension_list_reported=False,unknown_extension_count=None))["additional_controls_count"],1)
        with self.assertRaises(ValueError):review(report([],unknown_extension_count=-1))
    def test_archive_both_reports(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);a=p/"observed.json";b=p/"review.json";db=p/"research.sqlite3"
            r=report(["metadataPointer"])
            a.write_text(json.dumps(r));b.write_text(json.dumps(review(r)))
            d=archive(db,[a,b])
            self.assertEqual(d["observation_counts"],{"token2022":1,"token2022_review":1})
            self.assertEqual(archive(db,[a,b])["duplicate_reports"],2)
