"""Causal diagnostics for observed-minute shadow research, not entry gates."""
from decimal import Decimal, InvalidOperation
from math import isfinite, log
from statistics import pstdev
from .observed_pilot import ts

VERSION = "observed-regime-diagnostic-1"
# Experimental thresholds, in percentage points, not annualized.
# Same provisional price thresholds across markets; not calibrated.
TREND_PCT = 0.5
VOL_PCT = 0.2
LOOKBACK = 21
VENUES = {"BIST":"XIST", "NASDAQ":"XNAS", "XETRA":"XETR"}
MARKETS = (*VENUES, "FUTURES", "SOLANA")


def number(value):
    n = Decimal(str(value))
    if not n.is_finite() or n < 0:
        raise ValueError("invalid observation")
    return n


def liquidity(market, quote, now):
    """Assess asserted top-of-book only; no execution or market-wide claim."""
    out = {"status":"unknown", "spread_bps":None, "depth_unit":None,
           "minimum_side_depth":None, "reasons":[]}
    try:
        age = (now-ts(quote["source_at"])).total_seconds()
        if not 0 <= age <= 30:
            return {**out,"reasons":["stale_or_future_quote"]}
        bid,ask = number(quote["bid"]),number(quote["ask"])
        if not 0 < bid <= ask:
            raise ValueError("invalid book")
        spread = (ask/bid-1)*10000
        if spread > 1000000:
            raise ValueError("extreme spread")
        out["spread_bps"] = float(spread)
        if market in VENUES:
            if quote.get("venue") != VENUES[market]:
                return {**out,"reasons":["venue_unverified"]}
            keys,unit,minimum,limit=("bid_size","ask_size"),"shares",1,200
        elif market == "FUTURES":
            keys,unit,minimum,limit=("bid_depth_usdt","ask_depth_usdt"),"USDT",100,50
        elif market == "SOLANA":
            keys,unit,minimum,limit=("bid_depth_usd","ask_depth_usd"),"USD",100,200
        else:
            raise ValueError("unknown market")
        depth = min(number(quote[k]) for k in keys)
        if depth > Decimal("1e12"):
            raise ValueError("extreme depth")
        if market == "SOLANA":
            pool=number(quote["liquidity_usd"])
            if any(number(quote[k])>pool for k in keys):
                raise ValueError("inconsistent pool depth")
            if pool < 100000:
                out["reasons"].append("low_pool_liquidity")
        out.update(depth_unit=unit,minimum_side_depth=float(depth))
        if depth < minimum:
            out["reasons"].append("low_asserted_depth")
        if spread > limit:
            out["reasons"].append("wide_spread")
        out["status"]="constrained" if out["reasons"] else "asserted_threshold_met"
        return out
    except (KeyError,TypeError,ValueError,ArithmeticError,InvalidOperation):
        return {**out,"status":"unknown","reasons":["missing_or_invalid_book"]}


def diagnose(market, prices, quote, now):
    """Input: caller-validated contiguous completed-minute native midpoints."""
    if market not in MARKETS or len(prices)!=LOOKBACK:
        raise ValueError("market or context mismatch")
    p=[float(x) for x in prices]
    if any(not isfinite(x) or x<=0 for x in p):
        raise ValueError("invalid midpoint")
    returns=[100*(log(b)-log(a)) for a,b in zip(p,p[1:])]
    trend=sum(returns)
    vol=pstdev(returns)
    direction="bull" if trend>=TREND_PCT else "bear" if trend<=-TREND_PCT else "sideways"
    book=liquidity(market,quote,now)
    return {"version":VERSION,"market":market,"interval":"1m",
            "observations":LOOKBACK,"direction":direction,
            "volatility":"high" if vol>=VOL_PCT else "normal",
            "trend_log_pct":round(trend,6),"volatility_log_pct":round(vol,6),
            "liquidity":book,"thresholds":{"trend_log_pct":TREND_PCT,
                 "volatility_per_minute_log_pct":VOL_PCT},
            "calibrated":False,"instrument_only":True,
            "execution_verified":False,"automatic_strategy_switching":False,
            "real_orders":False}
