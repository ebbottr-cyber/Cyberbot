"""Independent synthetic USDT perpetual simulation; no exchange connection."""
import os,json,sqlite3
from contextlib import contextmanager
from decimal import Decimal as D
from pathlib import Path
from datetime import datetime,timezone
from .engine import PaperError
START=D("1000"); FEE=D(".0006"); SLIP=D(".001"); LEVERAGE=D(2); MMR=D(".005"); FUNDING=D(".0001")
SERIES={"BTCUSDT":tuple(map(D,("60000","61000","59000","63000","57000","62000","65000","31000","33000","32000","35000","34000"))),
        "ETHUSDT":tuple(map(D,("3000","3020","2900","3150","2800","3100","3300","1700","1800","1750","1900","1850")))}
def path_for(base=None):
    from .db_paths import checked
    return checked(base)["futures"]
def day():return datetime.now(timezone.utc).date().isoformat()
def fmt(x):return str(D(x).quantize(D(".01")))
class Futures:
    def __init__(self,path,*,series=None,day_clock=None):
        self.series=SERIES if series is None else series
        if set(self.series)!=set(SERIES) or len({len(v) for v in self.series.values()})!=1 or not 2<=len(self.series['BTCUSDT'])<=360 or any(not p.is_finite() or p<=0 for v in self.series.values() for p in v):raise ValueError('Invalid synthetic series.')
        self.day_clock=day_clock or day
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.tx() as db:
            db.execute("CREATE TABLE IF NOT EXISTS futures_state(id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT NOT NULL)")
            db.execute("INSERT OR IGNORE INTO futures_state VALUES(1,?)",(json.dumps({"cash":str(START),"tick":0,"peak":str(START),"max_dd":"0","day":self.day_clock(),"day_equity":str(START),"trades":[]}),))
    @contextmanager
    def tx(self):
        db=sqlite3.connect(self.path,timeout=10,isolation_level=None)
        try:
            db.execute("BEGIN IMMEDIATE");yield db;db.commit()
        except BaseException:
            db.rollback();raise
        finally:db.close()
    def load(self,db):return json.loads(db.execute("SELECT payload FROM futures_state WHERE id=1").fetchone()[0])
    def save(self,db,s):db.execute("UPDATE futures_state SET payload=? WHERE id=1",(json.dumps(s,allow_nan=False),))
    def price(self,s,t):return self.series[t["symbol"]][s["tick"]]
    def position(self,s):return next((t for t in s["trades"] if t["exit"] is None),None)
    def residual(self,s,t):
        p=self.price(s,t);sign=D(1) if t["side"]=="LONG" else D(-1)
        exit_price=p*(1-sign*SLIP);q=D(t["quantity"])
        return D(t["margin"])+q*sign*(exit_price-D(t["entry"]))-q*exit_price*FEE+D(t["funding"])
    def equity(self,s):
        t=self.position(s)
        return D(s["cash"])+(max(D(0),self.residual(s,t)) if t else D(0))
    def refresh(self,s):
        e=self.equity(s)
        if s["day"]!=self.day_clock():s.update(day=self.day_clock(),day_equity=str(e))
        peak=max(D(s["peak"]),e);s["peak"]=str(peak)
        s["max_dd"]=str(max(D(s["max_dd"]),1-e/peak))
        return e
    def open(self,symbol,side):
        if symbol not in self.series or side not in ("LONG","SHORT"):raise PaperError("Geçersiz sözleşme veya yön.")
        with self.tx() as db:
            s=self.load(db);e=self.refresh(s)
            if self.position(s):raise PaperError("En fazla bir açık Futures pozisyonu.")
            if e<=D(s["peak"])*D(".90") or e<=D(s["day_equity"])*D(".97"):raise PaperError("Risk sınırı.")
            if s["tick"]>=len(self.series[symbol])-1:raise PaperError("Sentetik seri tamamlandı.")
            p=self.series[symbol][s["tick"]];sign=D(1) if side=="LONG" else D(-1);entry=p*(1+sign*SLIP)
            stop=entry*(1-sign*D(".05"));exit_stop=stop*(1-sign*SLIP)
            risk_per_unit=abs(entry-exit_stop)+entry*FEE+exit_stop*FEE
            q=min(e*D(".005")/risk_per_unit,e*D(".10")*LEVERAGE/entry,D(s["cash"])/(entry*(1/LEVERAGE+FEE)))
            if q<=0:raise PaperError("Yetersiz bakiye.")
            margin=q*entry/LEVERAGE;fee=q*entry*FEE
            s["cash"]=str(D(s["cash"])-margin-fee)
            s["trades"].append({"id":len(s["trades"])+1,"symbol":symbol,"side":side,"entry":str(entry),"quantity":str(q),"margin":str(margin),"entry_fee":str(fee),"funding":"0","opened_tick":s["tick"],"exit":None,"pnl":None,"reason":None})
            self.refresh(s);self.save(db,s)
    def settle(self,s,t,reason):
        sign=D(1) if t["side"]=="LONG" else D(-1)
        p=self.price(s,t)*(1-sign*SLIP)
        recovered=D(0) if reason=="synthetic_liquidation" else max(D(0),self.residual(s,t))
        s["cash"]=str(D(s["cash"])+recovered)
        t.update(exit=str(p),closed_tick=s["tick"],reason=reason,pnl=str(recovered-D(t["margin"])-D(t["entry_fee"])))
    def close(self,trade_id):
        with self.tx() as db:
            s=self.load(db);self.refresh(s);t=self.position(s)
            if t is None or t["id"]!=trade_id:raise PaperError("Açık pozisyon bulunamadı.")
            self.settle(s,t,"manual");self.refresh(s);self.save(db,s)
    def advance(self):
        with self.tx() as db:
            s=self.load(db);self.refresh(s)
            if s["tick"]>=len(self.series["BTCUSDT"])-1:raise PaperError("Sentetik seri tamamlandı.")
            s["tick"]+=1;t=self.position(s)
            if t:
                p=self.price(s,t);sign=D(1) if t["side"]=="LONG" else D(-1)
                if s["tick"]%3==0:t["funding"]=str(D(t["funding"])-sign*D(t["quantity"])*p*FUNDING)
                move=sign*(p/D(t["entry"])-1)
                if self.residual(s,t)<=D(t["quantity"])*p*MMR:self.settle(s,t,"synthetic_liquidation")
                elif move<=-D(".05"):self.settle(s,t,"stop")
                elif move>=D(".10"):self.settle(s,t,"target")
            self.refresh(s);self.save(db,s)
    def snapshot(self):
        with self.tx() as db:
            s=self.load(db);e=self.refresh(s);self.save(db,s);t=self.position(s)
            return {"market":"FUTURES","mode":"synthetic_futures","currency":"USDT","initial_equity":str(START),"cash":fmt(s["cash"]),"equity":fmt(e),"pnl":fmt(e-START),"daily_pnl":fmt(e-D(s["day_equity"])),"max_recorded_drawdown_pct":fmt(D(s["max_dd"])*100),"drawdown_pct":fmt((1-e/D(s["peak"]))*100),"day_start_equity":fmt(s["day_equity"]),"open_count":int(t is not None),"tick":s["tick"],"last_tick":len(self.series["BTCUSDT"])-1,"trades":s["trades"],"quotes":[{"symbol":k,"price":str(v[s["tick"]])} for k,v in self.series.items()],"leverage":2,"real_orders":False,"exchange_execution_verified":False,"funding_model":"hypothetical_every_3_observations","liquidation_model":"simplified_isolated_margin"}
