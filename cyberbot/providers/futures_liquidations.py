"""Bounded Binance USD-M forceOrder snapshot research; no order or storage API."""
import argparse,json,time,os
from decimal import Decimal as D
from datetime import timedelta
from .binance_observed import configured,stamp
from .. import futures_pilot as fut,observed_pilot as stocks
from ..observed_pilot import PilotError

HOST="wss://fstream.binance.com/market/ws/"
MAX_MESSAGES=240
MAX_BYTES=16384

def parse_event(raw,sym,now):
    if not isinstance(raw,dict) or raw.get("e")!="forceOrder":
        raise PilotError("Likidasyon olay biçimi geçersiz.")
    o=raw.get("o")
    if not isinstance(o,dict) or o.get("s")!=sym or raw.get("st",1)!=1:
        raise PilotError("Likidasyon sözleşmesi uyuşmuyor.")
    if o.get("S") not in ("BUY","SELL"):raise PilotError("Likidasyon yönü geçersiz.")
    event,trade=stamp(raw.get("E")),stamp(o.get("T"))
    if not timedelta(0)<=now-event<=timedelta(seconds=30) or not timedelta(0)<=event-trade<=timedelta(seconds=30):
        raise PilotError("Likidasyon zaman damgası geçersiz.")
    qty=fut.number(o.get("q"),"0.000000000001","1000000000")
    last=fut.number(o.get("l"),"0","1000000000")
    filled=fut.number(o.get("z"),"0","1000000000")
    avg=fut.number(o.get("ap"),"0","1000000000000")
    if not last<=filled<=qty or (filled>0 and avg==0):
        raise PilotError("Likidasyon dolum miktarı tutarsız.")
    if o.get("X") not in ("NEW","PARTIALLY_FILLED","FILLED","CANCELED","EXPIRED","EXPIRED_IN_MATCH"):
        raise PilotError("Likidasyon emir durumu geçersiz.")
    if o["X"]=="FILLED" and filled!=qty:raise PilotError("Tam dolum miktarı tutarsız.")
    return {"event_at":event.isoformat(),"trade_at":trade.isoformat(),
            "liquidated_side":"LONG" if o["S"]=="SELL" else "SHORT",
            "original_qty":str(qty),"cumulative_filled_qty":str(filled),
            "average_fill_price":str(avg),"last_filled_qty":str(last),
            "order_status":o["X"],"reported_cumulative_notional_usdt":str(filled*avg)}

def summarize(events,start,end,sym,seconds,*,complete,received,duplicates,reason):
    totals={"LONG":D(0),"SHORT":D(0)}
    counts={"LONG":0,"SHORT":0}
    buckets={}
    for row in events:
        side=row["liquidated_side"]
        value=D(row["reported_cumulative_notional_usdt"])
        if value==0:continue
        counts[side]+=1;totals[side]+=value
        # Absolute UTC buckets, not overlapping rolling windows.
        bucket=int(stocks.ts(row["trade_at"]).timestamp())//10*10
        b=buckets.setdefault(bucket,{"LONG":0,"SHORT":0})
        b[side]+=1
    duration=max(0,(end-start).total_seconds())
    return {"status":"snapshot_window_complete" if complete else "snapshot_window_incomplete",
            "symbol":sym,"started_at":start.isoformat(),"ended_at":end.isoformat(),
            "requested_seconds":seconds,"elapsed_seconds":duration,"stop_reason":reason,
            "received_messages":received,"deduplicated_messages":duplicates,
            "filled_snapshot_counts":counts,
            "reported_cumulative_snapshot_notional_usdt":{k:str(v) for k,v in totals.items()},
            "clusters":[{"utc_bucket_epoch":k,"side":side,"filled_snapshots":n}
                        for k,b in sorted(buckets.items()) for side,n in b.items() if n>=3],
            "cluster_rule":"at_least_3_filled_snapshots_same_side_in_10s_utc_bucket",
            "events":events,"window_complete":complete,"market_coverage_complete":False,
            "unique_order_ids_available":False,"totals_are_unique_trade_volume":False,
            "cascade_prediction_verified":False,"directional_signal":None,
            "pilot_applied":False,"real_orders":False}

def live_connector(url):
    try:from websockets.sync.client import connect
    except ImportError:raise PilotError("İsteğe bağlı requirements-futures-stream.txt kurulmalı.") from None
    return connect(url,open_timeout=5,close_timeout=1,max_size=MAX_BYTES,
                   max_queue=16,proxy=None,compression=None)

def run(*,seconds=30,connector=None,clock=stocks.utc,monotonic=time.monotonic):
    if type(seconds) is not int or seconds not in (30,60):raise PilotError("Gözlem süresi 30 veya 60 saniye olmalı.")
    if not configured() or os.getenv("CYBERBOT_FUTURES_LIQUIDATION_ENABLED")!="1":
        raise PilotError("Likidasyon gözlem izni kapalı.")
    sym=fut.symbol()
    events=[];seen=set();received=duplicates=0;complete=False;reason="connection_failed"
    start=clock();end=start
    try:
        with (connector or live_connector)(HOST+sym.lower()+"@forceOrder") as ws:
            start=clock();deadline=monotonic()+seconds
            reason="message_cap"
            while received<MAX_MESSAGES:
                remaining=deadline-monotonic()
                if remaining<=0:complete=True;reason="window_elapsed";break
                try:message=ws.recv(timeout=remaining)
                except TimeoutError:
                    complete=monotonic()>=deadline
                    reason="window_elapsed" if complete else "early_timeout"
                    break
                received+=1
                if not isinstance(message,(str,bytes)) or len(message)>MAX_BYTES:
                    raise PilotError("Likidasyon mesaj boyutu geçersiz.")
                row=parse_event(json.loads(message),sym,clock())
                if stocks.ts(row["trade_at"])<start:continue
                # No stable order id: suppress only identical normalized snapshots.
                signature=tuple(row.values())
                if signature in seen:duplicates+=1;continue
                seen.add(signature);events.append(row)
            end=clock()
    except Exception as exc:
        end=clock();complete=False;reason=type(exc).__name__
    if end<start:complete=False;reason="clock_regressed";end=start
    return {**summarize(events,start,end,sym,seconds,complete=complete,received=received,
                        duplicates=duplicates,reason=reason),"transport_mocked":connector is not None}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seconds",type=int,choices=(30,60),default=30)
    a=p.parse_args()
    try:
        d=run(seconds=a.seconds);print(json.dumps(d,ensure_ascii=True))
        return 0 if d["window_complete"] else 1
    except (ValueError,OSError,ArithmeticError,KeyError,TypeError) as e:
        print(json.dumps({"status":"rejected","type":type(e).__name__}));return 1

if __name__=="__main__":raise SystemExit(main())
