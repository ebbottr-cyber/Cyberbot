"""Bounded daily equity strategy parameter research, never an order signal."""
import argparse
from datetime import date, datetime, timezone
from decimal import Decimal as D
import hashlib
import json
import os
from pathlib import Path
from contextlib import closing

from cyberbot.engine import FEE, SLIP
from cyberbot.strategy_lab import simulate
from cyberbot.providers.equity import history
from .adaptive_review import readonly

VERSION="equity-parameter-review-1"
MARKETS=("BIST","NASDAQ","XETRA")
STRATEGIES=("trend","momentum","reversion")
WINDOWS=(3,5,10,15,20)
MAX_BARS=1000
MIN_BARS=240
MAX_DD=D(".10")
MIN_TRADES=5
SHORTLIST=3


def checked_bars(raw):
    if not MIN_BARS<=len(raw)<=MAX_BARS:
        raise ValueError("240–1000 daily bars required")
    bars=[]
    prior=None
    for row in raw:
        t=date.fromisoformat(row["session"])
        if t>=datetime.now(timezone.utc).date() or (prior and not 1<=(t-prior).days<=7):
            raise ValueError("invalid or discontinuous observed dates")
        o,h,l,c,v=(D(str(row[k])) for k in ("open","high","low","close","volume"))
        if any(not x.is_finite() for x in (o,h,l,c,v)) or not 0<l<=min(o,c)<=max(o,c)<=h or v<=0:
            raise ValueError("invalid OHLCV")
        if prior and not D(".5")<=o/bars[-1][1]<=2:
            raise ValueError("large price discontinuity; corporate-action review required")
        if not D(".5")<=c/o<=2:
            raise ValueError("large intraday discontinuity")
        bars.append((o,c))
        prior=t
    return bars


def evaluate(raw, *, market, symbol, simulator=simulate):
    if market not in MARKETS:
        raise ValueError("daily equity research only")
    bars=checked_bars(raw)
    n=len(bars)
    a=n//2
    b=n*3//4
    def score(name,window,start,end):
        normal=simulator(bars[:end],name,window,start,end,fee=FEE,slip=SLIP)
        stress=simulator(bars[:end],name,window,start,end,fee=FEE*2,slip=SLIP*2)
        checks=(normal["return"]>0,stress["return"]>0,
                normal["drawdown"]<=MAX_DD,stress["drawdown"]<=MAX_DD,
                min(normal["closed"],stress["closed"])>=MIN_TRADES)
        return {"normal_pct":str(normal["return"]*100),
                "stress_pct":str(stress["return"]*100),
                "drawdown_pct":str(normal["drawdown"]*100),
                "stress_drawdown_pct":str(stress["drawdown"]*100),
                "closed":normal["closed"],"eligible":all(checks)}

    # Only discovery results decide the shortlist. Subsequent stages never
    # see the final period until a single candidate has been frozen.
    candidates=[]
    for strategy in STRATEGIES:
        for window in WINDOWS:
            candidates.append({"strategy":strategy,"window":window,
                               "discovery":score(strategy,window,20,a)})
    def rank(rows,stage):
        return sorted(rows,key=lambda r:(-D(r[stage]["stress_pct"]),r["strategy"],r["window"]))
    shortlist=rank([r for r in candidates if r["discovery"]["eligible"]],"discovery")[:SHORTLIST]
    for r in shortlist:
        r["validation"]=score(r["strategy"],r["window"],a,b)
    eligible=rank([r for r in shortlist if r["validation"]["eligible"]],"validation")
    result={"version":VERSION,"market":market,"symbol":symbol,"interval":"1d",
            "status":"NO_CANDIDATE","observations":n,"configurations":len(candidates),
            "discovery_end_exclusive":a,"validation_end_exclusive":b,
            "final_start_session":raw[b]["session"],"candidates":candidates,
            "selected":None,"final":None,"evidence_status":"EXPLORATORY_UNVERIFIED",
            "session_calendar_verified":False,"corporate_actions_verified":False,
            "liquidity_verified":False,"independent_validation":False,
            "automatic_promotion":False,"profitability_verified":False,"real_orders":False}
    if not eligible:
        return result
    selected=eligible[0]
    result["selected"]={k:selected[k] for k in ("strategy","window")}
    final=score(selected["strategy"],selected["window"],b,n)
    result["final"]=final
    result["status"]="REVIEW_ONLY" if final["eligible"] else "FINAL_FAILED"
    return result


def run(root,market,symbol):
    if os.environ.get("CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED")!="1":
        raise RuntimeError("local research rights confirmation required")
    providers=root/"var/providers"
    # Require an exact unique archive mapping instead of guessing venue by ticker.
    with closing(readonly(providers/"equity-full-local-5m.sqlite3")) as db:
        markets={r[0] for r in db.execute("SELECT DISTINCT market FROM candles_5m WHERE ticker=?",(symbol,))}
    if markets!={market}:
        raise ValueError("ambiguous or missing local market mapping")
    rows=history(providers/"equity-full-local-1d.sqlite3",market,symbol,limit=MAX_BARS)["bars"]
    if len({r["source"] for r in rows})!=1:
        raise ValueError("mixed source history")
    report=evaluate(rows,market=market,symbol=symbol)
    report["source_fingerprint"]=hashlib.sha256(json.dumps([VERSION,market,symbol,rows],
        sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path.cwd())
    p.add_argument("--market",required=True,choices=MARKETS)
    p.add_argument("--symbol",required=True)
    args=p.parse_args()
    print(json.dumps(run(args.root.resolve(),args.market,args.symbol),indent=2,allow_nan=False))
