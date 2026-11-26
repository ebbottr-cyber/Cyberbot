"""Isolated SOLANA account in observed-pilot DB; operator evidence only, no wallet or network."""
import os,json,sqlite3,re
from contextlib import closing
from datetime import timedelta
from decimal import Decimal as D,InvalidOperation,ROUND_DOWN
from .observed_pilot import tx,path,utc,ts,permitted as common_permission,PilotError

VERSION="solana-observed-1"
START=D("1000")
FEE=D(".005");SLIP=D(".01");FIXED=D(".25")
RISK=D(".005");CAP=D(".05");STOP=D(".10");TARGET=D(".20")
ALPHABET="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def address(value):
    if not isinstance(value,str) or not 32<=len(value)<=44 or any(c not in ALPHABET for c in value):return False
    n=0
    for c in value:n=n*58+ALPHABET.index(c)
    return len(value)-len(value.lstrip("1"))+(n.bit_length()+7)//8==32 and n!=0

def enabled():
    return common_permission() and os.getenv("CYBERBOT_SOLANA_PILOT_ENABLED")=="1"
def config():
    mint=os.getenv("CYBERBOT_SOLANA_PILOT_MINT");pool=os.getenv("CYBERBOT_SOLANA_PILOT_POOL")
    if not address(mint) or not address(pool) or mint==pool:raise PilotError("Geçerli ve ayrı mint/havuz kimliği gerekli.")
    return mint,pool
def number(v,*,low="0",high="1000000000000"):
    try:
        n=D(str(v))
        if not n.is_finite() or not D(low)<=n<=D(high):raise ValueError()
        return n
    except (ValueError,InvalidOperation):raise PilotError("Geçersiz fiyat veya derinlik.") from None
def security(q,now,mint,pool):
    # All fields are operator assertions, never an on-chain attestation.
    s=q.get("security")
    if not isinstance(s,dict):return False
    try:
        age=(now-ts(s.get("observed_at"))).total_seconds()
        return (s.get("mint")==mint and s.get("pool")==pool and 0<=age<=300
                and s.get("legacy_token_program") is True and s.get("mint_authority_disabled") is True
                and s.get("freeze_authority_disabled") is True and s.get("transfer_restrictions_absent") is True
                and number(s.get("top10_holder_pct"),high="100")<=D(30)
                and isinstance(s.get("evidence_id"),str) and bool(re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}",s["evidence_id"])))
    except (ValueError,TypeError,ArithmeticError):return False
def validate(q,now,mint,pool):
    if not isinstance(q,dict) or (q.get("market"),q.get("mint"),q.get("pool"),q.get("currency"))!=("SOLANA",mint,pool,"USD"):raise PilotError("Mint, havuz veya para birimi uyuşmuyor.")
    source=q.get("source")
    if not isinstance(source,str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}",source):raise PilotError("Kaynak kimliği gerekli.")
    t=ts(q.get("source_at"))
    bid=number(q.get("bid"),low=".000000000001");ask=number(q.get("ask"),low=".000000000001")
    if not 0<=(now-t).total_seconds()<=30 or bid>ask:raise PilotError("Eski, gelecek veya ters fiyat.")
    liq=number(q.get("liquidity_usd"));bd=number(q.get("bid_depth_usd"));ad=number(q.get("ask_depth_usd"))
    if bd>liq or ad>liq:raise PilotError("Derinlik beyanı havuz likiditesini aşıyor.")
    passed=security(q,now,mint,pool)
    sec=q.get("security") if passed else {}
    return {"source":source,"source_at":t.isoformat(),"received_at":now.isoformat(),"bid":str(bid),"ask":str(ask),"liquidity_usd":str(liq),"bid_depth_usd":str(bd),"ask_depth_usd":str(ad),"security_gate":passed,"security_at":ts(sec["observed_at"]).isoformat() if passed else None,"security_evidence_id":sec.get("evidence_id")}
def entry_gate(q,now):
    return (q["security_gate"] and 0<=(now-ts(q["security_at"])).total_seconds()<=300
            and D(q["liquidity_usd"])>=100000 and D(q["bid_depth_usd"])>=100 and D(q["ask_depth_usd"])>=100
            and D(q["ask"])/D(q["bid"])-1<=D(".02"))
def initial(mint,pool):
    return {"version":VERSION,"market":"SOLANA","mint":mint,"pool":pool,"cash":str(START),"peak":str(START),"day":None,"day_equity":str(START),"quote":None,"position":None,"pending":None,"fills":0}
def load(db,mint,pool):
    row=db.execute("SELECT payload FROM observed_accounts WHERE market='SOLANA'").fetchone()
    s=json.loads(row[0]) if row else initial(mint,pool)
    if (s["version"],s["mint"],s["pool"])!=(VERSION,mint,pool):raise PilotError("Kayıtlı pilot mint/havuz değiştirilemez.")
    return s
def mark(s):
    pos=s["position"];q=s["quote"]
    return D(s["cash"])+(max(D(0),D(pos["qty"])*D(q["bid"])*(1-SLIP)*(1-FEE)-FIXED) if pos else D(0))
def refresh(s,now):
    e=mark(s)
    if s["day"]!=now.date().isoformat():s.update(day=now.date().isoformat(),day_equity=str(e))
    s["peak"]=str(max(D(s["peak"]),e))
def risk_ok(s):
    e=mark(s)
    return e>D(s["peak"])*D(".90") and e>D(s["day_equity"])*D(".97")
def fresh(q,now):
    return q is not None and 0<=(now-ts(q["source_at"])).total_seconds()<=30
def save(db,s,now,event,detail):
    db.execute("INSERT INTO observed_accounts VALUES('SOLANA',?) ON CONFLICT(market) DO UPDATE SET payload=excluded.payload",(json.dumps(s,allow_nan=False),))
    db.execute("INSERT INTO observed_events(market,at,event,payload) VALUES('SOLANA',?,?,?)",(now.isoformat(),event,json.dumps(detail,allow_nan=False)))
def intent(side,now,reason):
    return {"side":side,"requested_at":now.isoformat(),"expires_at":(now+timedelta(seconds=60)).isoformat() if side=="buy" else None,"reason":reason}
def request(side,*,clock=utc):
    if not enabled():raise PilotError("Solana pilotu veya izin kapalı.")
    if side not in ("buy","sell"):raise PilotError("Geçersiz istek.")
    mint,pool=config()
    with tx() as db:
        now=clock();s=load(db,mint,pool);q=s["quote"]
        if not fresh(q,now):raise PilotError("Taze gözlem gerekli.")
        if s["pending"]:raise PilotError("Bekleyen istek var.")
        refresh(s,now)
        if side=="buy" and (s["position"] or not risk_ok(s) or not entry_gate(q,now)):raise PilotError("Güvenlik, likidite veya risk kapısı.")
        if side=="sell" and not s["position"]:raise PilotError("Açık pozisyon yok.")
        s["pending"]=intent(side,now,"manual");save(db,s,now,"request",s["pending"])
        return {"status":"pending","real_orders":False}
def observe(input_quote,*,clock=utc):
    if not enabled():raise PilotError("Solana pilotu veya izin kapalı.")
    mint,pool=config()
    with tx() as db:
        now=clock();q=validate(input_quote,now,mint,pool);s=load(db,mint,pool);old=s["quote"]
        if old and (q["source"]!=old["source"] or ts(q["source_at"])<=ts(old["source_at"]) or now<ts(old["received_at"])):raise PilotError("Tekrar, sırasız gözlem veya kaynak değişikliği.")
        s["quote"]=q;refresh(s,now)
        order=s["pending"];event="observation";detail={}
        if order and order["side"]=="buy" and (now>ts(order["expires_at"]) or ts(order["requested_at"]).date()!=now.date()):
            s["pending"]=None;event="expired"
        elif order and ts(q["source_at"])>ts(order["requested_at"]):
            if order["side"]=="buy":
                s["pending"]=None;event="entry_rejected"
                if not s["position"] and risk_ok(s) and entry_gate(q,now):
                    e=mark(s);entry=D(q["ask"])*(1+SLIP);stop=entry*(1-STOP)
                    loss=entry*(1+FEE)-stop*(1-SLIP)*(1-FEE)
                    budget=min(e*CAP,D(q["liquidity_usd"])*D(".001"),D(q["ask_depth_usd"]),D(q["bid_depth_usd"]))
                    qty=min((e*RISK-2*FIXED)/loss,(budget-FIXED)/(entry*(1+FEE)),(D(s["cash"])-FIXED)/(entry*(1+FEE))).quantize(D(".000000001"),rounding=ROUND_DOWN)
                    if qty>0:
                        cost=qty*entry*(1+FEE)+FIXED;s["cash"]=str(D(s["cash"])-cost)
                        s["position"]={"qty":str(qty),"cost":str(cost),"entry":str(entry),"stop":str(stop),"target":str(entry*(1+TARGET)),"opened_at":now.isoformat()}
                        detail=dict(s["position"]);event="buy_fill"
            elif s["position"]:
                pos=s["position"];qty=D(pos["qty"])
                # Never infer available execution depth from pool TVL.
                if qty*D(q["bid"])<=D(q["bid_depth_usd"]) and D(q["bid_depth_usd"])>0:
                    exit_price=D(q["bid"])*(1-SLIP);proceeds=max(D(0),qty*exit_price*(1-FEE)-FIXED)
                    s["cash"]=str(D(s["cash"])+proceeds);s["position"]=None;s["pending"]=None
                    detail={"pnl":str(proceeds-D(pos["cost"])),"exit":str(exit_price),"reason":order["reason"]};event="sell_fill"
                else:event="exit_waiting_depth"
            if event.endswith("_fill"):s["fills"]+=1
        if s["position"] and not s["pending"]:
            p=s["position"];bid=D(q["bid"])
            reason="security_or_liquidity" if not entry_gate(q,now) else "stop" if bid<=D(p["stop"]) else "target" if bid>=D(p["target"]) else None
            if reason:s["pending"]=intent("sell",now,reason)
        refresh(s,now);save(db,s,now,event,{"quote":q,"result":detail,"pending":s["pending"]})
        return {"status":event,"pending":s["pending"],"real_orders":False}
def snapshot(*,clock=utc):
    result={"market":"SOLANA","currency":"USD","initial_capital":str(START),"enabled":enabled(),"configured":False,"initialized":False,"equity":None,"cash":None,"position_open":None,"pending":None,"quote_fresh":False,"entry_gate":False,"security_verified":False,"live_data_verified":False,"real_orders":False}
    if not enabled():return result
    try:mint,pool=config()
    except PilotError:return result
    result.update(configured=True,mint=mint,pool=pool)
    p=path()
    if not p.is_file():return result
    with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
        db.execute("PRAGMA query_only=ON")
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='observed_accounts'").fetchone() or not db.execute("SELECT 1 FROM observed_accounts WHERE market='SOLANA'").fetchone():return result
        s=load(db,mint,pool)
    now=clock();q=s["quote"];valid=fresh(q,now)
    depth_ok=not s["position"] or D(s["position"]["qty"])*D(q["bid"])<=D(q["bid_depth_usd"])
    result.update(initialized=True,cash=s["cash"],equity=str(mark(s)) if valid and depth_ok else None,position_open=bool(s["position"]),pending=s["pending"],quote_fresh=valid,entry_gate=valid and entry_gate(q,now),fills=s["fills"],last_quote_at=q["source_at"],valuation_depth_asserted=depth_ok)
    return result
