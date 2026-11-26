import os
from pathlib import Path
from fastapi import APIRouter,HTTPException,Query
from fastapi.responses import HTMLResponse
from .analysis import demo_review,review
from .market import INDEX
from .providers.equity import history,DataError

router=APIRouter()

@router.get("/analysis",response_class=HTMLResponse)
def panel():
    return (Path(__file__).parent/"web"/"analysis.html").read_text(encoding="utf-8")

@router.get("/api/analysis/demo/{symbol}")
def demo(symbol:str,tick:int=Query(9,ge=0,le=9)):
    if symbol not in INDEX:raise HTTPException(404,"Bilinmeyen demo sembolü.")
    return demo_review(symbol,tick)

@router.get("/api/analysis/history")
def archive(market:str,symbol:str,limit:int=Query(250,ge=5,le=6000)):
    try:
        data=history(os.getenv("CYBERBOT_EBBOT_DB"),market,symbol,limit)
        return review(symbol,data["bars"],mode="historical_unverified",source="Yerel EBBot arşivi")
    except (DataError,ValueError) as e:
        raise HTTPException(422,str(e)) from None
