"""Opt-in observed-quote paper pilot. No exchange integration or automatic entry."""
import json,os,sqlite3,re
from contextlib import closing,contextmanager
from datetime import datetime,timezone,timedelta
from decimal import Decimal as D,InvalidOperation,ROUND_DOWN
from .db_paths import checked,pilot_path
from .engine import FEE,SLIP,RISK,STOP,TARGET,MAX_NOTIONAL,DAILY_LOSS,MAX_DRAWDOWN

VERSION="observed-pilot-1"
ACCOUNTS={"BIST":("THYAO.IS","TRY",D("45000")),"NASDAQ":("AAPL","USD",D("1000")),"XETRA":("SAP.DE","USD",D("1000"))}
MAX_AGE=30
FX_MAX_SKEW=10
ORDER_TTL=60
class PilotError(ValueError):pass
def utc():return datetime.now(timezone.utc)
def ts(x):
    try:
        t=datetime.fromisoformat(x.replace("Z","+00:00"))
        if t.tzinfo is None:raise ValueError()
        return t.astimezone(timezone.utc)
    except (ValueError,TypeError,AttributeError,OverflowError):raise PilotError("Saat dilimli zaman gerekli.") from None
def dec(x):
    try:
        v=D(str(x))
        if not v.is_finite() or not D(".00000001")<=v<=D("1000000000"):raise ValueError()
        return v
    except (ValueError,InvalidOperation):raise PilotError("Geçersiz fiyat.") from None
def permitted():
    return os.getenv("CYBERBOT_OBSERVED_PILOT_ENABLED")=="1" and os.getenv("CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED")=="1"
def path():
    checked()
    return pilot_path()
def account(m):
    if m not in ACCOUNTS:raise PilotError("Pilot yalnız BIST, NASDAQ ve XETRA örnek sembollerini destekliyor.")
    return ACCOUNTS[m]
def fx_permitted():
    return os.getenv("CYBERBOT_OBSERVED_FX_RIGHTS_CONFIRMED")=="1"
def quote_currency(m):
    return "EUR" if m=="XETRA" else account(m)[1]
def fresh(q,now,m):
    return q is not None and 0<=(now-ts(q["source_at"])).total_seconds()<=MAX_AGE and (m!="XETRA" or (fx_permitted() and q.get("fx") is not None and 0<=(now-ts(q["fx"]["source_at"])).total_seconds()<=MAX_AGE))
def rate(q,side):
    return D(q["fx"][side]) if "fx" in q else D(1)
def validate_fx(q,now,stock_time):
    if not fx_permitted():raise PilotError("EUR/USD kullanım izni kapalı.")
    fx=q.get("fx")
    if not isinstance(fx,dict) or fx.get("pair")!="EUR/USD":raise PilotError("EUR/USD alış/satış gözlemi gerekli.")
    source=fx.get("source")
    if not isinstance(source,str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}",source):raise PilotError("Kur kaynak kimliği gerekli.")
    t=ts(fx.get("source_at"));bid,ask=dec(fx.get("bid")),dec(fx.get("ask"))
    if not 0<=(now-t).total_seconds()<=MAX_AGE or abs((t-stock_time).total_seconds())>FX_MAX_SKEW or not D(".1")<=bid<=ask<=D("10") or ask/bid-1>D(".01"):raise PilotError("Kur eski, uyumsuz, gelecekte veya spread geniş.")
    return {"pair":"EUR/USD","source":source,"source_at":t.isoformat(),"bid":str(bid),"ask":str(ask)}
def initial(m):
    symbol,cur,start=account(m)
    return {"version":VERSION,"market":m,"symbol":symbol,"currency":cur,"initial_capital":str(start),"cash":str(start),"peak":str(start),"day":None,"day_equity":str(start),"quote":None,"position":None,"pending":None,"last_event":None,"fills":0}
def equity(s):
    p=s["position"]
    return D(s["cash"])+(D(p["quantity"])*D(s["quote"]["bid"])*(1-SLIP)*(1-FEE)*rate(s["quote"],"bid") if p else D(0))
def blocked(s):
    e=equity(s)
    return e<=D(s["peak"])*(1-MAX_DRAWDOWN) or e<=D(s["day_equity"])*(1-DAILY_LOSS)
def refresh(s,now):
    e=equity(s);d=now.date().isoformat()
    if s["day"]!=d:
        # First observation of UTC day; no implied session-open price.
        s.update(day=d,day_equity=str(e))
    s["peak"]=str(max(D(s["peak"]),e))
def validate(m,q,now):
    symbol,cur,_=account(m)
    if not isinstance(q,dict) or q.get("symbol")!=symbol or q.get("currency")!=quote_currency(m) or q.get("market")!=m:raise PilotError("Piyasa, sembol veya para birimi uyuşmuyor.")
    source=q.get("source")
    if not isinstance(source,str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}",source):raise PilotError("Kaynak kimliği gerekli.")
    if q.get("session_open") is not True:raise PilotError("Açık seans beyanı gerekli; gerçek borsa takvimi doğrulanmadı.")
    t=ts(q.get("source_at"));bid,ask=dec(q.get("bid")),dec(q.get("ask"))
    if not 0<=(now-t).total_seconds()<=MAX_AGE or ask<bid or ask/bid-1>D(".02"):raise PilotError("Eski/gelecek fiyat veya geniş alış-satış farkı.")
    result={"source":source,"source_at":t.isoformat(),"received_at":now.isoformat(),"bid":str(bid),"ask":str(ask),"session_asserted_open":True}
    if "venue" in q or "bid_size" in q or "ask_size" in q or "session_reference" in q:
        if q.get("venue")!={"BIST":"XIST","NASDAQ":"XNAS","XETRA":"XETR"}[m] or not isinstance(q.get("session_reference"),str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}",q["session_reference"]):raise PilotError("İşlem yeri veya seans kanıtı eksik.")
        result.update(venue=q["venue"],session_reference=q["session_reference"],bid_size=str(dec(q.get("bid_size"))),ask_size=str(dec(q.get("ask_size"))))
    if m=="XETRA":result["fx"]=validate_fx(q,now,t)
    elif "fx" in q:raise PilotError("Bu hesapta kur girdisi kullanılmaz.")
    return result
@contextmanager
def tx():
    if not permitted():raise PilotError("Pilot ve veri kullanım izni kapalı.")
    p=path();p.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(p,timeout=5,isolation_level=None)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            tables={x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables-{"observed_accounts","observed_events"}:raise PilotError("Pilot veritabanı şeması uyumsuz.")
            db.execute("CREATE TABLE IF NOT EXISTS observed_accounts(market TEXT PRIMARY KEY,payload TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS observed_events(id INTEGER PRIMARY KEY,market TEXT NOT NULL,at TEXT NOT NULL,event TEXT NOT NULL,payload TEXT NOT NULL)")
            yield db;db.commit()
        except BaseException:db.rollback();raise
def load(db,m):
    row=db.execute("SELECT payload FROM observed_accounts WHERE market=?",(m,)).fetchone()
    s=json.loads(row[0]) if row else initial(m)
    if (s["version"],s["market"],s["symbol"],s["currency"])!=(VERSION,m,*account(m)[:2]):raise PilotError("Pilot hesap kimliği uyuşmuyor.")
    return s
def save(db,s,now,event,detail=None):
    s["last_event"]=event
    db.execute("INSERT INTO observed_accounts VALUES(?,?) ON CONFLICT(market) DO UPDATE SET payload=excluded.payload",(s["market"],json.dumps(s,allow_nan=False)))
    db.execute("INSERT INTO observed_events(market,at,event,payload) VALUES(?,?,?,?)",(s["market"],now.isoformat(),event,json.dumps(detail or {},allow_nan=False)))
def request(m,side,*,clock=utc):
    account(m)
    if side not in ("buy","sell"):raise PilotError("Geçersiz sanal istek.")
    with tx() as db:
        now=clock();s=load(db,m)
        if not fresh(s["quote"],now,m):raise PilotError("Taze alış/satış fiyatı gerekli.")
        if s["pending"]:raise PilotError("Bekleyen istek var.")
        refresh(s,now)
        if side=="buy" and (s["position"] or blocked(s)):raise PilotError("Pozisyon veya risk sınırı.")
        if side=="sell" and not s["position"]:raise PilotError("Açık pozisyon yok.")
        s["pending"]={"side":side,"requested_at":now.isoformat(),"reason":"manual","expires_at":(now+timedelta(seconds=ORDER_TTL)).isoformat()}
        save(db,s,now,"request",s["pending"])
        return {"status":"pending","market":m,"real_orders":False}
def observe(m,input_quote,*,clock=utc):
    account(m)
    with tx() as db:
        now=clock();q=validate(m,input_quote,now);s=load(db,m);old=s["quote"]
        if old and (q["source"]!=old["source"] or ts(q["source_at"])<=ts(old["source_at"]) or ts(q["received_at"])<ts(old["received_at"])):raise PilotError("Kaynak değişikliği veya tekrar/sırasız gözlem.")
        if old and old.get("venue")!=q.get("venue"):raise PilotError("Kotasyon kapsamı değiştirilemez.")
        if m=="XETRA" and old:
            prior,new=old["fx"],q["fx"]
            if new["source"]!=prior["source"] or ts(new["source_at"])<ts(prior["source_at"]) or (new["source_at"]==prior["source_at"] and new!=prior):raise PilotError("Kur kaynağı değişti veya zaman/fiyat tutarsız.")
        s["quote"]=q;refresh(s,now)
        pending=s["pending"];event="observation";detail={}
        if pending:
            if pending["side"]=="buy" and (now>ts(pending["expires_at"]) or ts(pending["requested_at"]).date()!=now.date()):
                s["pending"]=None;event="expired"
            elif ts(q["source_at"])>ts(pending["requested_at"]) and (m!="XETRA" or ts(q["fx"]["source_at"])>ts(pending["requested_at"])):
                s["pending"]=None
                if pending["side"]=="buy" and not s["position"] and not blocked(s):
                    entry=D(q["ask"])*(1+SLIP);stop=entry*(1-STOP);e=equity(s)
                    entry_usd_or_native=entry*rate(q,"ask")
                    loss=entry_usd_or_native*(1+FEE)-stop*(1-SLIP)*(1-FEE)*rate(q,"bid")
                    qty=min(e*RISK/loss,e*MAX_NOTIONAL/entry_usd_or_native,D(s["cash"])/(entry_usd_or_native*(1+FEE))).quantize(D("1") if m=="XETRA" else D(".000001"),rounding=ROUND_DOWN)
                    if "ask_size" in q:qty=min(qty,D(q["ask_size"]),D(q["bid_size"])).quantize(D("1"),rounding=ROUND_DOWN)
                    if qty>0:
                        cost=qty*entry_usd_or_native*(1+FEE);s["cash"]=str(D(s["cash"])-cost)
                        s["position"]={"quantity":str(qty),"entry":str(entry),"cost":str(cost),"stop":str(stop),"target":str(entry*(1+TARGET)),"opened_at":now.isoformat(),"price_currency":quote_currency(m),"entry_conversion_rate":str(rate(q,"ask"))}
                        detail=dict(s["position"]);event="buy_fill"
                    else:event="risk_rejected"
                elif pending["side"]=="sell" and s["position"] and ("bid_size" not in q or D(s["position"]["quantity"])<=D(q["bid_size"])):
                    pos=s["position"];exit_price=D(q["bid"])*(1-SLIP);proceeds=D(pos["quantity"])*exit_price*(1-FEE)*rate(q,"bid")
                    s["cash"]=str(D(s["cash"])+proceeds);s["position"]=None
                    detail={"quantity":pos["quantity"],"exit":str(exit_price),"pnl":str(proceeds-D(pos["cost"])),"reason":pending["reason"],"price_currency":quote_currency(m),"exit_conversion_rate":str(rate(q,"bid"))};event="sell_fill"
                elif pending["side"]=="sell" and s["position"]:
                    s["pending"]=pending;event="exit_waiting_depth"
                else:event="risk_rejected"
                if event.endswith("_fill"):s["fills"]+=1
        p=s["position"]
        if p and s["pending"] is None:
            bid=D(q["bid"]);reason="stop" if bid<=D(p["stop"]) else "target" if bid>=D(p["target"]) else None
            if reason:
                s["pending"]={"side":"sell","requested_at":now.isoformat(),"expires_at":(now+timedelta(seconds=ORDER_TTL)).isoformat(),"reason":reason}
        refresh(s,now);save(db,s,now,event,{"quote":q,"result":detail,"pending":s["pending"]})
        return {"status":event,"market":m,"pending":s["pending"],"real_orders":False}
def snapshot(*,clock=utc):
    now=clock();p=path();result={"version":VERSION,"enabled":permitted(),"mode":"operator_observed_unverified","accounts":[],"live_data_verified":False,"exchange_execution_verified":False,"real_orders":False,"bulk_price_download_enabled":False,"automatic_entry_enabled":False}
    for m in ACCOUNTS:
        s=initial(m);exists=False
        if p.is_file():
            with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
                db.execute("PRAGMA query_only=ON")
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='observed_accounts'").fetchone():
                    s=load(db,m);exists=bool(db.execute("SELECT 1 FROM observed_accounts WHERE market=?",(m,)).fetchone())
        is_fresh=permitted() and fresh(s["quote"],now,m) and (not s["position"] or "bid_size" not in s["quote"] or D(s["position"]["quantity"])<=D(s["quote"]["bid_size"]))
        result["accounts"].append({"market":m,"symbol":s["symbol"],"currency":s["currency"],"price_currency":quote_currency(m),"fx_required":m=="XETRA","fx_rights_confirmed":fx_permitted() if m=="XETRA" else None,"last_fx_at":s["quote"]["fx"]["source_at"] if permitted() and fx_permitted() and m=="XETRA" and s["quote"] else None,"initial_capital":s["initial_capital"],"initialized":exists,"cash":s["cash"] if permitted() and exists else None,"equity":str(equity(s)) if is_fresh else None,"quote_fresh":is_fresh,"last_quote_at":s["quote"]["source_at"] if permitted() and s["quote"] else None,"position_open":bool(s["position"]) if permitted() else None,"pending":s["pending"] if permitted() else None,"fills":s["fills"] if permitted() else None})
    return result
