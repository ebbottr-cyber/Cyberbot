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
