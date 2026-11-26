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

from .tournament import tournament,TournamentJournal
from .capital import CAPITAL,account_paths
from .stress import universe

def tournament_store():
    from .learning_api import store
    path=Path(os.getenv("CYBERBOT_LEARNING_DB","var/learning.sqlite3")).expanduser().resolve()
    forbidden=set(account_paths().values())
    forbidden.add(Path(os.getenv("CYBERBOT_DB","var/paper.sqlite3")).expanduser().resolve())
    if os.getenv("CYBERBOT_EBBOT_DB"):forbidden.add(Path(os.environ["CYBERBOT_EBBOT_DB"]).expanduser().resolve())
    if path in forbidden:raise ValueError("Araştırma veritabanı ayrı olmalı.")
    # Initialize the existing learning schema; tournament records use a separate table.
    store()
    return TournamentJournal(path)

@router.post("/api/strategies/tournament")
def compete(mode:str="synthetic",market:str="BIST",symbol:str="THYAO.IS",limit:int=Query(360,ge=240,le=1000)):
    if not _robust_lock.acquire(blocking=False):raise HTTPException(429,"Bir araştırma deneyi çalışıyor.")
    try:
        if market not in CAPITAL:raise ValueError("Geçersiz piyasa.")
        if mode=="synthetic":
            series=next(v.prices for v in universe("gap",360).values() if v.market==market)
            rows=[{"open":str(series[max(0,i-1)]),"close":str(p)} for i,p in enumerate(series)]
            symbol="DEMO-TOURNAMENT-"+market
        elif mode=="historical_unverified":
            if market=="SOLANA":raise ValueError("Solana tarihsel arşivi bağlı değil.")
            rows=history(os.getenv("CYBERBOT_EBBOT_DB"),market,symbol,limit)["bars"]
        else:raise ValueError("Geçersiz veri modu.")
        result=tournament(rows,mode=mode,market=market,symbol=symbol)
        journal=tournament_store()
        return {"new":journal.save(result),"result":result}
    except (DataError,ValueError,ArithmeticError) as e:raise HTTPException(422,str(e)) from None
    finally:_robust_lock.release()

@router.get("/api/strategies/tournament/history")
def tournament_history(market:str="BIST",mode:str="synthetic"):
    if market not in CAPITAL or mode not in ("synthetic","historical_unverified"):raise HTTPException(422,"Geçersiz filtre.")
    try:return {"recent":tournament_store().recent(market,mode),"promotion_enabled":False}
    except ValueError as e:raise HTTPException(422,str(e)) from None

@router.get("/api/strategies/tournament/result/{key}")
def tournament_result(key:str):
    try:result=tournament_store().get(key)
    except ValueError as e:raise HTTPException(422,str(e)) from None
    if result is None:raise HTTPException(404,"Turnuva bulunamadı.")
    return result

from .regimes import evaluate as regime_evaluate, demo_rows as regime_demo

@router.post("/api/strategies/regimes")
def regimes(mode:str="synthetic",market:str="BIST",symbol:str="THYAO.IS",limit:int=Query(360,ge=120,le=1000)):
    if not _robust_lock.acquire(blocking=False):raise HTTPException(429,"Bir araştırma deneyi çalışıyor.")
    try:
        if market not in CAPITAL:raise ValueError("Geçersiz piyasa.")
        if mode=="synthetic":
            rows=regime_demo(market)
            symbol="DEMO-REGIME-"+market
        elif mode=="historical_unverified":
            if market=="SOLANA":raise ValueError("Solana tarihsel arşivi bağlı değil.")
            rows=history(os.getenv("CYBERBOT_EBBOT_DB"),market,symbol,limit)["bars"]
        else:raise ValueError("Geçersiz veri modu.")
        return regime_evaluate(rows,mode=mode,market=market,symbol=symbol)
    except (DataError,ValueError,ArithmeticError) as e:raise HTTPException(422,str(e)) from None
    finally:_robust_lock.release()

from .adaptive import evaluate as adaptive_evaluate
from .strategy_memory import StrategyMemory,filter_choice

@router.post("/api/strategies/adaptive")
def adaptive(mode:str="synthetic",market:str="BIST",symbol:str="THYAO.IS",limit:int=Query(360,ge=240,le=1000)):
    if not _robust_lock.acquire(blocking=False):raise HTTPException(429,"Bir araştırma deneyi çalışıyor.")
    try:
        if market not in CAPITAL:raise ValueError("Geçersiz piyasa.")
        if mode=="synthetic":
            rows=regime_demo(market)
            symbol="DEMO-ADAPTIVE-"+market
        elif mode=="historical_unverified":
            if market=="SOLANA":raise ValueError("Solana tarihsel arşivi bağlı değil.")
            rows=history(os.getenv("CYBERBOT_EBBOT_DB"),market,symbol,limit)["bars"]
        else:raise ValueError("Geçersiz veri modu.")
        result=adaptive_evaluate(rows,mode=mode,market=market,symbol=symbol)
        memory=StrategyMemory(tournament_store().path)
        saved=memory.record(result)
        result["memory"]=saved
        result["next_research_candidate"]=filter_choice(result["next_research_candidate"],saved["states"])
        return result
    except (DataError,ValueError,ArithmeticError) as e:raise HTTPException(422,str(e)) from None
    finally:_robust_lock.release()

@router.get("/api/strategies/memory")
def strategy_memory(mode:str="synthetic",market:str="BIST",symbol:str="THYAO.IS"):
    if market not in CAPITAL or mode not in ("synthetic","historical_unverified"):
        raise HTTPException(422,"Geçersiz filtre.")
    if mode=="synthetic":symbol="DEMO-ADAPTIVE-"+market
    try:return StrategyMemory(tournament_store().path).read(mode,market,symbol)
    except ValueError as e:raise HTTPException(422,str(e)) from None
