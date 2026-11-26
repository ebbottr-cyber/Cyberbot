import os,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from cyberbot.solana_pilot import observe,request,snapshot,address,PilotError
class SolanaPilotTests(unittest.TestCase):
    def test_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);t=datetime(2026,1,1,tzinfo=timezone.utc)
            # Valid-length base58 fixture identities, not real asset recommendations.
            mint="1"*31+"2";pool="1"*31+"3"
            self.assertTrue(address(mint));self.assertFalse(address("1"*32))
            env={"CYBERBOT_DB":str(p/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(p/"learning.sqlite3"),"CYBERBOT_WORKER_DB":str(p/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(p/"pilot.sqlite3"),"CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":"","CYBERBOT_OBSERVED_PILOT_ENABLED":"1","CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED":"1","CYBERBOT_SOLANA_PILOT_ENABLED":"1","CYBERBOT_SOLANA_PILOT_MINT":mint,"CYBERBOT_SOLANA_PILOT_POOL":pool}
            def quote(at,*,safe=True,depth="500",bid="1",ask="1.001"):
                q={"market":"SOLANA","mint":mint,"pool":pool,"currency":"USD","source":"fixture","source_at":at.isoformat(),"bid":bid,"ask":ask,"liquidity_usd":"200000","bid_depth_usd":depth,"ask_depth_usd":"500"}
                if safe:q["security"]={"mint":mint,"pool":pool,"observed_at":at.isoformat(),"legacy_token_program":True,"mint_authority_disabled":True,"freeze_authority_disabled":True,"transfer_restrictions_absent":True,"top10_holder_pct":"20","evidence_id":"fixture"}
                return q
            with patch.dict(os.environ,env):
                self.assertFalse(snapshot(clock=lambda:t)["initialized"]);self.assertEqual(list(p.iterdir()),[])
                observe(quote(t,safe=False),clock=lambda:t)
                with self.assertRaises(PilotError):request("buy",clock=lambda:t)
                t+=timedelta(seconds=1);observe(quote(t),clock=lambda:t);request("buy",clock=lambda:t)
                with self.assertRaises(PilotError):observe(quote(t),clock=lambda:t)
                t+=timedelta(seconds=1);self.assertEqual(observe(quote(t),clock=lambda:t)["status"],"buy_fill")
                self.assertTrue(snapshot(clock=lambda:t)["position_open"])
                t+=timedelta(seconds=1);d=observe(quote(t,safe=False,depth="0"),clock=lambda:t)
                self.assertEqual(d["pending"]["reason"],"security_or_liquidity")
                t+=timedelta(seconds=1);self.assertEqual(observe(quote(t,safe=False,depth="0"),clock=lambda:t)["status"],"exit_waiting_depth")
                self.assertIsNone(snapshot(clock=lambda:t)["equity"])
                t+=timedelta(seconds=70);self.assertEqual(observe(quote(t,safe=False),clock=lambda:t)["status"],"sell_fill")
                self.assertFalse(snapshot(clock=lambda:t)["position_open"])
                self.assertFalse(snapshot(clock=lambda:t)["security_verified"])
                self.assertIsNone(snapshot(clock=lambda:t+timedelta(seconds=31))["equity"])
                with patch.dict(os.environ,{"CYBERBOT_SOLANA_PILOT_ENABLED":"0"}):
                    with self.assertRaises(PilotError):observe(quote(t),clock=lambda:t)
                self.assertEqual(list(p.iterdir()),[p/"pilot.sqlite3"])
