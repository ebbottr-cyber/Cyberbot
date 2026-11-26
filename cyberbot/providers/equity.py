"""EBBot stock_daily arşivi için bağımsız, salt okunur araştırma adaptörü."""
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
import math
import re
import sqlite3

MARKETS={"BIST":("TRY",r"[A-Z0-9]{1,12}\.IS"),"NASDAQ":("USD",r"[A-Z][A-Z0-9.-]{0,14}"),"XETRA":("EUR",r"[A-Z0-9]{1,12}\.DE")}
class DataError(ValueError):
    pass

def history(path, market, symbol, limit=250):
    if market not in MARKETS or not re.fullmatch(MARKETS[market][1],symbol) or (market=="NASDAQ" and symbol.endswith((".IS",".DE",".HK",".SS",".SZ"))):
        raise DataError("Piyasa veya sembol biçimi geçersiz.")
    if type(limit) is not int or not 1<=limit<=6000:
        raise DataError("Kayıt sınırı 1–6000 olmalı.")
    if not path:
        raise DataError("EBBot veri dosyası henüz yapılandırılmadı.")
    try:
        db=Path(path).expanduser().resolve(strict=True)
        if not db.is_file():
            raise OSError()
        with closing(sqlite3.connect(db.as_uri()+"?mode=ro",uri=True,timeout=2)) as conn:
            conn.execute("PRAGMA query_only=ON")
            rows=conn.execute("SELECT date, open, high, low, close, volume, data_source FROM stock_daily WHERE code=? ORDER BY date DESC LIMIT ?",(symbol,limit)).fetchall()
    except (OSError,sqlite3.Error):
        raise DataError("Arşiv okunamadı veya stock_daily şeması uyumsuz.") from None
    bars=[]
    seen=set()
    today=datetime.now(timezone.utc).date()
    for d,o,h,l,c,v,source in reversed(rows):
        try:
            session=date.fromisoformat(d)
            if session>today or session in seen: raise ValueError()
            if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in (o,h,l,c,v)): raise ValueError()
            if min(o,h,l,c)<=0 or v<0 or h<max(o,l,c) or l>min(o,h,c): raise ValueError()
            if not isinstance(source,str) or not source.strip() or len(source)>120: raise ValueError()
        except (ValueError,TypeError,OverflowError):
            raise DataError("Arşivde geçersiz veya tekrar eden OHLCV satırı.") from None
        seen.add(session)
        bars.append({"session":d,"open":o,"high":h,"low":l,"close":c,"volume":v,"source":source})
    return {"market":market,"symbol":symbol,"currency":MARKETS[market][0],"bars":bars,
            "status":"historical_unverified" if bars else "no_data","age_days":(today-date.fromisoformat(bars[-1]["session"])).days if bars else None,
            "venue_verified":False,"license_verified":False,"paper_fill_enabled":False,"real_orders":False}
