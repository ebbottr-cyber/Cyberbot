import os
from pathlib import Path
from functools import lru_cache
from fastapi import APIRouter,HTTPException,Query
from fastapi.responses import HTMLResponse
from .learning import Journal,research,demo_rows
from .providers.equity import history,DataError

router=APIRouter()

@lru_cache
def journal(path):
    return Journal(path)
def store():
    from .db_paths import checked
    return journal(checked()["learning"])

@router.get("/learning",response_class=HTMLResponse)
def panel():
    return (Path(__file__).parent/"web"/"learning.html").read_text(encoding="utf-8")

@router.get("/api/learning")
def recent():
    return store().recent()

@router.get("/api/learning/experiment/{key}")
def result(key:str):
    d=store().get(key)
    if d is None:raise HTTPException(404,"Deney bulunamadı.")
    return d

@router.post("/api/learning/run")
def run(mode:str="synthetic",market:str="BIST",symbol:str="THYAO.IS",limit:int=Query(250,ge=120,le=6000)):
    try:
        if mode=="synthetic":
            d=research(demo_rows(),mode=mode,symbol="DEMO-WALK")
        elif mode=="historical_unverified":
            b=history(os.getenv("CYBERBOT_EBBOT_DB"),market,symbol,limit)
            d=research(b["bars"],mode=mode,symbol=market+":"+symbol)
        else:raise ValueError("Geçersiz veri modu.")
        return {"new":store().save(d),"experiment":d}
    except (DataError,ValueError) as e:
        raise HTTPException(422,str(e)) from None
