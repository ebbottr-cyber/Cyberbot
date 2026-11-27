import os
import unittest
from unittest.mock import patch

from tools.dexterm_readonly_probe import normalize, isolated_env, probe

MINT = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"

class DexTermReadOnlyTests(unittest.TestCase):
    def test_bounded_numeric_candidates_only(self):
        row = {"mint": MINT, "priceUsd": 0.01, "liquidityUsd": 100000,
               "symbol":"untrusted", "audit":{"top10Pct":0}, "holderCount":float("nan")}
        d = normalize({"rows":[row,row,{"mint":"bad"}], "errors":[]})
        self.assertEqual(d["candidate_count"],1)
        self.assertEqual(d["candidates"][0]["reported"],{"priceUsd":0.01,"liquidityUsd":100000})
        for k in ("security_verified","live_data_verified","pilot_applied","real_orders"):
            self.assertFalse(d[k])
    def test_partial_and_invalid_payloads(self):
        self.assertEqual(normalize({"rows":[]})["status"],"diagnostic_partial")
        self.assertEqual(normalize({"rows":[{"mint":MINT}],"errors":["missing"]})["status"],"diagnostic_partial")
        with self.assertRaises(ValueError): normalize({"rows":[{}]*11})
        with self.assertRaises(ValueError): normalize({"error":"failure"})
    def test_no_credentials_or_unapproved_live(self):
        with patch.dict(os.environ, {"CYBERBOT_PILOT_KILL_SWITCH":"1",
                         "CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED":"0",
                         "HELIUS_API_KEY":"test","DEXTERM_ACTION_TOKEN":"test"}):
            env = isolated_env("isolated")
            self.assertNotIn("HELIUS_API_KEY",env)
            self.assertNotIn("DEXTERM_ACTION_TOKEN",env)
            self.assertEqual(env["DEXTERM_DB_PATH"],":memory:")
            with self.assertRaises(ValueError): probe("unused",True)
        with patch.dict(os.environ,{"CYBERBOT_PILOT_KILL_SWITCH":"0"}):
            with self.assertRaises(ValueError): probe("unused")
