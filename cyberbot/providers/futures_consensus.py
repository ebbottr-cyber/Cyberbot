"""Futures research-only consensus over bounded public observations.

All inputs can share a venue and underlying trades. Agreement is not independent
confirmation or a probability. This module has no paper/live order access.
"""
import argparse,json,os
from decimal import Decimal as D
import httpx
from . import futures_timeframes as tf,futures_momentum as mom,futures_sentiment as sent
from . import binance_observed as binance
from .. import futures_pilot as fut,observed_pilot as stocks
from ..observed_pilot import PilotError

VERSION="futures-consensus-1"
def bounded(value,lo,hi):return fut.number(value,lo,hi)
def recent(value,now,seconds):
    t=stocks.ts(value)
    if not 0<=(now-t).total_seconds()<=seconds:raise PilotError("Sinyal kanıtı eski veya gelecek.")
    return t
def vote(x,threshold):
    return "UP" if x>threshold else "DOWN" if x<-threshold else "NEUTRAL"
def report(raw,sym,status):
    if (not isinstance(raw,dict) or raw.get("symbol")!=sym or raw.get("status")!=status
        or raw.get("real_orders") is not False or raw.get("pilot_applied") is not False
        or raw.get("directional_signal") is not None):
        raise PilotError("Araştırma raporu kimliği veya güvenlik alanı geçersiz.")
    return raw

def evaluate(*,symbol,now,market,book,timeframes,momentum,sentiment,fast=None,liquidations=None):
    if symbol not in ("BTCUSDT","ETHUSDT"):raise PilotError("Sembol geçersiz.")
    market=report(market,symbol,"research_only")
    book=report(book,symbol,"visible_snapshot_only")
    timeframes=report(timeframes,symbol,"research_only")
    momentum=report(momentum,symbol,"research_only")
    sentiment=report(sentiment,symbol,"research_only")
    mt=recent(market["source_at"],now,30);bt=recent(book["source_at"],now,30)
    if abs((mt-bt).total_seconds())>5:raise PilotError("Piyasa ve defter gözlemleri uyumsuz.")
    cutoff=recent(timeframes["cutoff_at"],now,60)
    if momentum.get("mode")!="closed_candles" or sentiment.get("period")!="5m":
        raise PilotError("Gösterge veya duyarlılık periyodu yanlış.")
    recent(sentiment["period_end"],now,900)
    frames=timeframes["timeframes"];metrics=momentum["timeframes"]
    if set(frames)!=set(tf.FRAMES) or set(metrics)!=set(mom.FRAMES):raise PilotError("Zaman dilimi kapsamı eksik.")
    cutoff_ms=int(cutoff.timestamp()*1000)
    for f,step in tf.FRAMES.items():
        end=binance.stamp(cutoff_ms//step*step)
        if stocks.ts(frames[f]["closed_through"])!=end or frames[f].get("closed_bars")!=21:
            raise PilotError("Trend kapanış zamanı veya mum sayısı yanlış.")
        if frames[f].get("trend_label") not in ("UP","DOWN","NEUTRAL"):
            raise PilotError("Trend etiketi geçersiz.")
        if f in metrics and (stocks.ts(metrics[f]["closed_through"])!=end or metrics[f].get("closed_bars")!=60):
            raise PilotError("Momentum kapanış zamanı veya mum sayısı yanlış.")
    labels=[frames[f]["trend_label"] for f in tf.FRAMES]
    trend=labels[0] if len(set(labels))==1 else "NEUTRAL"
    momentum_votes=[]
    for f in mom.FRAMES:
        row=metrics[f]
        rsi=bounded(row["rsi14"],"0","100")
        hist=bounded(row["macd_histogram"],"-1000000000","1000000000")
        change=bounded(row["momentum_5_bars_pct"],"-100","100000000000000000000")
        momentum_votes.append("UP" if rsi>55 and hist>0 and change>D(".1") else
                              "DOWN" if rsi<45 and hist<0 and change<D("-.1") else "NEUTRAL")
    mv=momentum_votes[0] if len(set(momentum_votes))==1 else "NEUTRAL"
    bands=book.get("depth_bands")
    if not isinstance(bands,list):raise PilotError("Emir defteri katmanları eksik.")
    by_n={b["levels_per_side"]:b for b in bands}
    if len(by_n)!=len(bands) or set(by_n)-{5,10,20}:raise PilotError("Emir defteri katmanı geçersiz.")
    bv="NEUTRAL"
    blockers=[]
    if set(by_n)!={5,10,20} or book.get("ticker_top_matches") is not True:
        blockers.append("book_incomplete_or_top_mismatch")
    else:
        book_votes=[vote(bounded(by_n[n]["notional_imbalance"],"-1","1"),D(".1")) for n in (5,10,20)]
        bv=book_votes[0] if len(set(book_votes))==1 else "NEUTRAL"
    tv=vote(bounded(sentiment["taker_volume"]["volume_imbalance"],"-1","1"),D(".1"))
    votes={"trend":trend,"momentum":mv,"visible_book":bv,"taker_volume":tv}
    spread=bounded(book["spread_bps"],"0","20000")
    basis=bounded(market["mark_index_basis_pct"],"-100","100000000000000000000")
    funding=bounded(market["reported_last_funding_rate"],"-.1",".1")
    oi=bounded(market["open_interest_base"],"0","1000000000000")
    crowd=bounded(sentiment["global_accounts"]["long_share"],"0","1")
    atr={f:bounded(metrics[f]["atr_pct"],"0","100000000000000000000") for f in mom.FRAMES}
    semivariance={}
    for f in mom.FRAMES:
        semivariance[f]={k:str(bounded(metrics[f][k],"0","10000000000000000000000000000000000"))
                         for k in ("upside_semivariance_20","downside_semivariance_20")}
    if spread>D(20):blockers.append("wide_spread")
    if abs(basis)>D(1):blockers.append("wide_mark_index_basis")
    if abs(funding)>D(".001"):blockers.append("elevated_reported_funding")
    if atr["1m"]>D(2) or atr["5m"]>D(4):blockers.append("elevated_atr")
    if oi==0:blockers.append("zero_open_interest")
    candidate="UP" if all(x=="UP" for x in votes.values()) else "DOWN" if all(x=="DOWN" for x in votes.values()) else None
    if candidate=="UP" and crowd>D(".75") or candidate=="DOWN" and crowd<D(".25"):
        blockers.append("crowded_accounts")
    optional={"fast_momentum":"not_provided","liquidations":"not_provided"}
    if fast is not None:
        f=report(fast,symbol,"research_only")
        if f.get("mode")!="30s_midpoint":raise PilotError("Hızlı momentum modu geçersiz.")
        fm=f["fast_momentum"]
        recent(fm["end_at"],now,30)
        elapsed=(stocks.ts(fm["end_at"])-stocks.ts(fm["start_at"])).total_seconds()
        if not 29<=elapsed<=31:raise PilotError("Hızlı momentum aralığı geçersiz.")
        fv=vote(bounded(fm["momentum_pct"],"-100","100000000000000000000"),D(".05"))
        optional["fast_momentum"]=fv
        if candidate and fv!=candidate:blockers.append("fast_momentum_not_confirming")
    if liquidations is not None:
        liq=report(liquidations,symbol,"snapshot_window_complete")
        recent(liq["ended_at"],now,60)
        if liq.get("window_complete") is not True:raise PilotError("Likidasyon penceresi eksik.")
        clusters=liq.get("clusters")
        if not isinstance(clusters,list) or len(clusters)>24:raise PilotError("Likidasyon kümesi geçersiz.")
        optional["liquidations"]="clusters_reported" if clusters else "no_cluster_observed"
        if clusters:blockers.append("liquidation_cluster_observed")
    if candidate is None:blockers.append("signals_mixed_or_neutral")
    label="research_"+candidate.lower() if candidate and not blockers else "HOLD"
    return {"version":VERSION,"status":"research_only","symbol":symbol,"evaluated_at":now.isoformat(),
            "votes":votes,"research_label":label,"blockers":blockers,"optional_context":optional,
            "risk_context":{"spread_bps":str(spread),"mark_index_basis_pct":str(basis),
                            "reported_funding_rate":str(funding),"open_interest_base":str(oi),
                            "global_long_account_share":str(crowd),"atr_pct":{f:str(v) for f,v in atr.items()},
                            "directional_semivariance":semivariance},
            "independent_sources_verified":False,"thresholds_validated":False,
            "confidence_probability":None,"directional_signal":None,"actual_action":"HOLD",
            "paper_orders":False,"pilot_applied":False,"real_orders":False,"profitability_verified":False}

def run(*,transport=None,clock=stocks.utc):
    # Keep this separate from automatic observation and the existing paper ledger.
    flags=("CYBERBOT_FUTURES_CONSENSUS_ENABLED","CYBERBOT_FUTURES_TIMEFRAMES_ENABLED","CYBERBOT_FUTURES_MOMENTUM_ENABLED")
    if not binance.configured() or any(os.getenv(f)!="1" for f in flags):
        raise PilotError("Birleşik Futures araştırma izinleri kapalı.")
    symbol=fut.symbol();start=clock();cutoff=int(start.timestamp()*1000)-3000
    def check():
        if not 0<=(clock()-start).total_seconds()<60:raise PilotError("Birleşik gözlem süresi aşıldı.")
    def guarded(endpoint,params):
        check()
        if transport is not None:return transport(endpoint,params)
        if endpoint in (sent.GLOBAL,sent.TAKER):return sent.fetch(client,endpoint,symbol)
        return binance.get(client,endpoint,params)
    frames={};metrics={}
    with httpx.Client(timeout=httpx.Timeout(8,connect=3),follow_redirects=False,trust_env=False) as client:
        for f in tf.FRAMES:
            check();limit=60 if f in mom.FRAMES else 21
            raw=transport(tf.KLINES,tf.params(symbol,f,cutoff,limit=limit)) if transport is not None else tf.fetch(client,symbol,f,cutoff,limit=limit)
            rows=tf.parse(raw,f,cutoff,limit=limit)
            frames[f]=tf.frame_metrics(rows[-21:],f,cutoff)
            if f in mom.FRAMES:metrics[f]={**mom.indicators(rows),"closed_through":frames[f]["closed_through"]}
        raw={e:guarded(e,{"symbol":symbol,"period":"5m","limit":3}) for e in (sent.GLOBAL,sent.TAKER)}
        sentiment=sent.summarize(raw,symbol,clock())
        info=guarded(binance.INFO,{})
        book=guarded(binance.BOOK,{"symbol":symbol});mark=guarded(binance.MARK,{"symbol":symbol})
        binance.parse(book,mark,info,symbol,clock())
        market=binance.market_context(book,mark,guarded(binance.OPEN_INTEREST,{"symbol":symbol}),symbol,clock())
        depth=binance.orderbook_context(guarded(binance.DEPTH,{"symbol":symbol,"limit":20}),book,symbol,clock())
        check()
    common={"symbol":symbol,"status":"research_only","real_orders":False,"pilot_applied":False,"directional_signal":None}
    result=evaluate(symbol=symbol,now=clock(),market=market,book=depth,
                    timeframes={**common,"cutoff_at":binance.stamp(cutoff).isoformat(),"timeframes":frames},
                    momentum={**common,"mode":"closed_candles","timeframes":metrics},sentiment=sentiment)
    return {**result,"transport_mocked":transport is not None,
            "public_request_count":12,"shared_candle_requests":5}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.parse_args()
    try:print(json.dumps(run(),ensure_ascii=True));return 0
    except (ValueError,OSError,ArithmeticError,KeyError,TypeError) as e:
        print(json.dumps({"status":"rejected","type":type(e).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
