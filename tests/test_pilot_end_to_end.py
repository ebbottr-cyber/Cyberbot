"""Five-market integration fixture. No network, live prices or production writes."""
import json,os,sqlite3,tempfile,unittest
from contextlib import closing
from datetime import datetime,timezone,timedelta
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch
from cyberbot import observed_pilot as stocks,solana_pilot as sol,futures_pilot as fut
from cyberbot.pilot_ingress import ingest,SCHEMA
from cyberbot.pilot_control import change,snapshot as control
from cyberbot.pilot_performance import snapshot as performance
from cyberbot.pilot_authorization import snapshot as authorization
from cyberbot.operations import backup
from cyberbot.recovery import recover

MARKETS=("BIST","NASDAQ","XETRA","SOLANA","FUTURES")

class PilotEndToEndTests(unittest.TestCase):
    def test_five_account_roundtrip_halt_recover(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);t=datetime(2026,1,2,12,tzinfo=timezone.utc)
            mint="1"*31+"2";pool="1"*31+"3"
            env={"CYBERBOT_DB":str(root/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(root/"learning.sqlite3"),"CYBERBOT_WORKER_DB":str(root/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(root/"pilot.sqlite3"),"CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":"","CYBERBOT_OBSERVED_PILOT_ENABLED":"1","CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED":"1","CYBERBOT_OBSERVED_FX_RIGHTS_CONFIRMED":"1","CYBERBOT_PILOT_INGRESS_ENABLED":"1","CYBERBOT_PILOT_SHADOW_ENABLED":"1","CYBERBOT_SOLANA_PILOT_ENABLED":"1","CYBERBOT_SOLANA_PILOT_MINT":mint,"CYBERBOT_SOLANA_PILOT_POOL":pool,"CYBERBOT_FUTURES_PILOT_ENABLED":"1","CYBERBOT_FUTURES_PILOT_SYMBOL":"BTCUSDT","CYBERBOT_PILOT_BACKUP_RIGHTS_CONFIRMED":"1","CYBERBOT_PILOT_KILL_SWITCH":"0","CYBERBOT_INGRESS_FX_SOURCE":"fixture_fx"}
            env.update({"CYBERBOT_INGRESS_SOURCE_"+m:"fixture" for m in MARKETS})
            def quote(m,*,closing_price=False,shallow=False):
                q={"market":m,"source":"fixture","source_at":t.isoformat(),"bid":"101" if closing_price else "100","ask":"101" if closing_price else "100"}
                if m in stocks.ACCOUNTS:
                    q.update(symbol=stocks.account(m)[0],currency=stocks.quote_currency(m),session_open=True,venue={"BIST":"XIST","NASDAQ":"XNAS","XETRA":"XETR"}[m],session_reference="fixture",bid_size=".001" if shallow else "100",ask_size="100")
                    if m=="XETRA":q["fx"]={"pair":"EUR/USD","source":"fixture_fx","source_at":t.isoformat(),"bid":"1.10","ask":"1.101"}
                elif m=="SOLANA":
                    q.update(mint=mint,pool=pool,currency="USD",bid="1.02" if closing_price else "1",ask="1.021" if closing_price else "1.001",liquidity_usd="200000",bid_depth_usd="0" if shallow else "500",ask_depth_usd="500")
                    q["security"]={"mint":mint,"pool":pool,"observed_at":t.isoformat(),"legacy_token_program":True,"mint_authority_disabled":True,"freeze_authority_disabled":True,"transfer_restrictions_absent":True,"top10_holder_pct":"20","evidence_id":"fixture"}
                else:
                    q.update(symbol="BTCUSDT",currency="USDT",contract="linear_perpetual",bid="99" if closing_price else "100",ask="99.1" if closing_price else "100.1",mark="99" if closing_price else "100",bid_depth_usdt="1000",ask_depth_usdt="0" if shallow else "1000",funding=[])
                return q
            def tick(m,**kw):
                return ingest({"schema":SCHEMA,"market":m,"quote":quote(m,**kw)},clock=lambda:t)
            def request(m,entry=True):
                if m in stocks.ACCOUNTS:return stocks.request(m,"buy" if entry else "sell",clock=lambda:t)
                if m=="SOLANA":return sol.request("buy" if entry else "sell",clock=lambda:t)
                return fut.request("SHORT" if entry else "CLOSE",clock=lambda:t)
            def report():return performance(clock=lambda:t)
            def rows():return {a["market"]:a for a in report()["markets"]}
            with patch.dict(os.environ,env):
                self.assertEqual(list(root.iterdir()),[])
                for m in MARKETS:
                    tick(m);request(m)
                self.assertEqual(set(change(True,clock=lambda:t)["cancelled_markets"]),set(MARKETS))
                self.assertTrue(control()["halted"])
                t+=timedelta(seconds=1)
                for m in MARKETS:
                    self.assertEqual(tick(m)["status"],"observation")
                    with self.assertRaises(stocks.PilotError):request(m)
                self.assertTrue(all(not a["position_open"] and a["pending"] is None for a in rows().values()))
                change(False,clock=lambda:t)
                for m in MARKETS:request(m)
                t+=timedelta(seconds=1)
                for m in MARKETS:
                    self.assertEqual(tick(m)["status"],"open_fill" if m=="FUTURES" else "buy_fill")
                self.assertTrue(all(a["position_open"] and D(a["cash"])>=0 for a in rows().values()))
                change(True,clock=lambda:t)
                for m in MARKETS:request(m,False)
                t+=timedelta(seconds=1)
                for m in MARKETS:self.assertEqual(tick(m,shallow=True)["status"],"exit_waiting_depth")
                self.assertTrue(all(a["equity"] is None for a in rows().values()))
                t+=timedelta(seconds=70)
                for m in MARKETS:self.assertEqual(tick(m,closing_price=True)["status"],"close_fill" if m=="FUTURES" else "sell_fill")
                final=report()
                self.assertIsNone(final["combined_equity"]);self.assertFalse(final["real_orders"]);self.assertFalse(final["live_data_verified"])
                for a in final["markets"]:
                    with self.subTest(market=a["market"]):
                        self.assertEqual(a["status"],"recorded");self.assertFalse(a["position_open"]);self.assertIsNone(a["pending"])
                        self.assertEqual(a["statistics"]["closed"],1);self.assertEqual(len(a["recent"]),2)
                        self.assertGreater(D(a["statistics"]["nominal_fees"]),0)
                        self.assertLessEqual(abs(D(a["cash"])-D(a["initial_capital"])-D(a["statistics"]["realized_pnl"])),D(".000002"))
                        self.assertFalse(a["risk_gate"])
                path=root/"pilot.sqlite3";before=path.read_bytes()
                self.assertFalse(authorization(clock=lambda:t)["automatic_entry_enabled"])
                restored=recover(backup(root/"backups"),root/"restore")
                self.assertEqual(path.read_bytes(),before)
                with patch.dict(os.environ,{"CYBERBOT_PILOT_DB":str(restored/"paper-observed-pilot.sqlite3")}):
                    self.assertEqual(report(),final);self.assertTrue(control()["halted"])
                self.assertEqual(report(),final)
                self.assertFalse((root/"paper.sqlite3").exists())
                t+=timedelta(seconds=31)
                self.assertTrue(all(a["equity"] is None and a["statistics"]["closed"]==1 for a in rows().values()))

    def test_accounting_not_capped_by_price_only_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);t=datetime(2026,1,2,12,tzinfo=timezone.utc)
            with patch.dict(os.environ,{"CYBERBOT_DB":str(root/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(root/"learning.sqlite3"),"CYBERBOT_WORKER_DB":str(root/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(root/"pilot.sqlite3"),"CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":"","CYBERBOT_OBSERVED_PILOT_ENABLED":"1","CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED":"1","CYBERBOT_PILOT_KILL_SWITCH":"0"}):
                q={"market":"BIST","symbol":"THYAO.IS","currency":"TRY","source":"fixture","source_at":t.isoformat(),"session_open":True,"bid":"100","ask":"100"}
                stocks.observe("BIST",q,clock=lambda:t);stocks.request("BIST","buy",clock=lambda:t)
                t+=timedelta(seconds=1);q["source_at"]=t.isoformat();stocks.observe("BIST",q,clock=lambda:t)
                stocks.request("BIST","sell",clock=lambda:t)
                t+=timedelta(seconds=1);q["source_at"]=t.isoformat();stocks.observe("BIST",q,clock=lambda:t)
                with stocks.tx() as db:
                    db.executemany("INSERT INTO observed_events(market,at,event,payload) VALUES('BIST',?,'observation',?)",[(t.isoformat(),json.dumps({"fixture_only":True}))]*5001)
                a=performance(clock=lambda:t)["markets"][0]
                self.assertGreater(a["event_count"],5000);self.assertEqual(a["accounting_event_count"],2)
                self.assertEqual(a["statistics"]["closed"],1)
