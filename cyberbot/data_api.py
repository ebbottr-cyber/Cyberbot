"""Veri merkezi: gerçek tarihsel gözlemler demo işlem defterine bağlanmaz."""
import logging
import os
import time
from dataclasses import asdict
from threading import Lock
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pathlib import Path
from .providers.equity import history, DataError
from .providers.solana_meme import SolanaMemeFeed, MarketDataError

router=APIRouter()
log=logging.getLogger(__name__)
_lock=Lock()
_cache=None
_last_attempt=None

@router.get("/data",response_class=HTMLResponse)
def center():
    return (Path(__file__).parent/"web"/"data.html").read_text(encoding="utf-8")

@router.get("/api/data/status")
def status():
    return {"equity_configured":bool(os.getenv("CYBERBOT_EBBOT_DB")),
            "solana_enabled":os.getenv("CYBERBOT_SOLANA_READ_ENABLED")=="1",
            "execution_enabled":False,"history_is_verified":False}

@router.get("/api/data/history")
def historical(market:str,symbol:str,limit:int=Query(250,ge=1,le=6000)):
    try:
        return history(os.getenv("CYBERBOT_EBBOT_DB"),market,symbol,limit)
    except DataError as e:
        log.warning("Hisse arşivi okunamadı: %s",e)
        raise HTTPException(422,str(e)) from None

@router.post("/api/data/solana/scan")
def scan():
    global _cache,_last_attempt
    if os.getenv("CYBERBOT_SOLANA_READ_ENABLED")!="1":
        raise HTTPException(403,"Solana veri erişimi kapalı.")
    with _lock:
        now=time.monotonic()
        if _cache is not None and now-_cache[0]<60:
            return {**_cache[1],"cached":True}
        if _last_attempt is not None and now-_last_attempt<60:
            raise HTTPException(429,"Yeni tarama için 60 saniye bekleyin.")
        _last_attempt=now
        try:
            feed=SolanaMemeFeed()
            stamp=int(time.time()*1000)
            quotes=feed.new_pools(stamp)[:8]+feed.latest_profiles(stamp,limit=8)[:8]
            result={"status":"read_only_observation","observed_at_ms":stamp,"cached":False,
                    "quotes":[asdict(q) for q in quotes],"security_verified":False,"paper_fill_enabled":False}
            _cache=(time.monotonic(),result)
            return result
        except (MarketDataError,ValueError,TypeError,OverflowError) as e:
            log.warning("Solana tarama hatası: %s",type(e).__name__)
            raise HTTPException(503,"Veri sağlayıcısı yanıt vermedi veya veri geçersiz.") from None

from .providers.coverage import coverage

@router.get("/api/data/coverage")
def coverage_status():
    return coverage(os.getenv("CYBERBOT_COVERAGE_REPORT"))
