"""Separate native-currency paper accounts. No broker or FX execution."""
import os
import json
from decimal import Decimal as D, InvalidOperation
from datetime import datetime, timezone
from pathlib import Path
from .engine import Ledger
from .market import INDEX

CAPITAL={"BIST":("TRY",D("45000")),"NASDAQ":("USD",D("1000")),"XETRA":("USD",D("1000")),"SOLANA":("USD",D("1000"))}
MAX_FX_AGE=300

def account_paths(base=None):
    base=Path(base or os.getenv("CYBERBOT_DB","var/paper.sqlite3")).expanduser().resolve()
    root=base.parent/(base.stem+"-markets")
    return {m:root/(m.lower()+".sqlite3") for m in CAPITAL}

def valid_usdt(value):
    try:
        v=D(str(value))
        return str(v) if v.is_finite() and D(".01")<=v<=D("100") else None
    except (InvalidOperation,ValueError,TypeError):return None

def fx_quote(path=None,now=None):
    path=path or os.getenv("CYBERBOT_FX_FILE") or (str(Path("var/fx-provider.json")) if os.getenv("CYBERBOT_FX_PROVIDER_ENABLED")=="1" and os.getenv("CYBERBOT_FX_RIGHTS_CONFIRMED")=="1" else None)
    missing={"status":"unavailable","usdtry":None,"observed_at":None,"source":None}
    if not path:return missing
    try:
        with Path(path).open("rb") as f:raw=f.read(8193)
        if len(raw)>8192:return missing
        x=json.loads(raw);rate=D(str(x["usdtry"]))
        stamp=datetime.fromisoformat(x.get("usdtry_observed_at",x["observed_at"]).replace("Z","+00:00"))
        source=x["source"]
        if not rate.is_finite() or not D(".01")<=rate<=D("1000000") or stamp.tzinfo is None or not isinstance(source,str) or not 1<=len(source)<=100:return missing
        age=((now or datetime.now(timezone.utc))-stamp).total_seconds()
        if age< -5 or age>MAX_FX_AGE:return {**missing,"status":"stale","observed_at":stamp.isoformat(),"source":source}
        usdt=valid_usdt(x.get("usdtusd"));usdt_stamp=None;usdt_status="unavailable"
        if usdt is not None:
            try:
                other=datetime.fromisoformat(x.get("usdtusd_observed_at",x["observed_at"]).replace("Z","+00:00"))
                if other.tzinfo is None:raise ValueError()
                usdt_stamp=other.isoformat()
                usdt_age=((now or datetime.now(timezone.utc))-other).total_seconds()
                usdt_status="fresh_input" if -5<=usdt_age<=MAX_FX_AGE else "stale"
            except (ValueError,TypeError,AttributeError,OverflowError):usdt_status="unavailable"
        return {"status":"fresh_input","usdtry":str(rate),"observed_at":stamp.isoformat(),"source":source,"age_seconds":max(0,int(age)),"provider_verified":False,
                "usdtusd":usdt if usdt_status=="fresh_input" else None,"usdtusd_status":usdt_status,"usdtusd_observed_at":usdt_stamp}
    except (OSError,ValueError,TypeError,KeyError,InvalidOperation,AttributeError,OverflowError):return missing

def usd_total(accounts,quote,field="equity"):
    if quote.get("status") not in ("fresh_input","synthetic_reference"):return None
    rate=D(quote["usdtry"])
    if not rate.is_finite() or rate<=0:return None
    if any(a["currency"]=="USDT" for a in accounts) and valid_usdt(quote.get("usdtusd")) is None:return None
    return str(sum((D(a[field])/rate if a["currency"]=="TRY" else D(a[field])*D(quote["usdtusd"]) if a["currency"]=="USDT" else D(a[field]) for a in accounts),D(0)).quantize(D(".01")))

class Portfolio:
    def __init__(self,base=None):
        paths=account_paths(base)
        archive=os.getenv("CYBERBOT_EBBOT_DB")
        if archive and Path(archive).expanduser().resolve() in paths.values():raise ValueError("Archive path collision.")
        from .futures import Futures,path_for
        self.futures=Futures(path_for(base))
        self.ledgers={m:Ledger(paths[m],instruments={k:v for k,v in INDEX.items() if v.market==m},start=amount,currency=cur) for m,(cur,amount) in CAPITAL.items()}
    def snapshot(self):
        accounts=[]
        for m,ledger in self.ledgers.items():
            s=ledger.snapshot()
            accounts.append({"market":m,"initial_equity":str(CAPITAL[m][1]),**s})
        fx=fx_quote()
        futures=self.futures.snapshot()
        combined=accounts+[futures]
        total=usd_total(combined,fx)
        return {"accounts":accounts,"futures":futures,"four_market_equity_usd":usd_total(accounts,fx),"fx":fx,"currency":"USD","equity":total,"cash":usd_total(combined,fx,"cash"),
                "daily_pnl":usd_total(combined,fx,"daily_pnl"),"pnl":usd_total(combined,fx,"pnl"),
                "initial_equity_at_current_fx":usd_total(combined,fx,"initial_equity"),
                "pnl_basis":"native_trading_pnl_converted_at_current_rate_excludes_fx_gain",
                "open_count":sum(a["open_count"] for a in combined),"open_markets":sum(a["open_count"]>0 for a in combined),
                "real_orders":False,"mode":"synthetic_paper","fx_gain_measured":False}
