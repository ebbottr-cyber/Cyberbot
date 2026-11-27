"""Bounded five-minute USD-M sentiment research; never an order or pilot input."""
import json,os,re
from datetime import timedelta
from decimal import Decimal as D
import httpx
from .binance_observed import HOST,MAX_BYTES,configured,stamp
from .. import futures_pilot as fut,observed_pilot as stocks
from ..observed_pilot import PilotError

GLOBAL="/futures/data/globalLongShortAccountRatio"
TOP_ACCOUNT="/futures/data/topLongShortAccountRatio"
TOP_POSITION="/futures/data/topLongShortPositionRatio"
TAKER="/futures/data/takerlongshortRatio"
TOP=(TOP_ACCOUNT,TOP_POSITION)
PERIOD=timedelta(minutes=5)
MAX_AGE=timedelta(minutes=15)

def fetch(client,endpoint,sym,key=""):
    if endpoint not in (GLOBAL,TAKER,*TOP) or sym not in ("BTCUSDT","ETHUSDT"):
        raise PilotError("Duyarlılık veri yolu geçersiz.")
    if endpoint in TOP and not key:raise PilotError("Top Trader veri anahtarı gerekli.")
    headers={"X-MBX-APIKEY":key} if endpoint in TOP else {}
    try:
        with client.stream("GET",HOST+endpoint,params={"symbol":sym,"period":"5m","limit":3},headers=headers) as response:
            response.raise_for_status();raw=bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw)>MAX_BYTES:raise PilotError("Duyarlılık yanıtı çok büyük.")
        return json.loads(raw)
    except (httpx.HTTPError,ValueError,OSError):
        raise PilotError("Duyarlılık veri sorgusu başarısız; otomatik tekrar yok.") from None

def observations(raw,endpoint,sym,now):
    if not isinstance(raw,list) or not 1<=len(raw)<=3:raise PilotError("Duyarlılık kayıt sınırı.")
    out={};seen=set()
    for row in raw:
        if not isinstance(row,dict) or (endpoint!=TAKER and row.get("symbol")!=sym) or row.get("symbol",sym)!=sym:
            raise PilotError("Duyarlılık sembolü uyuşmuyor.")
        source=stamp(row.get("timestamp"))
        # API docs label taker timestamp as period start and ratios as period end.
        end=source+PERIOD if endpoint==TAKER else source
        if source>now or end in seen:raise PilotError("Gelecek veya tekrarlı duyarlılık kaydı.")
        seen.add(end)
        if not timedelta(0)<=now-end<=MAX_AGE:continue
        if endpoint==TAKER:
            a,b=(fut.number(row.get(k),"0","1000000000000") for k in ("buyVol","sellVol"))
            ratio=fut.number(row.get("buySellRatio"),"0","100000000")
            if a+b==0 or b==0:raise PilotError("Taker hacmi oranı tanımsız.")
            calc=a/b
            if abs(ratio-calc)>max(D(".001"),calc*D(".005")):
                raise PilotError("Taker hacmi oranı tutarsız.")
            value={"buy_volume_reported":str(a),"sell_volume_reported":str(b),
                   "buy_sell_ratio_reported":str(ratio),"volume_imbalance":str((a-b)/(a+b))}
        else:
            a,b=(fut.number(row.get(k),"0","1") for k in ("longAccount","shortAccount"))
            ratio=fut.number(row.get("longShortRatio"),"0","100000000")
            if abs(a+b-1)>D(".002") or b==0:raise PilotError("Long/Short payları tutarsız.")
            calc=a/b
            if abs(ratio-calc)>max(D(".002"),calc*D(".005")):
                raise PilotError("Long/Short oranı tutarsız.")
            value={"long_share":str(a),"short_share":str(b),"long_short_ratio_reported":str(ratio)}
        out[end]={"source_timestamp":source.isoformat(),**value}
    return out

def summarize(raw,sym,now,*,include_top=False):
    endpoints=(GLOBAL,TAKER,*TOP) if include_top else (GLOBAL,TAKER)
    parsed={e:observations(raw[e],e,sym,now) for e in endpoints}
    common=set.intersection(*(set(v) for v in parsed.values()))
    if not common:raise PilotError("Ortak tamamlanmış duyarlılık dönemi yok.")
    end=max(common)
    return {"status":"research_only","symbol":sym,"period":"5m","period_end":end.isoformat(),
            "global_accounts":parsed[GLOBAL][end],"taker_volume":parsed[TAKER][end],
            "top_trader_accounts":parsed[TOP_ACCOUNT][end] if include_top else None,
            "top_trader_positions":parsed[TOP_POSITION][end] if include_top else None,
            "top_trader_status":"reported" if include_top else "not_requested",
            "timestamp_semantics":"provider_documented_not_independently_verified",
            "directional_signal":None,"pilot_applied":False,"real_orders":False}

def run(*,include_top=False,transport=None,clock=stocks.utc):
    if not configured():raise PilotError("Binance adaptörü veya veri kullanım izni kapalı.")
    key=os.getenv("CYBERBOT_BINANCE_SENTIMENT_DATA_KEY","").strip() if include_top else ""
    if include_top and not re.fullmatch(r"[A-Za-z0-9_-]{1,256}",key):
        raise PilotError("Top Trader için geçerli salt veri API anahtarı gerekli.")
    sym=fut.symbol()
    endpoints=(GLOBAL,TAKER,*TOP) if include_top else (GLOBAL,TAKER)
    with httpx.Client(timeout=httpx.Timeout(8,connect=3),follow_redirects=False,trust_env=False) as client:
        raw={e:transport(e,{"symbol":sym,"period":"5m","limit":3}) if transport is not None
             else fetch(client,e,sym,key) for e in endpoints}
    return {**summarize(raw,sym,clock(),include_top=include_top),"transport_mocked":transport is not None}
