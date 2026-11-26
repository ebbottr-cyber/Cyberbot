import os
from functools import lru_cache
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from .engine import Ledger, PaperError
from .lab import experiment
from .market import INDEX

app=FastAPI(title="Cyberbot Obsidian",docs_url=None,redoc_url=None,openapi_url=None)

@lru_cache
def ledger():
    return Ledger(os.environ.get("CYBERBOT_DB","var/paper.sqlite3"))

@app.middleware("http")
async def local_guard(request:Request, call_next):
    host=request.headers.get("host","").split(":")[0]
    client=request.client.host if request.client else ""
    if host not in ("localhost","127.0.0.1") or client not in ("127.0.0.1","::1"):
        return JSONResponse({"detail":"Yalnız yerel erişim."},status_code=403)
    if request.method not in ("GET","HEAD"):
        origin=request.headers.get("origin")
        if origin and origin != "http://"+request.headers.get("host",""):
            return JSONResponse({"detail":"Kaynak reddedildi."},status_code=403)
        if request.headers.get("x-cyberbot-paper")!="1":
            return JSONResponse({"detail":"Sanal işlem başlığı gerekli."},status_code=403)
    response=await call_next(request)
    response.headers["Cache-Control"]="no-store"
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["X-Frame-Options"]="DENY"
    response.headers["Content-Security-Policy"]="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    return response

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
