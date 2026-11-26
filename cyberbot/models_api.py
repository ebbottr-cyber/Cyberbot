import os
from pathlib import Path
from threading import Lock
from fastapi import APIRouter,HTTPException,Query
from fastapi.responses import HTMLResponse
from .models import evaluate,summarize,LocalModelError
from .learning import demo_rows
from .providers.equity import history,DataError
from .analysis import review
from .chronos_research import configured,benchmark,ChronosError

router=APIRouter()
_lock=Lock()

@router.get("/models",response_class=HTMLResponse)
def panel():
    return (Path(__file__).parent/"web"/"models.html").read_text(encoding="utf-8")

@router.get("/api/models/status")
def status():
    return {"local_llm_configured":os.getenv("CYBERBOT_LOCAL_LLM_ENABLED")=="1" and bool(os.getenv("CYBERBOT_OLLAMA_MODEL")),
            "chronos_connected":False,"chronos_configured":configured(),"real_orders":False}

@router.get("/api/models/demo")
def demo():
    return evaluate([r["close"] for r in demo_rows()],mode="synthetic")

@router.get("/api/models/history")
def historical(market:str,symbol:str,limit:int=Query(250,ge=120,le=6000)):
    try:
        d=history(os.getenv("CYBERBOT_EBBOT_DB"),market,symbol,limit)
        return evaluate([b["close"] for b in d["bars"]],mode="historical_unverified")
    except (DataError,ValueError,OverflowError) as e:
        raise HTTPException(422,str(e)) from None

@router.post("/api/models/summary")
def summary():
    model=os.getenv("CYBERBOT_OLLAMA_MODEL")
    if os.getenv("CYBERBOT_LOCAL_LLM_ENABLED")!="1" or not model:
        raise HTTPException(403,"Yerel dil modeli yapılandırılmadı.")
    if not _lock.acquire(blocking=False):
        raise HTTPException(429,"Bir model isteği zaten çalışıyor.")
    try:
        bars=demo_rows()
        report=review("DEMO-MODEL",bars,mode="synthetic",source="Cyberbot demo")
        return summarize(report,model)
    except LocalModelError as e:
        raise HTTPException(503,str(e)) from None
    finally:
        _lock.release()

@router.post("/api/models/chronos")
def chronos(mode:str="synthetic",market:str="BIST",symbol:str="THYAO.IS",windows:int=Query(16,ge=8,le=32)):
    if not configured():raise HTTPException(403,"Yerel Chronos 2 yapılandırılmadı.")
    if not _lock.acquire(blocking=False):raise HTTPException(429,"Bir model isteği zaten çalışıyor.")
    try:
        if mode=="synthetic":
            if market=="FUTURES":
                from .futures_research import rows_for
                prices=[r["close"] for r in rows_for(symbol)]
            else:prices=[r["close"] for r in demo_rows()]
        elif mode=="historical_unverified":
            prices=[b["close"] for b in history(os.getenv("CYBERBOT_EBBOT_DB"),market,symbol,250)["bars"]]
        else:raise ChronosError("Geçersiz veri modu.")
        return benchmark(prices,mode=mode,windows=windows)
    except (DataError,ValueError,OverflowError) as e:
        raise HTTPException(422,str(e)) from None
    finally:
        _lock.release()
