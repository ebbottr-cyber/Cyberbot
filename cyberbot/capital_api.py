import os
from functools import lru_cache
from threading import Lock
from fastapi import APIRouter,HTTPException
from .capital import Portfolio,CAPITAL
from .engine import PaperError

router=APIRouter()
lock=Lock()
@lru_cache(maxsize=4)
def portfolio(base):
    return Portfolio(base)
def store():
    return portfolio(os.getenv("CYBERBOT_DB","var/paper.sqlite3"))
def market_ledger(market):
    if market not in CAPITAL:raise HTTPException(404,"Bilinmeyen piyasa.")
    return store().ledgers[market]

@router.get("/api/portfolio/status")
def status():
    with lock:return store().snapshot()
@router.post("/api/portfolio/{market}/buy/{symbol}")
def buy(market:str,symbol:str):
    with lock:
        market_ledger(market).buy(symbol)
        return store().snapshot()
@router.post("/api/portfolio/{market}/sell/{trade_id}")
def sell(market:str,trade_id:int):
    with lock:
        market_ledger(market).sell(trade_id)
        return store().snapshot()
@router.post("/api/portfolio/{market}/advance")
def advance(market:str):
    with lock:
        market_ledger(market).advance()
        return store().snapshot()
