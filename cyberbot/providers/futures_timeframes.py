"""Bounded closed-candle USD-M timeframe research; no orders or archive writes."""
import argparse,json,os
from decimal import Decimal as D
import httpx
from .binance_observed import HOST,MAX_BYTES,configured,stamp
from .. import futures_pilot as fut,observed_pilot as stocks
from ..observed_pilot import PilotError

KLINES="/fapi/v1/klines"
FRAMES={"1m":60000,"5m":300000,"15m":900000,"1h":3600000,"4h":14400000}
LIMIT=21
DEADBAND=D(".001")

def params(sym,frame,cutoff_ms,*,limit=LIMIT):
    if type(limit) is not int or limit not in (LIMIT,60):raise PilotError("Mum sayısı sınırı.")
    if sym not in ("BTCUSDT","ETHUSDT") or frame not in FRAMES:
        raise PilotError("Futures zaman dilimi veya sembol geçersiz.")
    step=FRAMES[frame];end=cutoff_ms//step*step-1
    return {"symbol":sym,"interval":frame,"limit":limit,"endTime":end}

def fetch(client,sym,frame,cutoff_ms,*,limit=LIMIT):
    query=params(sym,frame,cutoff_ms,limit=limit)
    try:
        with client.stream("GET",HOST+KLINES,params=query) as response:
            response.raise_for_status();raw=bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw)>MAX_BYTES:raise PilotError("Mum yanıtı çok büyük.")
        return json.loads(raw)
    except (httpx.HTTPError,ValueError,OSError):
        raise PilotError("Mum sorgusu başarısız; otomatik tekrar yok.") from None

def parse(raw,frame,cutoff_ms,*,limit=LIMIT):
    if type(limit) is not int or limit not in (LIMIT,60):raise PilotError("Mum sayısı sınırı.")
    step=FRAMES[frame];end=cutoff_ms//step*step
    if not isinstance(raw,list) or len(raw)!=limit:
        raise PilotError("Beklenen kapanmış mum sayısı eksik.")
    rows=[]
    for i,row in enumerate(raw):
        expected=end-(limit-i)*step
        if (not isinstance(row,list) or len(row)!=12 or type(row[0]) is not int
            or type(row[6]) is not int or row[0]!=expected or row[6]!=expected+step-1
            or row[6]>=cutoff_ms):
            raise PilotError("Eksik, açık veya sırasız mum.")
        if not all(isinstance(row[j],str) for j in (1,2,3,4,5,7,9,10)):
            raise PilotError("Mum sayısal biçimi geçersiz.")
        o,h,l,c=(stocks.dec(row[j]) for j in (1,2,3,4))
        if not l<=min(o,c)<=max(o,c)<=h:raise PilotError("Mum fiyat aralığı tutarsız.")
        v,q,tb,tq=(fut.number(row[j],"0","1000000000000000000") for j in (5,7,9,10))
        if tb>v or tq>q or type(row[8]) is not int or row[8]<0:
            raise PilotError("Mum hacim bilgisi tutarsız.")
        rows.append((o,h,l,c,v))
    return rows

def frame_metrics(rows,frame,cutoff_ms):
    closes=[x[3] for x in rows];sma5=sum(closes[-5:])/5;sma20=sum(closes[-20:])/20
    delta=sma5/sma20-1;ret=closes[-1]/closes[0]-1
    direction="UP" if delta>DEADBAND and ret>DEADBAND else "DOWN" if delta<-DEADBAND and ret<-DEADBAND else "NEUTRAL"
    step=FRAMES[frame];end=cutoff_ms//step*step
    return {"interval":frame,"closed_through":stamp(end).isoformat(),"closed_bars":len(rows),
            "last_close":str(closes[-1]),"sma5":str(sma5),"sma20":str(sma20),
            "sma_gap_pct":str(delta*100),"return_20_bars_pct":str(ret*100),
            "trend_label":direction}

def summarize(raw,sym,cutoff_ms):
    if sym not in ("BTCUSDT","ETHUSDT") or set(raw)!=set(FRAMES):raise PilotError("Zaman dilimi kapsamı eksik.")
    frames={f:frame_metrics(parse(raw[f],f,cutoff_ms),f,cutoff_ms) for f in FRAMES}
    labels=[v["trend_label"] for v in frames.values()]
    counts={k:labels.count(k) for k in ("UP","DOWN","NEUTRAL")}
    higher=labels[-2:]
    alignment="aligned_up" if all(x=="UP" for x in labels) else "aligned_down" if all(x=="DOWN" for x in labels) else "mixed_or_neutral"
    return {"status":"research_only","symbol":sym,"cutoff_at":stamp(cutoff_ms).isoformat(),
            "timeframes":frames,"trend_counts":counts,"alignment":alignment,
            "higher_timeframes_agree":higher[0]==higher[1] and higher[0]!="NEUTRAL",
            "deadband_pct":str(DEADBAND*100),"thresholds_validated":False,
            "directional_signal":None,"pilot_applied":False,"real_orders":False,
            "profitability_verified":False,"bulk_price_download_enabled":False}

def run(*,transport=None,clock=stocks.utc):
    if not configured() or os.getenv("CYBERBOT_FUTURES_TIMEFRAMES_ENABLED")!="1":
        raise PilotError("Zaman dilimi gözlem izni kapalı.")
    sym=fut.symbol();start=clock()
    # Fixed as-of cutoff across all five requests, allow three seconds for publication.
    cutoff_ms=int(start.timestamp()*1000)-3000
    raw={}
    with httpx.Client(timeout=httpx.Timeout(8,connect=3),follow_redirects=False,trust_env=False) as client:
        for frame in FRAMES:
            if not 0<=(clock()-start).total_seconds()<30:raise PilotError("Mum gözlem süresi aşıldı.")
            raw[frame]=transport(KLINES,params(sym,frame,cutoff_ms)) if transport is not None else fetch(client,sym,frame,cutoff_ms)
    if not 0<=(clock()-start).total_seconds()<=30:raise PilotError("Mum gözlem süresi aşıldı.")
    return {**summarize(raw,sym,cutoff_ms),"transport_mocked":transport is not None}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.parse_args()
    try:print(json.dumps(run(),ensure_ascii=True));return 0
    except (ValueError,OSError,ArithmeticError,KeyError,TypeError) as e:
        print(json.dumps({"status":"rejected","type":type(e).__name__}));return 1

if __name__=="__main__":raise SystemExit(main())
