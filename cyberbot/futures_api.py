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
