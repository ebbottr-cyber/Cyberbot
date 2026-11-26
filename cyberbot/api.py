import os
from functools import lru_cache
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from .engine import Ledger, PaperError
from .lab import experiment
from .market import INDEX
from .access import authorize
from .db_paths import checked,PathCollision

app=FastAPI(title="Cyberbot Obsidian",docs_url=None,redoc_url=None,openapi_url=None)

@lru_cache
def _ledger(path):
    return Ledger(path)
def ledger():
    return _ledger(checked()["paper"])
ledger.cache_clear=_ledger.cache_clear

@app.middleware("http")
async def local_guard(request:Request, call_next):
    denial=authorize(request)
    if denial:
        return JSONResponse({"detail":denial},status_code=403,headers={"Cache-Control":"no-store"})
    response=await call_next(request)
    response.headers["Cache-Control"]="no-store"
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["X-Frame-Options"]="DENY"
    response.headers["Content-Security-Policy"]="default-src 'none'; script-src 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; manifest-src 'self'; img-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    return response

@app.exception_handler(PathCollision)
async def collision(request:Request,exc:PathCollision):
    return JSONResponse({"detail":str(exc)},status_code=409)

@app.exception_handler(PaperError)
async def paper_error(request:Request,exc:PaperError):
    return JSONResponse({"detail":str(exc)},status_code=409)

class Buy(BaseModel):
    symbol:str

@app.get("/",response_class=HTMLResponse)
def home():
    return (Path(__file__).parent/"web"/"index.html").read_text(encoding="utf-8")

@app.get("/api/status")
def status():
    return ledger().snapshot()

@app.post("/api/paper/buy")
def buy(body:Buy):
    ledger().buy(body.symbol)
    return ledger().snapshot()

@app.post("/api/paper/sell/{trade_id}")
def sell(trade_id:int):
    ledger().sell(trade_id)
    return ledger().snapshot()

@app.post("/api/paper/advance")
def advance():
    ledger().advance()
    return ledger().snapshot()

@app.get("/api/lab/{symbol}")
def lab(symbol:str):
    if symbol not in INDEX:
        raise HTTPException(404,"Bilinmeyen sembol.")
    return experiment(symbol)

from .data_api import router as data_router
app.include_router(data_router)

from .trader_api import router as trader_router
app.include_router(trader_router)

from .analysis_api import router as analysis_router
app.include_router(analysis_router)

from .strategy_api import router as strategy_router
app.include_router(strategy_router)

from .learning_api import router as learning_router
app.include_router(learning_router)

from .models_api import router as models_router
app.include_router(models_router)

from .pwa import router as pwa_router
app.include_router(pwa_router)

from .operations_api import router as operations_router
app.include_router(operations_router)

from .stress_api import router as stress_router
app.include_router(stress_router)

from .capital_api import router as capital_router
app.include_router(capital_router)

from .futures_api import router as futures_router
app.include_router(futures_router)

from .development_api import router as development_router
app.include_router(development_router)

from .knowledge_api import router as knowledge_router
app.include_router(knowledge_router)
