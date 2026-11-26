from pathlib import Path
from fastapi import APIRouter
from .futures import Futures,path_for
from fastapi.responses import HTMLResponse
router=APIRouter()
def store():return Futures(path_for())
@router.get("/futures",response_class=HTMLResponse)
def panel():return (Path(__file__).parent/"web"/"futures.html").read_text(encoding="utf-8")
@router.get("/api/futures/status")
def status():return store().snapshot()
@router.post("/api/futures/open/{symbol}/{side}")
def open_position(symbol:str,side:str):
    f=store();f.open(symbol,side);return f.snapshot()
@router.post("/api/futures/close/{trade_id}")
def close(trade_id:int):
    f=store();f.close(trade_id);return f.snapshot()
@router.post("/api/futures/advance")
def advance():
    f=store();f.advance();return f.snapshot()

from fastapi import HTTPException
from threading import Lock
from .futures_research import run_job
from .research_pipeline import PipelineJournal,research_path
_lock=Lock()
@router.post("/api/futures/research/{symbol}")
def research(symbol:str):
    if not _lock.acquire(blocking=False):raise HTTPException(429,"Araştırma çalışıyor.")
    try:
        job=run_job(symbol)
        return {"status":job["status"],"result":PipelineJournal(research_path()).get(job["id"])}
    except (ValueError,ArithmeticError) as e:raise HTTPException(422,str(e)) from None
    finally:_lock.release()
