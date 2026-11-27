"""Operator-observed isolated USDT perpetual simulation. No exchange or order API."""
import os,json,re,sqlite3
from contextlib import closing
from datetime import datetime,timezone,timedelta
from decimal import Decimal as D,ROUND_DOWN,InvalidOperation
from .observed_pilot import tx,path,utc,ts,dec,permitted as common_permission,PilotError
from .futures import START,FEE,SLIP,LEVERAGE,MMR
from .pilot_control import halted

VERSION="futures-observed-1"
FUNDING_PERIOD=8*3600
MAX_FUNDING_EVENTS=24
MAX_AGE=30
RISK=D(".005");MARGIN_CAP=D(".10");STOP=D(".05");TARGET=D(".10")
def enabled():
    return common_permission() and os.getenv("CYBERBOT_FUTURES_PILOT_ENABLED")=="1"
def symbol():
    s=os.getenv("CYBERBOT_FUTURES_PILOT_SYMBOL","BTCUSDT")
    if s not in ("BTCUSDT","ETHUSDT"):raise PilotError("Geçersiz pilot sözleşmesi.")
    return s
def number(x,lo,hi):
    try:
        n=D(str(x))
        if not n.is_finite() or not D(lo)<=n<=D(hi):raise ValueError()
        return n
    except (ValueError,InvalidOperation):raise PilotError("Geçersiz sayısal gözlem.") from None
def validate(q,now,sym):
    if not isinstance(q,dict) or (q.get("market"),q.get("symbol"),q.get("currency"),q.get("contract"))!=("FUTURES",sym,"USDT","linear_perpetual"):raise PilotError("Sözleşme kimliği uyuşmuyor.")
    source=q.get("source")
    if not isinstance(source,str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}",source):raise PilotError("Kaynak kimliği gerekli.")
    t=ts(q.get("source_at"));bid,ask,mark=(dec(q.get(k)) for k in ("bid","ask","mark"))
    if not 0<=(now-t).total_seconds()<=MAX_AGE or bid>ask:raise PilotError("Eski/gelecek veya ters fiyat.")
    bd=number(q.get("bid_depth_usdt"),"0","1000000000");ad=number(q.get("ask_depth_usdt"),"0","1000000000")
    funding=q.get("funding",[])
    if not isinstance(funding,list) or len(funding)>MAX_FUNDING_EVENTS:raise PilotError("Fonlama olay sınırı.")
    return {"source":source,"source_at":t.isoformat(),"received_at":now.isoformat(),"bid":str(bid),"ask":str(ask),"mark":str(mark),"bid_depth_usdt":str(bd),"ask_depth_usdt":str(ad)},funding
def boundaries(old,new):
    a=ts(old).timestamp();b=ts(new).timestamp()
    first=(int(a//FUNDING_PERIOD)+1)*FUNDING_PERIOD;last=int(b//FUNDING_PERIOD)*FUNDING_PERIOD
    count=max(0,(last-first)//FUNDING_PERIOD+1)
    if count>MAX_FUNDING_EVENTS:raise PilotError("Fonlama boşluğu çok uzun; manuel inceleme gerekli.")
    return [datetime.fromtimestamp(first+i*FUNDING_PERIOD,timezone.utc) for i in range(count)]
def funding_records(raw,expected,source,sym):
    if len(raw)!=len(expected):raise PilotError("Fonlama gözlemi eksik veya fazladan; durum ilerletilmedi.")
    out=[]
    for x,t in zip(raw,expected):
        if not isinstance(x,dict) or x.get("source")!=source or x.get("symbol")!=sym or ts(x.get("settled_at"))!=t:raise PilotError("Fonlama zaman/kaynak uyuşmazlığı.")
        out.append({"settled_at":t.isoformat(),"rate":str(number(x.get("rate"),"-.01",".01")),"mark":str(dec(x.get("mark"))),"source":source,"symbol":sym})
    return out
def initial(sym):
    return {"version":VERSION,"symbol":sym,"cash":str(START),"peak":str(START),"day":None,"day_equity":str(START),"quote":None,"position":None,"pending":None,"fills":0,"liquidations":0,"gap_count":0,"funding_events":0}
def load(db,sym):
    row=db.execute("SELECT payload FROM observed_accounts WHERE market='FUTURES'").fetchone()
    s=json.loads(row[0]) if row else initial(sym)
    if (s["version"],s["symbol"])!=(VERSION,sym):raise PilotError("Pilot sözleşmesi değiştirilemez.")
    return s
def sign(p):return D(1) if p["side"]=="LONG" else D(-1)
def residual(p,price):
    return D(p["margin"])+D(p["qty"])*sign(p)*(price-D(p["entry"]))+D(p["funding"])
def liquidation(p,mark):
    return residual(p,mark)<=D(p["qty"])*mark*(MMR+FEE)
def exit_price(p,q):
    return D(q["bid"])*(1-SLIP) if sign(p)>0 else D(q["ask"])*(1+SLIP)
def equity(s):
    p=s["position"]
    if not p:return D(s["cash"])
    q=s["quote"];price=exit_price(p,q)
    return D(s["cash"])+max(D(0),residual(p,price)-D(p["qty"])*price*FEE)
def refresh(s,now):
    e=equity(s)
    if s["day"]!=now.date().isoformat():
        # First observable daily mark, not a guaranteed UTC midnight balance.
        s.update(day=now.date().isoformat(),day_equity=str(e))
    s["peak"]=str(max(D(s["peak"]),e))
def risk_ok(s):
    e=equity(s);return e>D(s["peak"])*D(".90") and e>D(s["day_equity"])*D(".97")
def entry_risk_budget(s):
    e=equity(s)
    return max(D(0),min(e*RISK,e-D(s["peak"])*D(".90"),e-D(s["day_equity"])*D(".97")))
def fresh(q,now):
    return q is not None and 0<=(now-ts(q["source_at"])).total_seconds()<=MAX_AGE
def entry_gate(q):
    return D(q["ask"])/D(q["bid"])-1<=D(".005") and D(q["bid_depth_usdt"])>=100 and D(q["ask_depth_usdt"])>=100 and D(".98")<=D(q["mark"])/((D(q["bid"])+D(q["ask"]))/2)<=D("1.02")
def save(db,s,now,event,detail):
    db.execute("INSERT INTO observed_accounts VALUES('FUTURES',?) ON CONFLICT(market) DO UPDATE SET payload=excluded.payload",(json.dumps(s,allow_nan=False),))
    db.execute("INSERT INTO observed_events(market,at,event,payload) VALUES('FUTURES',?,?,?)",(now.isoformat(),event,json.dumps(detail,allow_nan=False)))
def intent(side,now,reason):
    return {"side":side,"requested_at":now.isoformat(),"expires_at":(now+timedelta(seconds=60)).isoformat() if side!="CLOSE" else None,"reason":reason}
def request(side,*,clock=utc):
    if not enabled():raise PilotError("Futures pilotu veya veri izni kapalı.")
    if side not in ("LONG","SHORT","CLOSE"):raise PilotError("Geçersiz yön.")
    sym=symbol()
    with tx() as db:
        now=clock();s=load(db,sym);q=s["quote"]
        if not fresh(q,now) or (s["position"] and boundaries(q["source_at"],now.isoformat())):raise PilotError("Güncel fiyat/fonlama gerekli.")
        if s["pending"]:raise PilotError("Bekleyen istek var.")
        refresh(s,now)
        if side=="CLOSE":
            if not s["position"]:raise PilotError("Pozisyon yok.")
        elif halted(db) or s["position"] or not risk_ok(s) or not entry_gate(q):raise PilotError("Giriş/risk kapısı kapalı.")
        s["pending"]=intent(side,now,"manual");save(db,s,now,"request",s["pending"])
        return {"status":"pending","real_orders":False}
def settle(s,reason,price,*,liquidated=False):
    p=s["position"];qty=D(p["qty"])
    recovered=D(0) if liquidated else max(D(0),residual(p,price)-qty*price*FEE)
    s["cash"]=str(D(s["cash"])+recovered);s["position"]=None;s["pending"]=None
    if liquidated:s["liquidations"]+=1
    else:s["fills"]+=1
    return {"reason":reason,"observed_price":str(price),"pnl":str(recovered-D(p["margin"])-D(p["entry_fee"])),"funding":p["funding"],"isolated_loss_capped":True,"exchange_execution_verified":False}
def observe(input_quote,*,clock=utc):
    if not enabled():raise PilotError("Futures pilotu veya veri izni kapalı.")
    sym=symbol()
    with tx() as db:
        now=clock();q,raw=validate(input_quote,now,sym);s=load(db,sym);old=s["quote"]
        if old and (q["source"]!=old["source"] or ts(q["source_at"])<=ts(old["source_at"]) or now<ts(old["received_at"])):raise PilotError("Sırasız/tekrar gözlem veya kaynak değişikliği.")
        p=s["position"]
        expected=boundaries(old["source_at"],q["source_at"]) if p else []
        records=funding_records(raw,expected,q["source"],sym)
        if p and (ts(q["source_at"])-ts(old["source_at"])).total_seconds()>MAX_AGE:s["gap_count"]+=1
        s["quote"]=q;event="observation";detail={};applied=[]
        for item in records:
            p=s["position"]
            if not p:break
            mark=D(item["mark"]);amount=-sign(p)*D(p["qty"])*mark*D(item["rate"])
            p["funding"]=str(D(p["funding"])+amount);s["funding_events"]+=1
            applied.append({**item,"amount_usdt":str(amount)})
            if liquidation(p,mark):
                detail=settle(s,"funding_boundary_liquidation",mark,liquidated=True);event="model_liquidation";break
        if s["position"] and liquidation(s["position"],D(q["mark"])):
            detail=settle(s,"mark_liquidation",D(q["mark"]),liquidated=True);event="model_liquidation"
        refresh(s,now)
        order=s["pending"]
        if order and order["side"]!="CLOSE" and halted(db):
            s["pending"]=None;event="entry_cancelled"
        elif order and order["side"]!="CLOSE" and (now>ts(order["expires_at"]) or ts(order["requested_at"]).date()!=now.date()):
            s["pending"]=None;event="expired"
        elif order and ts(q["source_at"])>ts(order["requested_at"]):
            if order["side"]=="CLOSE":
                p=s["position"]
                depth=D(q["bid_depth_usdt"] if sign(p)>0 else q["ask_depth_usdt"])
                book=D(q["bid"] if sign(p)>0 else q["ask"])
                if D(p["qty"])*book<=depth:
                    detail=settle(s,order["reason"],exit_price(p,q));event="close_fill"
                else:event="exit_waiting_depth"
            else:
                s["pending"]=None;event="entry_rejected"
                if not s["position"] and risk_ok(s) and entry_gate(q):
                    direction=D(1) if order["side"]=="LONG" else D(-1)
                    book=D(q["ask"] if direction>0 else q["bid"]);entry=book*(1+direction*SLIP)
                    stop=entry*(1-direction*STOP);exit_stop=stop*(1-direction*SLIP)
                    loss=abs(entry-exit_stop)+FEE*(entry+exit_stop)
                    e=equity(s);depth=min(D(q["bid_depth_usdt"]),D(q["ask_depth_usdt"]))
                    qty=min(entry_risk_budget(s)/loss,e*MARGIN_CAP*LEVERAGE/entry,D(s["cash"])/(entry*(1/LEVERAGE+FEE)),depth/max(D(q["ask"]),entry)).quantize(D(".000001"),rounding=ROUND_DOWN)
                    if qty>0:
                        margin=qty*entry/LEVERAGE;fee=qty*entry*FEE
                        s["cash"]=str(D(s["cash"])-margin-fee)
                        s["position"]={"side":order["side"],"qty":str(qty),"entry":str(entry),"margin":str(margin),"entry_fee":str(fee),"funding":"0","opened_at":q["source_at"]}
                        s["fills"]+=1;event="open_fill";detail=dict(s["position"])
        p=s["position"]
        if p and not s["pending"]:
            move=sign(p)*(D(q["mark"])/D(p["entry"])-1)
            if move<=-STOP or move>=TARGET:s["pending"]=intent("CLOSE",now,"stop" if move<=-STOP else "target")
        refresh(s,now);save(db,s,now,event,{"quote":q,"funding_applied":applied,"funding_supplied":records,"result":detail,"pending":s["pending"]})
        return {"status":event,"pending":s["pending"],"real_orders":False}
def snapshot(*,clock=utc):
    result={"market":"FUTURES","currency":"USDT","initial_capital":str(START),"enabled":enabled(),"initialized":False,"equity":None,"cash":None,"quote_fresh":False,"funding_due":None,"position":None,"pending":None,"leverage":2,"funding_model":"assumed_8h_utc","liquidation_model":"simplified_isolated_mark","exchange_execution_verified":False,"live_data_verified":False,"real_orders":False}
    if not enabled():return result
    sym=symbol();result["symbol"]=sym;p=path()
    if not p.is_file():return result
    with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
        db.execute("PRAGMA query_only=ON")
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='observed_accounts'").fetchone() or not db.execute("SELECT 1 FROM observed_accounts WHERE market='FUTURES'").fetchone():return result
        s=load(db,sym)
    now=clock();q=s["quote"];pos=s["position"];valid=fresh(q,now)
    due=bool(pos and (int(now.timestamp()//FUNDING_PERIOD)>int(ts(q["source_at"]).timestamp()//FUNDING_PERIOD)))
    depth_ok=not pos or D(pos["qty"])*D(q["bid"] if sign(pos)>0 else q["ask"])<=D(q["bid_depth_usdt"] if sign(pos)>0 else q["ask_depth_usdt"])
    result.update(initialized=True,cash=s["cash"],equity=str(equity(s)) if valid and not due and depth_ok else None,quote_fresh=valid,funding_due=due,position=pos,pending=s["pending"],fills=s["fills"],liquidations=s["liquidations"],gap_count=s["gap_count"],funding_events=s["funding_events"],last_quote_at=q["source_at"],valuation_depth_asserted=depth_ok)
    return result
