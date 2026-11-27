"""Bounded public USD-M quote adapter. No credentials, account or order endpoints."""
import json,os,sqlite3
from contextlib import closing
from datetime import datetime,timezone
from decimal import Decimal as D
import httpx
from .. import futures_pilot as fut, observed_pilot as stocks
from ..pilot_ingress import ingest,source_for,SCHEMA
from ..observed_pilot import PilotError

SOURCE="binance-usdm-public"
HOST="https://fapi.binance.com"
BOOK="/fapi/v1/ticker/bookTicker"
MARK="/fapi/v1/premiumIndex"
INFO="/fapi/v1/fundingInfo"
FUNDING="/fapi/v1/fundingRate"
OPEN_INTEREST="/fapi/v1/openInterest"
MAX_BYTES=262144
PERIOD_MS=fut.FUNDING_PERIOD*1000

def configured():
    return os.getenv("CYBERBOT_BINANCE_OBSERVED_ENABLED")=="1" and os.getenv("CYBERBOT_BINANCE_DATA_RIGHTS_CONFIRMED")=="1"
def stamp(ms):
    if type(ms) is not int or not 0<ms<253402300799000:raise PilotError("Sağlayıcı zamanı geçersiz.")
    return datetime.fromtimestamp(ms/1000,timezone.utc)
def get(client,endpoint,params):
    if endpoint not in (BOOK,MARK,INFO,FUNDING,OPEN_INTEREST):raise PilotError("İzin verilmeyen API.")
    try:
        with client.stream("GET",HOST+endpoint,params=params) as response:
            response.raise_for_status()
            raw=bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw)>MAX_BYTES:raise PilotError("Sağlayıcı yanıtı çok büyük.")
        return json.loads(raw)
    except (httpx.HTTPError,ValueError,OSError):raise PilotError("Binance salt okunur veri sorgusu başarısız; otomatik tekrar yok.") from None
def parse(book,mark,info,sym,now):
    if not isinstance(book,dict) or not isinstance(mark,dict) or book.get("symbol")!=sym or mark.get("symbol")!=sym:raise PilotError("Sembol uyuşmazlığı.")
    bt,mt=stamp(book.get("time")),stamp(mark.get("time"))
    if any(not 0<=(now-t).total_seconds()<=fut.MAX_AGE for t in (bt,mt)) or abs((bt-mt).total_seconds())>3:raise PilotError("Fiyat/mark eski veya eşzamanlı değil.")
    if book["time"]//PERIOD_MS!=mark["time"]//PERIOD_MS:raise PilotError("Fonlama sınırında eşzamanlı gözlem gerekli.")
    next_at=mark.get("nextFundingTime")
    if type(next_at) is not int or next_at!=(mark["time"]//PERIOD_MS+1)*PERIOD_MS:raise PilotError("Fonlama takvimi modelle uyuşmuyor.")
    if not isinstance(info,list) or any(not isinstance(x,dict) or not isinstance(x.get("symbol"),str) for x in info):raise PilotError("Fonlama aralığı yanıtı geçersiz.")
    overrides=[x for x in info if x["symbol"]==sym]
    if len(overrides)>1 or any(type(x.get("fundingIntervalHours")) is not int or x["fundingIntervalHours"]!=8 for x in overrides):raise PilotError("Fonlama aralığı 8 saat değil.")
    bid,ask,mp=(stocks.dec(v) for v in (book.get("bidPrice"),book.get("askPrice"),mark.get("markPrice")))
    bq=fut.number(book.get("bidQty"),"0","1000000000");aq=fut.number(book.get("askQty"),"0","1000000000")
    if bid>ask:raise PilotError("Ters fiyat.")
    q={"market":"FUTURES","symbol":sym,"currency":"USDT","contract":"linear_perpetual","source":SOURCE,"source_at":min(bt,mt).isoformat(),"bid":str(bid),"ask":str(ask),"mark":str(mp),"bid_depth_usdt":str(min(bid*bq,D("1000000000"))),"ask_depth_usdt":str(min(ask*aq,D("1000000000"))),"funding":[]}
    return q
def existing(sym):
    p=stocks.path()
    if not p.is_file():return None
    with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
        db.execute("PRAGMA query_only=ON")
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='observed_accounts'").fetchone():return None
        if not db.execute("SELECT 1 FROM observed_accounts WHERE market='FUTURES'").fetchone():return None
        return fut.load(db,sym)
def settled(raw,expected,sym):
    if not isinstance(raw,list):raise PilotError("Fonlama yanıtı liste değil.")
    rows=[]
    for x in raw:
        if not isinstance(x,dict) or x.get("symbol")!=sym or x.get("rateType","Regular")!="Regular":raise PilotError("Fonlama sembolü veya türü geçersiz.")
        rows.append({"symbol":sym,"source":SOURCE,"settled_at":stamp(x.get("fundingTime")).isoformat(),"rate":str(fut.number(x.get("fundingRate"),"-.01",".01")),"mark":str(stocks.dec(x.get("markPrice")))})
    return fut.funding_records(rows,expected,SOURCE,sym)
def market_context(book,mark,oi,sym,now):
    """Current public observations only, not a directional signal or order input."""
    if not isinstance(oi,dict) or oi.get("symbol")!=sym or book.get("symbol")!=sym or mark.get("symbol")!=sym:
        raise PilotError("Piyasa bağlamı sembolü uyuşmuyor.")
    times=[stamp(x.get("time")) for x in (book,mark,oi)]
    if any(not 0<=(now-t).total_seconds()<=fut.MAX_AGE for t in times) or (max(times)-min(times)).total_seconds()>3:
        raise PilotError("Piyasa bağlamı eski veya eşzamanlı değil.")
    interest=fut.number(oi.get("openInterest"),"0","1000000000000")
    index=stocks.dec(mark.get("indexPrice"));mp=stocks.dec(mark.get("markPrice"))
    rate=fut.number(mark.get("lastFundingRate"),"-.1",".1")
    bid,ask=(stocks.dec(book.get(k)) for k in ("bidPrice","askPrice"))
    bq,aq=(fut.number(book.get(k),"0","1000000000") for k in ("bidQty","askQty"))
    if bid>ask:raise PilotError("Ters fiyat.")
    total=bq+aq
    return {"status":"research_only","symbol":sym,"source_at":min(times).isoformat(),
            "open_interest_base":str(interest),"indicative_open_interest_usdt":str(interest*mp),
            "reported_last_funding_rate":str(rate),"index_price":str(index),
            "mark_index_basis_pct":str((mp/index-1)*100),
            "best_level_qty_imbalance":str((bq-aq)/total) if total else None,
            "settled_funding_verified":False,"full_book_verified":False,
            "directional_signal":None,"pilot_applied":False,"real_orders":False}
def run(*,apply=False,transport=None,clock=stocks.utc,context_probe=False):
    if apply and context_probe:raise PilotError("Piyasa bağlamı yalnız salt okunur tanılama modunda.")
    if not configured():raise PilotError("Binance adaptörü veya veri kullanım izni kapalı.")
    if apply and (not fut.enabled() or os.getenv("CYBERBOT_PILOT_INGRESS_ENABLED")!="1" or source_for("FUTURES")!=SOURCE):raise PilotError("Futures pilot/giriş izni veya kaynak ayarı eksik.")
    sym=fut.symbol()
    old=existing(sym) if apply else None
    if old and old["quote"] and old["quote"]["source"]!=SOURCE:raise PilotError("Mevcut pilot farklı kaynağa bağlı.")
    with httpx.Client(timeout=httpx.Timeout(8,connect=3),follow_redirects=False,trust_env=False) as client:
        def fetch(endpoint,params):return transport(endpoint,params) if transport is not None else get(client,endpoint,params)
        info=fetch(INFO,{})
        book=fetch(BOOK,{"symbol":sym});mark=fetch(MARK,{"symbol":sym})
        q=parse(book,mark,info,sym,clock())
        context=market_context(book,mark,fetch(OPEN_INTEREST,{"symbol":sym}),sym,clock()) if context_probe else None
        if old and old["position"]:
            before=stocks.ts(old["quote"]["source_at"]);after=stocks.ts(q["source_at"])
            if after<=before:raise PilotError("Yeni gözlem yok.")
            expected=fut.boundaries(before.isoformat(),after.isoformat())
            # Only exact open-position gap, no bulk price history. Check unexpected events too.
            if expected or (after-before).total_seconds()>fut.MAX_AGE:
                raw=fetch(FUNDING,{"symbol":sym,"startTime":int(before.timestamp()*1000)+1,"endTime":int(after.timestamp()*1000),"limit":fut.MAX_FUNDING_EVENTS+1})
                q["funding"]=settled(raw,expected,sym)
        fut.validate(q,clock(),sym)
    envelope={"schema":SCHEMA,"market":"FUTURES","quote":q}
    result={"status":"quote_validated","symbol":sym,"source":SOURCE,"source_at":q["source_at"],"quote":q,"market_context":context,"applied":False,"live_data_verified":False,"exchange_execution_verified":False,"real_orders":False,"automatic_entry_enabled":False,"bulk_price_download_enabled":False,"transport_mocked":transport is not None}
    if apply:
        result["ingress"]=ingest(envelope,clock=clock);result["applied"]=True
    return result
