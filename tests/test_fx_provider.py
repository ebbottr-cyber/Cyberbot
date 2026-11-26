import json,os,tempfile,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
from cyberbot.fx_provider import refresh,parse,FXError
from cyberbot.capital import fx_quote,usd_total

class FXTests(unittest.TestCase):
    def test_refresh_and_quota(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);q=root/"fx.json";quota=root/"quota.sqlite3"
            now=datetime(2026,11,26,18,tzinfo=timezone.utc)
            calls=[]
            def transport(pair):
                calls.append(pair)
                return {"symbol":pair,"rate":"45" if pair=="USD/TRY" else ".99","timestamp":int(now.timestamp())}
            with patch.dict(os.environ,{"CYBERBOT_FX_PROVIDER_ENABLED":"1","CYBERBOT_FX_RIGHTS_CONFIRMED":"1","CYBERBOT_TWELVEDATA_KEY":"fixture"}),patch("cyberbot.fx_provider.paths",return_value=(q,quota)):
                self.assertEqual(refresh(transport=transport,clock=lambda:now)["status"],"updated")
                self.assertEqual(len(calls),2)
                with self.assertRaises(FXError):refresh(transport=transport,clock=lambda:now)
                self.assertEqual(len(calls),2)
                data=fx_quote(q,now)
                self.assertEqual(data["usdtusd"],"0.99")
                self.assertEqual(usd_total([{"currency":"TRY","equity":"45000"},{"currency":"USDT","equity":"1000"}],data),"1990.00")
                before=q.read_bytes()
                with self.assertRaises(FXError):refresh(transport=lambda pair:{"symbol":pair,"rate":1,"timestamp":0},clock=lambda:now+timedelta(seconds=240))
                self.assertEqual(q.read_bytes(),before)
    def test_independent_ages(self):
        with tempfile.TemporaryDirectory() as tmp:
            q=Path(tmp)/"fx.json";now=datetime.now(timezone.utc)
            q.write_text(json.dumps({"usdtry":"45","usdtusd":"1","observed_at":now.isoformat(),"usdtry_observed_at":now.isoformat(),"usdtusd_observed_at":(now-timedelta(seconds=301)).isoformat(),"source":"fixture"}))
            data=fx_quote(q,now)
            self.assertEqual(data["status"],"fresh_input")
            self.assertEqual(data["usdtusd_status"],"stale")
            self.assertIsNone(usd_total([{"currency":"USDT","equity":"1000"}],data))
            self.assertEqual(usd_total([{"currency":"TRY","equity":"45000"}],data),"1000.00")
    def test_disabled(self):
        with patch.dict(os.environ,{"CYBERBOT_FX_PROVIDER_ENABLED":"0"}):
            with self.assertRaises(FXError):refresh(transport=lambda p:self.fail("network"))
    def test_wrong_pair(self):
        now=datetime.now(timezone.utc)
        with self.assertRaises(FXError):parse({"symbol":"USDT/TRY","rate":45,"timestamp":int(now.timestamp())},"USD/TRY",now)
