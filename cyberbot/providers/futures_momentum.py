"""Bounded Futures indicator research, with an independent 30-second midpoint probe."""
import argparse,json,os,time
from decimal import Decimal as D
import httpx
from . import futures_timeframes as tf
from .binance_observed import BOOK,configured,get,stamp
from .. import futures_pilot as fut,observed_pilot as stocks
from ..observed_pilot import PilotError

LIMIT=60
FRAMES=("1m","5m")

def wilder(values,n=14):
    if len(values)<n:raise PilotError("Gösterge örneklemi eksik.")
    value=sum(values[:n],D(0))/n
    for x in values[n:]:value=(value*(n-1)+x)/n
    return value

def ema(values,n):
    if len(values)<n:raise PilotError("EMA örneklemi eksik.")
    out=[sum(values[:n],D(0))/n];alpha=D(2)/(n+1)
    for x in values[n:]:out.append(out[-1]+alpha*(x-out[-1]))
    return out

def indicators(rows):
    if len(rows)!=LIMIT:raise PilotError("60 kapanmış mum gerekli.")
    c=[r[3] for r in rows]
    changes=[b-a for a,b in zip(c,c[1:])]
    gains=wilder([max(D(0),x) for x in changes])
    losses=wilder([max(D(0),-x) for x in changes])
    rsi=D(50) if gains==losses==0 else D(100) if losses==0 else D(100)*gains/(gains+losses)
    fast,slow=ema(c,12),ema(c,26)
    macd=[a-b for a,b in zip(fast[-len(slow):],slow)]
    signal=ema(macd,9)[-1]
    tr=[max(h-l,abs(h-prev),abs(l-prev)) for prev,(_,h,l,_,_) in zip(c,rows[1:])]
    atr=wilder(tr)
    returns=[b/a-1 for a,b in zip(c,c[1:])][-20:]
    up=sum((max(D(0),x)**2 for x in returns),D(0))/len(returns)
    down=sum((min(D(0),x)**2 for x in returns),D(0))/len(returns)
    return {"rsi14":str(rsi),"macd_12_26":str(macd[-1]),"macd_signal9":str(signal),
            "macd_histogram":str(macd[-1]-signal),"atr14":str(atr),
            "atr_pct":str(atr/c[-1]*100),"momentum_5_bars_pct":str((c[-1]/c[-6]-1)*100),
            "upside_semivariance_20":str(up),"downside_semivariance_20":str(down),
            "upside_semideviation_pct":str(up.sqrt()*100),"downside_semideviation_pct":str(down.sqrt()*100),
            "semivariance_target_return":"0","semivariance_divisor":len(returns),
            "annualized":False,"ema_seed":"initial_sma","closed_bars":len(rows)}

def midpoint(raw,sym,now):
    if not isinstance(raw,dict) or raw.get("symbol")!=sym:raise PilotError("Momentum sembolü uyuşmuyor.")
    t=stamp(raw.get("time"))
    if not 0<=(now-t).total_seconds()<=3:raise PilotError("Momentum fiyatı eski veya gelecek.")
    bid,ask=(stocks.dec(raw.get(k)) for k in ("bidPrice","askPrice"))
    if bid>=ask:raise PilotError("Momentum fiyatı çapraz veya kilitli.")
    return t,(bid+ask)/2

def fast_momentum(first,second):
    a,p=first;b,q=second;elapsed=(b-a).total_seconds()
    if not 29<=elapsed<=31:raise PilotError("30 saniyelik kaynak zaman aralığı uyuşmuyor.")
    return {"status":"two_midpoint_samples","start_at":a.isoformat(),"end_at":b.isoformat(),
            "elapsed_seconds":elapsed,"start_mid":str(p),"end_mid":str(q),
            "momentum_pct":str((q/p-1)*100),"continuous_path_verified":False,
            "execution_verified":False}

def run(*,transport=None,clock=stocks.utc,fast_probe=False,sleep=time.sleep,monotonic=time.monotonic):
    if not configured() or os.getenv("CYBERBOT_FUTURES_MOMENTUM_ENABLED")!="1":
        raise PilotError("Momentum gözlem izni kapalı.")
    sym=fut.symbol();started=clock();cutoff=int(started.timestamp()*1000)-3000
    reports={};fast=None
    with httpx.Client(timeout=httpx.Timeout(8,connect=3),follow_redirects=False,trust_env=False) as client:
        if fast_probe:
            # Separate opt-in operation; do not download candles or write a paper ledger.
            def sample():
                raw=transport(BOOK,{"symbol":sym}) if transport is not None else get(client,BOOK,{"symbol":sym})
                return midpoint(raw,sym,clock())
            first=sample();deadline=monotonic()+30
            sleep(max(0,deadline-monotonic()))
            fast=fast_momentum(first,sample())
        else:
            for frame in FRAMES:
                if not 0<=(clock()-started).total_seconds()<30:raise PilotError("Gösterge gözlem süresi aşıldı.")
                raw=transport(tf.KLINES,tf.params(sym,frame,cutoff,limit=LIMIT)) if transport is not None else tf.fetch(client,sym,frame,cutoff,limit=LIMIT)
                rows=tf.parse(raw,frame,cutoff,limit=LIMIT)
                reports[frame]={**indicators(rows),"closed_through":stamp(cutoff//tf.FRAMES[frame]*tf.FRAMES[frame]).isoformat()}
            if not 0<=(clock()-started).total_seconds()<=30:raise PilotError("Gösterge gözlem süresi aşıldı.")
    return {"status":"research_only","symbol":sym,"mode":"30s_midpoint" if fast_probe else "closed_candles",
            "timeframes":reports,"fast_momentum":fast,"transport_mocked":transport is not None,
            "thresholds_validated":False,"directional_signal":None,"pilot_applied":False,
            "real_orders":False,"profitability_verified":False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fast-probe",action="store_true",help="Two public midpoint samples about 30 seconds apart")
    a=p.parse_args()
    try:print(json.dumps(run(fast_probe=a.fast_probe),ensure_ascii=True));return 0
    except (ValueError,OSError,ArithmeticError,KeyError,TypeError) as e:
        print(json.dumps({"status":"rejected","type":type(e).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
