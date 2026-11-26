"""One-shot, local quote adapter boundary. No network, scheduling or trade requests."""
import os,json,re
from pathlib import Path
from . import observed_pilot as stocks,solana_pilot as sol,futures_pilot as fut
from .observed_pilot import PilotError
MARKETS=("BIST","NASDAQ","XETRA","SOLANA","FUTURES")
MAX_BYTES=32768
SCHEMA="cyberbot-quote-1"

def source_for(market):
    source=os.getenv("CYBERBOT_INGRESS_SOURCE_"+market,"")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}",source):raise PilotError("Piyasa için açık kaynak kimliği gerekli.")
    return source

def ingest(envelope,*,clock=stocks.utc):
    if os.getenv("CYBERBOT_PILOT_INGRESS_ENABLED")!="1" or not stocks.permitted():raise PilotError("Yerel giriş veya veri izni kapalı.")
    if not isinstance(envelope,dict) or set(envelope)!={"schema","market","quote"} or envelope["schema"]!=SCHEMA:raise PilotError("Girdi şeması geçersiz.")
    market=envelope["market"];q=envelope["quote"]
    if not isinstance(market,str) or market not in MARKETS or not isinstance(q,dict) or q.get("market")!=market:raise PilotError("Piyasa uyuşmazlığı.")
    if q.get("source")!=source_for(market):raise PilotError("Kaynak izin listesinde değil.")
    if market=="XETRA":
        fx=q.get("fx")
        fx_source=os.getenv("CYBERBOT_INGRESS_FX_SOURCE","")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}",fx_source) or not isinstance(fx,dict) or fx.get("source")!=fx_source:raise PilotError("Kur kaynağı izin listesinde değil.")
    # The actual pilot is still responsible for timestamp, order, depth and risk validation.
    if market=="SOLANA":result=sol.observe(q,clock=clock)
    elif market=="FUTURES":result=fut.observe(q,clock=clock)
    else:result=stocks.observe(market,q,clock=clock)
    return {"market":market,"status":result["status"],"source":q["source"],"source_verified":False,"provider_connected":False,"real_orders":False,"automatic_entry_enabled":False}

def read_file(file,*,clock=stocks.utc):
    with Path(file).open("rb") as stream:raw=stream.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise PilotError("Gözlem dosyası çok büyük.")
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:raise PilotError("Tekrar JSON alanı.")
            out[k]=v
        return out
    def reject(value):raise PilotError("Geçersiz JSON sayısı.")
    try:envelope=json.loads(raw,object_pairs_hook=pairs,parse_constant=reject)
    except (UnicodeError,ValueError,RecursionError):raise PilotError("Gözlem JSON dosyası geçersiz.") from None
    return ingest(envelope,clock=clock)
