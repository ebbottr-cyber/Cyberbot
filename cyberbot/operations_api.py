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
