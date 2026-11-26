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
