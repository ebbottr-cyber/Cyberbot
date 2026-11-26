from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import HTMLResponse,JSONResponse
from .operations import health

router=APIRouter()

@router.get("/health",response_class=HTMLResponse)
def panel():
    return (Path(__file__).parent/"web"/"health.html").read_text(encoding="utf-8")

@router.get("/api/health")
def status():
    report=health()
    return JSONResponse(report,status_code=200 if report["status"]=="ok" else 503)

from .worker import status as worker_status

@router.get('/api/worker/status')
def worker():
    return worker_status()

from .readiness import snapshot as readiness_snapshot
@router.get("/api/readiness")
def readiness():return readiness_snapshot()

from .observed_pilot import snapshot as observed_snapshot
import sqlite3
@router.get("/api/observed-pilot")
def observed_pilot():
    try:return observed_snapshot()
    except (ValueError,OSError,sqlite3.Error,KeyError,TypeError,ArithmeticError):return JSONResponse({"detail":"Pilot kayıtları okunamadı."},status_code=503)

from .solana_pilot import snapshot as solana_pilot_snapshot
@router.get("/api/solana-pilot")
def solana_pilot():
    try:return solana_pilot_snapshot()
    except (ValueError,OSError,sqlite3.Error,KeyError,TypeError,ArithmeticError):return JSONResponse({"detail":"Solana pilotu okunamadı."},status_code=503)

from .futures_pilot import snapshot as futures_pilot_snapshot
@router.get("/api/futures-pilot")
def futures_pilot():
    try:return futures_pilot_snapshot()
    except (ValueError,OSError,sqlite3.Error,KeyError,TypeError,ArithmeticError):return JSONResponse({"detail":"Futures pilotu okunamadı."},status_code=503)

from .pilot_performance import snapshot as pilot_performance_snapshot
@router.get("/pilot",response_class=HTMLResponse)
def pilot_panel():return (Path(__file__).parent/"web"/"pilot.html").read_text(encoding="utf-8")
@router.get("/api/pilot/performance")
def pilot_performance():
    try:return pilot_performance_snapshot()
    except (ValueError,OSError,sqlite3.Error,KeyError,TypeError,ArithmeticError):return JSONResponse({"detail":"Pilot performansı okunamadı."},status_code=503)

from .alerts import snapshot as alerts_snapshot

@router.get("/alerts",response_class=HTMLResponse)
def alerts_panel():
    return (Path(__file__).parent/"web"/"alerts.html").read_text(encoding="utf-8")

@router.get("/api/alerts")
def alerts():
    try:return alerts_snapshot()
    except (OSError,ValueError,sqlite3.Error,KeyError,TypeError,ArithmeticError):
        return JSONResponse({"detail":"Uyarı kayıtları okunamadı."},status_code=503)
