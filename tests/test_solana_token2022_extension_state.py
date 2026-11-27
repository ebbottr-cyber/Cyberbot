import unittest
from tools.solana_token2022_extension_state import observe
from tools.solana_token2022_research import classify,TOKEN2022
from cyberbot.providers.solana_observed import mint_info,UnsupportedMint

M="1"*31+"2"
P="1"*31+"3"

class ExtensionStateTests(unittest.TestCase):
    def test_hook_and_delegate_are_observed_not_verified(self):
        d=observe({"extension":"transferHook","state":{"authority":None,"programId":P}})
        self.assertEqual(d["status"],"parsed_fields_observed")
        self.assertEqual(d["pointers"]["programId"]["address"],P)
        self.assertFalse(d["state_verified"])
        self.assertFalse(d["trade_eligible"])
        self.assertEqual(observe({"extension":"permanentDelegate","state":{}})["status"],"state_missing_or_invalid")
    def test_fee_schedules_never_assert_active_epoch(self):
        fee={"epoch":8,"maximumFee":2**64-1,"transferFeeBasisPoints":150}
        state={"transferFeeConfigAuthority":None,"withdrawWithheldAuthority":P,"withheldAmount":0,
               "olderTransferFee":fee,"newerTransferFee":fee}
        d=observe({"extension":"transferFeeConfig","state":state})
        self.assertEqual(d["fee_schedules"]["newerTransferFee"]["maximum_fee_raw"],str(2**64-1))
        self.assertFalse(d["active_fee_verified"])
        bad={**state,"newerTransferFee":{**fee,"transferFeeBasisPoints":10001}}
        self.assertEqual(observe({"extension":"transferFeeConfig","state":bad})["status"],"state_missing_or_invalid")
    def test_metadata_identity_and_no_untrusted_strings(self):
        d=observe({"extension":"tokenMetadata","state":{"updateAuthority":None,"mint":P,"uri":"arbitrary"}},mint=M)
        self.assertFalse(d["metadata_mint_matches"])
        self.assertNotIn("uri",str(d))
        self.assertEqual(d["status"],"state_missing_or_invalid")
    def test_classification_keeps_legacy_gate(self):
        raw={"jsonrpc":"2.0","id":1,"result":{"context":{"slot":10},"value":{"owner":TOKEN2022,"executable":False,
             "data":{"program":"spl-token-2022","parsed":{"type":"mint","info":{"isInitialized":True,
             "decimals":6,"supply":"100","mintAuthority":None,"freezeAuthority":None,
             "extensions":[{"extension":"transferHook","state":{"authority":None,"programId":P}}]}}}}}}
        d=classify(raw,mint=M)
        self.assertEqual(d["extension_state_observations"][0]["status"],"parsed_fields_observed")
        self.assertFalse(d["extension_state_verified"])
        self.assertFalse(d["trade_eligible"])
        with self.assertRaises(UnsupportedMint):mint_info(raw)
