"""Read-only fund/ETF snapshot endpoints, protected by the existing app middleware."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter()
MAX_BYTES = 25_000_000

@router.get("/fund-etf", response_class=HTMLResponse)
def page():
    return (Path(__file__).parent/"web"/"fund_etf.html").read_text(encoding="utf-8")

@router.get("/api/fund-etf")
def data():
    base=dict(status="unavailable",real_orders=False,execution_allowed=False,live_data_verified=False)
    path=Path(os.environ.get("CYBERBOT_FUND_ETF_SNAPSHOT","var/fund-etf-snapshot.json"))
    try:
        with path.open("rb") as f:
            raw=f.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:
            raise ValueError("snapshot_too_large")
        obj=json.loads(raw,parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
        if obj.get("schema_version")!=1 or obj.get("real_orders") is not False or obj.get("execution_allowed") is not False:
            raise ValueError("invalid_snapshot")
        stamp=datetime.fromisoformat(obj["generated_at"])
        if stamp.tzinfo is None:
            raise ValueError("timezone_required")
        age=(datetime.now(timezone.utc)-stamp).total_seconds()
        if age<0:
            raise ValueError("future_snapshot")
        if not isinstance(obj.get("instruments"),list) or not isinstance(obj.get("portfolios",[]),list):
            raise ValueError("invalid_snapshot")
        # Return only UI fields; do not publish untrusted external URLs or full news text.
        items=[]
        for i in obj["instruments"]:
            m=i.get("metrics") or {}; rank=i.get("rank") or {}; decision=i.get("decision") or {}
            items.append(dict(market=i.get("market"),symbol=i.get("symbol"),name=i.get("name"),
                group=i.get("category") or i.get("sector"),currency=m.get("currency") or i.get("currency"),
                status=i.get("status"),score=rank.get("research_score"),peer_rank=i.get("peer_rank"),
                last_session=m.get("last_session"),action=decision.get("action"),reason=decision.get("reason_tr"), commentary=(i.get("explanation") or {}).get("commentary"), commentary_provider=(i.get("explanation") or {}).get("provider")))
        portfolios=[{k:p.get(k) for k in ("id","currency","status","equity","cash","cash_weight","last_session","hypothetical_drawdown","alerts")} for p in obj.get("portfolios",[])]
        payload=dict(base,status=obj.get("status"),generated_at=stamp.isoformat(),age_seconds=age,
                     stale=age>172800,markets=obj.get("markets",[]),counts=obj.get("counts",{}),
                     instruments=items,portfolios=portfolios,errors=obj.get("errors",[]),source_checks=obj.get("source_checks",[]),backup=obj.get("backup",{"status":"disabled"}),
                     paper_replays=[{k:p.get(k) for k in ("id","market","symbol","currency","status","available_cash","available_units","reserved_cash","reserved_units","pending","events","pnl")} for p in obj.get("paper_replays",[])],
                     auto_paper=[{k:p.get(k) for k in ("id","market","symbol","currency","status","available_cash","available_units","reserved_cash","reserved_units","pending","history","reason_tr","pnl")} for p in obj.get("auto_paper",[])],
                     optimizations=[{k:p.get(k) for k in ("id","market","currency","status","weights","last_session")} for p in obj.get("optimizations",[])])
        return JSONResponse(payload)
    except (OSError,ValueError,TypeError,KeyError,AttributeError):
        return JSONResponse(dict(base,reason="Araştırma çıktısı yok veya okunamadı."),status_code=503)

FUND_MENU = '<a class="tile" href="/fund-etf"><strong>Fon &amp; ETF</strong><span>TEFAS · Global ETF</span></a>'

def with_fund_menu(html):
    """Render one idempotent menu link while retaining all other market markup."""
    if 'href="/fund-etf"' in html:
        return html
    marker='<a class="tile" href="/futures">'
    if marker in html:
        return html.replace(marker,FUND_MENU+marker,1)
    return html

@router.get("/api/fund-etf/development")
def development_data():
    from tools.fund_etf_development import overview
    import sqlite3
    base=dict(status="unavailable",markets=[],recent=[],paper_accounts=[],
              real_orders=False,model_promoted=False,profitability_verified=False)
    try:
        history=overview(os.environ.get("CYBERBOT_FUND_ETF_DEVELOPMENT","var/fund-etf.sqlite3.development.sqlite3"))
        current=data()
        history["paper_accounts"]=[]
        history["paper_snapshot_status"]="unavailable"
        if current.status_code==200:
            snap=json.loads(current.body)
            history["paper_snapshot_status"]="stale" if snap["stale"] else snap["status"]
            history["paper_generated_at"]=snap["generated_at"]
            if not snap["stale"] and snap["status"] in ("research_only","partial"):
                for p in snap.get("auto_paper",[]):
                    history["paper_accounts"].append({**{k:p.get(k) for k in ("id","market","symbol","currency","status","pnl","reason_tr")},
                        "pending_count":len(p.get("pending") or []),
                        "intent_count":len(p.get("history") or [])})
        return JSONResponse(history)
    except (sqlite3.Error,OSError,ValueError,KeyError,TypeError,AttributeError):
        return JSONResponse(base,status_code=503)


def with_fund_development(html):
    """Add an independent section without editing the shared static dashboard."""
    fragment=(Path(__file__).parent/"web"/"fund_etf_development_fragment.html").read_text(encoding="utf-8")
    if 'id="fundDevelopment"' in html:
        return html
    return html.replace("</main>",fragment+"</main>",1)
