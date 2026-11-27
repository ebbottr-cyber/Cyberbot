"""Actual SQLite-to-panel offline integration with synthetic research observations."""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
import httpx
from tools.dexterm_research_archive import archive
from tools.solana_paper_replay import collect,FALSE_FLAGS
from tools.solana_route_preview import inspect,USDC
from tools.solana_exit_history import collect_exits
from tools.solana_paper_positions import replay
from tools.solana_learning_cycle import run
from tools.solana_pwa_publish import publish,read

M="1"*31+"2"
P="1"*31+"3"
BASE=datetime(2026,1,1,tzinfo=timezone.utc)
def stamp(s):return (BASE+timedelta(seconds=s)).isoformat()
def route(a,b,n,out):
    return inspect({"inputMint":a,"outputMint":b,"swapMode":"ExactIn","inAmount":str(n),"outAmount":str(out),
                    "routePlan":[{"bps":10000,"swapInfo":{"ammKey":P,"inputMint":a,"outputMint":b,"inAmount":str(n),"outAmount":str(out)}}]},a,b,n)
def bridge():
    q={"status":"route_preview_only","mint":M,"retrieved_at":stamp(0),
       "buy":route(USDC,M,100000000,200000),"sell":route(M,USDC,200000,99000000),
       "test_input_usdc":"100","reported_roundtrip_return_usdc":"99",
       "quote_source_timestamp_verified":False,"transport_mocked":False,**FALSE_FLAGS}
    d={"status":"diagnostic_complete","mint":M,"reference_pool":P,"retrieved_at":stamp(0),
       "stages":{"mint":{"status":"ok","data":{"mint_authority_disabled":True,"freeze_authority_disabled":True}},
                 "holders":{"status":"ok"},"reference_pool":{"status":"ok"},
                 "route_preview":{"status":"ok","data":q}},**FALSE_FLAGS}
    return {"source":"dexterm_historical_shortlist_exact_mint_lookup","status":"diagnostic_complete",
            "lookups":[],"scan":{"reports":[{"candidate":{"mint":M,"pool":P},"diagnostic":d}],**FALSE_FLAGS},**FALSE_FLAGS}
def write(folder,name,body):
    p=folder/name;p.write_text(json.dumps(body),encoding="utf-8");return p
def populate(folder):
    db=folder/"research.db"
    archive(db,[write(folder,"entry.json",bridge())])
    rows,_=collect(db,500);e=rows[0]
    q={"mint":M,"entry_timestamp":stamp(0),"retrieved_at":stamp(180),
       "entry_source_digest":e["source_digest"],"entry_source_index":e["source_index"],
       "quantity_raw":"200000","sell":route(M,USDC,200000,110000000)}
    report={"source":"dexterm_exact_quantity_exit_quote","status":"exit_quotes_complete",
            "research_only":True,"attempted_quotes":1,"quotes":[q],"transport_mocked":False,
            "api_key_used":False,"quote_source_timestamp_verified":False,"fee_semantics_verified":False,**FALSE_FLAGS}
    archive(db,[write(folder,"exit.json",report)])
    return db

class EndToEndTests(unittest.TestCase):
    def test_archive_to_paper_and_learning_publication(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);db=populate(folder);before=db.read_bytes()
            rows,_=collect(db,500);exits,stats=collect_exits(db,rows)
            self.assertEqual(stats["bound_exit_quotes"],1)
            self.assertEqual(len(exits),1)
            paper=replay(db)
            self.assertEqual(paper["closed_positions"],1)
            self.assertEqual(paper["open_positions"],0)
            self.assertEqual(paper["realized_net_raw"],9475000)
            learned=run(db,folder/"models.db",allow_experiment=True)
            self.assertTrue(learned["experiment_blocked"])
            self.assertEqual(learned["archive_stats"]["bound_exit_quotes"],1)
            publish(folder,"ready",learned)
            panel=read(folder)
            self.assertEqual(panel["status_label_tr"],"Eğitim engellendi")
            self.assertFalse(panel["live_trading_enabled"])
            self.assertEqual(before,db.read_bytes())
    def test_http_access_and_no_store(self):
        from cyberbot.api import app
        async def check(folder):
            with patch.dict(os.environ,{"CYBERBOT_TAILSCALE_ENABLED":"0","CYBERBOT_SOLANA_PWA_REPORT_DIR":str(folder)}):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=("127.0.0.1",12345)),base_url="http://localhost") as c:
                    res=await c.get("/api/solana/research-status")
                    self.assertEqual(res.status_code,200)
                    self.assertEqual(res.headers["cache-control"],"no-store")
                    self.assertFalse(res.json()["real_orders"])
                    self.assertEqual(res.json()["publication_state"],"ready")
                    page=await c.get("/solana/research")
                    self.assertEqual(page.status_code,200)
                    self.assertIn("SOLANA ARAŞTIRMA",page.text)
                    self.assertEqual((await c.post("/api/solana/research-status",headers={"x-cyberbot-paper":"1"})).status_code,405)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=("192.0.2.1",12345)),base_url="http://localhost") as c:
                    self.assertEqual((await c.get("/api/solana/research-status")).status_code,403)
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);db=populate(folder)
            publish(folder,"ready",run(db,folder/"models.db"))
            asyncio.run(check(folder))
