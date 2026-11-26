import os
from pathlib import Path
from fastapi import APIRouter,HTTPException,Query
from fastapi.responses import HTMLResponse
from .strategy_lab import comparison,synthetic
from .providers.equity import history,DataError

router=APIRouter()

@router.get("/strategies",response_class=HTMLResponse)
def panel():
    return (Path(__file__).parent/"web"/"strategies.html").read_text(encoding="utf-8")

@router.get("/api/strategies/demo")
def demo():
    return synthetic()

@router.get("/api/strategies/history")
def research(market:str,symbol:str,limit:int=Query(250,ge=60,le=6000)):
    try:
        d=history(os.getenv("CYBERBOT_EBBOT_DB"),market,symbol,limit)
        return comparison(d["bars"],mode="historical_unverified",symbol=symbol)
    except (DataError,ValueError) as e:
        raise HTTPException(422,str(e)) from None

from threading import Lock
from .robustness import evaluate
from .learning import demo_rows

_robust_lock=Lock()

@router.post("/api/strategies/robustness")
def robustness(mode:str="synthetic",market:str="BIST",symbol:str="THYAO.IS",limit:int=Query(250,ge=120,le=1000)):
    if not _robust_lock.acquire(blocking=False):raise HTTPException(429,"Bir dayanıklılık deneyi çalışıyor.")
    try:
        if mode=="synthetic":
            rows=demo_rows()
            symbol="DEMO-ROBUST"
        elif mode=="historical_unverified":
            rows=history(os.getenv("CYBERBOT_EBBOT_DB"),market,symbol,limit)["bars"]
        else:raise ValueError("Geçersiz veri modu.")
        return evaluate(rows,mode=mode,market=market,symbol=symbol)
    except (DataError,ValueError,ArithmeticError) as e:
        raise HTTPException(422,str(e)) from None
    finally:_robust_lock.release()
