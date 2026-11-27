import unittest
from unittest.mock import patch
from cyberbot.integration_api import central_preflight, MARKETS

class CentralPreflightTests(unittest.TestCase):
    @patch("cyberbot.integration_api.dexterm_status",return_value={"status":"archive_available"})
    @patch("cyberbot.pilot_preflight.snapshot")
    def test_readiness_never_confuses_research_with_live_execution(self,preflight,dex):
        preflight.return_value={"real_orders":False,"network_probed":False,
            "python_supported":True,"dependencies":{"fastapi":"1","uvicorn":"1","httpx":"1"},
            "database_isolation":"checked","entry_halted":True,
            "markets":[{"market":"BIST","adapter_configured":True,"local_quote_validated":True,
                        "blockers":["same_engine_forward_test_missing","private"]},
                       {"market":"SOLANA","adapter_configured":True,"local_quote_validated":True,
                        "blockers":["legacy_solana_provider_removed"]}]}
        result=central_preflight()
        self.assertEqual(tuple(x["market"] for x in result["markets"]),MARKETS)
        self.assertTrue(result["checks"]["database_isolation_checked"])
        self.assertTrue(result["checks"]["entry_halted"])
        self.assertTrue(result["markets"][0]["local_quote_validated"])
        self.assertEqual(result["markets"][-1]["source"],"DexTerm")
        self.assertEqual(result["markets"][-1]["archive_status"],"archive_available")
        self.assertFalse(result["markets"][-1]["local_quote_validated"])
        self.assertNotIn("legacy_solana",str(result))
        self.assertNotIn("private",str(result))
        self.assertTrue(all(x["status"]=="blocked" for x in result["markets"]))
        self.assertFalse(result["automatic_entry_enabled"])
        self.assertFalse(result["tests_executed"])

    @patch("cyberbot.integration_api.dexterm_status",return_value={"status":"not_configured"})
    @patch("cyberbot.pilot_preflight.snapshot",side_effect=OSError)
    def test_failed_local_inspection_does_not_claim_readiness(self,preflight,dex):
        result=central_preflight()
        self.assertEqual(len(result["markets"]),5)
        self.assertEqual(result["checks"],{})
        self.assertTrue(all(not x["live_paper_verified"] for x in result["markets"]))
        self.assertIn("preflight_unavailable",result["markets"][0]["blockers"])
