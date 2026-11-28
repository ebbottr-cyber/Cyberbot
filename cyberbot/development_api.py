from pathlib import Path
import sqlite3
from fastapi import APIRouter,HTTPException
from fastapi.responses import HTMLResponse
from .development import overview
from .fund_etf_api import with_fund_development
from .worker import status as worker_status
from .operations import health

router=APIRouter()
@router.get("/development",response_class=HTMLResponse)
def panel():return with_fund_development((Path(__file__).parent/"web"/"development.html").read_text(encoding="utf-8"))
@router.get("/api/development")
def data(mode:str="synthetic"):
    if mode not in ("synthetic","historical_unverified"):raise HTTPException(422,"Geçersiz veri modu.")
    try:
        result=overview(mode)
        worker=worker_status()
        last=worker.get("last_cycle") or {}
        result["worker"]={"status":worker["status"],"last_finished_at":last.get("finished_at"),"last_status":last.get("status"),"recorded_cycles":worker["cycles_recorded"],"running_verified":False}
        h=health()
        result["runtime"]={k:h[k] for k in ("local_llm_configured","chronos_configured","model_runtime_verified","bulk_price_download_enabled","real_orders")}
        return result
    except (sqlite3.Error,OSError,ValueError,KeyError,TypeError):raise HTTPException(503,"Araştırma kayıtları okunamadı.") from None
