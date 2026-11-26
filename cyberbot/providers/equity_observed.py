"""Licensed local equity quote bridge; IEX probe is diagnostic only, not XNAS."""
import os,json,re
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path
import httpx
from .. import observed_pilot as stocks
from ..pilot_ingress import ingest,source_for,SCHEMA
from ..observed_pilot import PilotError,ts,dec
VENUES={"BIST":"XIST","NASDAQ":"XNAS","XETRA":"XETR"}
MAX_BYTES=32768
def configured(m):
    return m in VENUES and os.getenv("CYBERBOT_EQUITY_OBSERVED_ENABLED")=="1" and os.getenv("CYBERBOT_EQUITY_QUOTE_RIGHTS_"+m)=="1"
def read_json(p):
    with Path(p).open("rb") as stream:raw=stream.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise PilotError("Dosya boyutu sınırı.")
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:raise PilotError("Tekrar JSON alanı.")
            result[k]=v
        return result
    def invalid(v):raise PilotError("Geçersiz JSON sayısı.")
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)
def session_gate(schedule,m,quote_at,now):
    if not isinstance(schedule,dict) or schedule.get("market")!=m or schedule.get("mic")!=VENUES[m]:raise PilotError("Seans piyasa kimliği uyuşmuyor.")
    if os.getenv("CYBERBOT_EQUITY_SESSION_REVIEWED_"+m)!="1":raise PilotError("Seans takvimi inceleme beyanı eksik.")
    reviewed=ts(schedule.get("reviewed_at"))
    if not timedelta(0)<=now-reviewed<=timedelta(days=7):raise PilotError("Seans takvimi eski.")
    ref=schedule.get("reference")
    if not isinstance(ref,str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}",ref):raise PilotError("Seans kanıt kimliği eksik.")
    windows=schedule.get("continuous_windows")
    if not isinstance(windows,list) or not 1<=len(windows)<=20:raise PilotError("Sürekli işlem seansı eksik.")
    prior=None;matches=0
    for w in windows:
        start,end=ts(w["open"]),ts(w["close"])
        if not timedelta(0)<end-start<=timedelta(hours=12) or (prior and start<prior) or end>reviewed+timedelta(days=7) or start<reviewed-timedelta(days=7):raise PilotError("Seans aralığı geçersiz.")
        prior=end
        if start<=quote_at<=now<end:matches+=1
    if matches!=1:raise PilotError("Sürekli işlem seansı dışında.")
    return ref
def prepare(m,raw,schedule,now):
    if not configured(m):raise PilotError("Piyasa adaptörü veya veri izni kapalı.")
    sym,_,_=stocks.account(m)
    if not isinstance(raw,dict) or (raw.get("market"),raw.get("symbol"),raw.get("mic"),raw.get("currency"))!=(m,sym,VENUES[m],stocks.quote_currency(m)):raise PilotError("Piyasa/sözleşme/para birimi uyuşmazlığı.")
    if raw.get("source")!=source_for(m) or raw.get("realtime") is not True or raw.get("continuous_trading") is not True:raise PilotError("Kaynak, gerçek zaman veya işlem durumu beyanı eksik.")
    at=ts(raw.get("source_at"));ref=session_gate(schedule,m,at,now)
    q={k:raw[k] for k in ("market","symbol","currency","source","source_at","bid","ask")}
    q["session_open"]=True
    q["venue"]=VENUES[m];q["session_reference"]=ref
    q["bid_size"]=str(dec(raw.get("bid_size")));q["ask_size"]=str(dec(raw.get("ask_size")))
    if m=="XETRA":q["fx"]=raw["fx"]
    stocks.validate(m,q,now)
    return {"schema":SCHEMA,"market":m,"quote":q}
def run_local(m,quote_file,schedule_file,*,apply=False,clock=stocks.utc):
    envelope=prepare(m,read_json(quote_file),read_json(schedule_file),clock())
    result={"market":m,"status":"local_quote_validated","mic":VENUES[m],"applied":False,"venue_verified":False,"live_data_verified":False,"real_orders":False}
    if apply:
        result["ingress"]=ingest(envelope,clock=clock);result["applied"]=True
    return result
def iex_probe(*,transport=None,clock=stocks.utc):
    if os.getenv("CYBERBOT_IEX_PROBE_ENABLED")!="1" or os.getenv("CYBERBOT_IEX_DATA_RIGHTS_CONFIRMED")!="1":raise PilotError("IEX tanılama izni kapalı.")
    key=os.getenv("CYBERBOT_ALPACA_KEY","");secret=os.getenv("CYBERBOT_ALPACA_SECRET","")
    if not key or not secret or len(key)>256 or len(secret)>256:raise PilotError("Alpaca kimlik bilgisi eksik.")
    url="https://data.alpaca.markets/v2/stocks/AAPL/quotes/latest"
    if transport is None:
        try:
            with httpx.Client(timeout=httpx.Timeout(8,connect=3),follow_redirects=False,trust_env=False) as c:
                with c.stream("GET",url,params={"feed":"iex"},headers={"APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret}) as res:
                    res.raise_for_status();data=bytearray()
                    for chunk in res.iter_bytes():
                        data.extend(chunk)
                        if len(data)>MAX_BYTES:raise PilotError("Yanıt boyutu sınırı.")
            raw=json.loads(data)
        except (httpx.HTTPError,ValueError,OSError):raise PilotError("IEX sorgusu başarısız; tekrar yok.") from None
    else:raw=transport()
    if raw.get("symbol")!="AAPL":raise PilotError("Sembol uyuşmazlığı.")
    q=raw["quote"];at=ts(q["t"]);bid,ask=dec(q["bp"]),dec(q["ap"])
    if q.get("bx")!="V" or q.get("ax")!="V" or not timedelta(0)<=clock()-at<=timedelta(seconds=30) or bid>ask:raise PilotError("IEX kotasyonu eski veya işlem yeri uyuşmuyor.")
    return {"status":"diagnostic_only","symbol":"AAPL","listed_market":"NASDAQ","feed":"iex","mic":"IEXG","source_at":at.isoformat(),"bid":str(bid),"ask":str(ask),"applied":False,"nasdaq_venue_verified":False,"live_data_verified":False,"real_orders":False,"transport_mocked":transport is not None}
