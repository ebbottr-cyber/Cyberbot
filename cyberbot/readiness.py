"""Read-only live-paper readiness inventory. Never enables providers or places orders."""
import os
from datetime import datetime,timezone
from pathlib import Path
from .db_paths import checked,PathCollision
from .operations import inspect_db,required
from .capital import CAPITAL,fx_quote
from .futures import START
from .worker import status as worker_status
from .providers.equity import history,DataError

VERSION="paper-readiness-1"
PROBES={"BIST":"THYAO.IS","NASDAQ":"AAPL","XETRA":"SAP.DE"}

def snapshot():
    now=datetime.now(timezone.utc)
    try:paths=checked()
    except (PathCollision,OSError,RuntimeError):
        return {"version":VERSION,"as_of":now.isoformat(),"status":"blocked","database_isolation":"failed","markets":[],"blockers":["Veritabanı yolları doğrulanamadı veya çakışıyor."],"live_paper_enabled":False,"real_orders":False,"bulk_price_download_enabled":False}
    archive=os.getenv("CYBERBOT_EBBOT_DB")
    rights=os.getenv("CYBERBOT_EQUITY_RESEARCH_RIGHTS_CONFIRMED")=="1"
    fx=fx_quote(now=now)
    markets=[]
    for market,(currency,amount) in {**CAPITAL,"FUTURES":("USDT",START)}.items():
        role="futures" if market=="FUTURES" else "paper_"+market.lower()
        db=inspect_db(paths[role],required(role))
        data={"status":"not_configured","symbol":PROBES.get(market),"observations":None,"last_session":None,"age_days":None,"currency":None}
        blockers=[]
        if db!="ok":blockers.append("Sanal kasa: "+db)
        if market in PROBES:
            if not archive:data["status"]="archive_not_configured"
            elif not rights:data["status"]="rights_not_confirmed"
            else:
                try:
                    d=history(archive,market,PROBES[market],250)
                    data.update(status=d["status"],observations=len(d["bars"]),last_session=d["bars"][-1]["session"] if d["bars"] else None,age_days=d["age_days"],currency=d["currency"])
                except DataError:data["status"]="archive_unavailable"
            from .providers.equity_observed import configured
            data["local_quote_bridge_configured"]=configured(market)
            blockers.append("Lisanslı yerel kotasyon adaptörü mevcut; gerçek zamanlı akış, seans ve işlem yeri doğrulanmadı.")
            if market=="XETRA":blockers.append("EUR/USD bid/ask dönüşüm pilotu mevcut; gerçek kur kaynağı doğrulanmadı.")
            if not rights:blockers.append("Arşiv araştırma kullanım hakkı beyanı yok.")
        elif market=="SOLANA":
            data["status"]="legacy_quote_diagnostics_removed"
            blockers.append("Eski bağımsız Solana kotasyon tanılaması kaldırıldı; ortak pilot kaydı geriye uyumluluk için korunuyor.")
        else:
            from .providers.binance_observed import configured
            data["status"]="public_adapter_configured" if configured() else "public_adapter_disabled"
            blockers.append("Binance public adaptör kodu mevcut; gerçek bağlantı, fonlama takvimi ve likidasyon doğrulanmadı.")
        blockers.append("Canlı veriyle ileri test doğrulaması yok; Beş piyasanın manuel gözlem pilotları mevcut.")
        markets.append({"market":market,"currency":currency,"initial_capital":str(amount),"database":db,"data":data,"status":"blocked","blockers":blockers,"live_data_verified":False,"paper_execution_verified":False})
    worker=worker_status()
    last=worker.get("last_cycle") or {}
    return {"version":VERSION,"as_of":now.isoformat(),"status":"blocked","database_isolation":"checked","markets":markets,
            "fx":{"status":fx["status"],"usdtry_available":fx.get("usdtry") is not None,"usdtusd_available":fx.get("usdtusd") is not None,"provider_verified":False},
            "worker":{"status":worker["status"],"last_finished_at":last.get("finished_at"),"running_verified":False},
            "blockers":["Sentetik kasalar canlı fiyatla birleştirilmez.","Yerel gözlem pilotu gerçek canlı yürütme değildir; bu rapor başlatma izni değildir."],
            "live_paper_enabled":False,"real_orders":False,"bulk_price_download_enabled":False,"profitability_verified":False}
