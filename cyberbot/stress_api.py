from pathlib import Path
from threading import Lock
from fastapi import APIRouter,HTTPException,Query
from fastapi.responses import HTMLResponse
from .stress import run,SCENARIOS

router=APIRouter()
_lock=Lock()

@router.get("/stress",response_class=HTMLResponse)
def panel():
    return (Path(__file__).parent/"web"/"stress.html").read_text(encoding="utf-8")

@router.post("/api/stress/run")
def stress(scenario:str="gap",steps:int=Query(240,ge=60,le=360)):
    if scenario not in SCENARIOS:raise HTTPException(422,"Geçersiz senaryo.")
    if not _lock.acquire(blocking=False):raise HTTPException(429,"Bir stres testi zaten çalışıyor.")
    try:return run(scenario,steps)
    finally:_lock.release()
