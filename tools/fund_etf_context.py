"""Point-in-time macro and disclosure context for fund/ETF research.

Date-only macro releases become eligible the following UTC day by default.
Archive publication dates are supplied by sources, not independently verified.
No network access, sentiment guessing, or real orders.
"""
import math
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from tools.fund_etf_decision import decide


def utc_stamp(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("timezone_required")
    return stamp.astimezone(timezone.utc)


def context(database, market, symbol, cutoff, series, *, news_days=7, news_limit=100):
    stamp = utc_stamp(cutoff)
    if stamp > datetime.now(timezone.utc) or market not in ("TEFAS","ETF"):
        raise ValueError("invalid_cutoff_or_market")
    if not isinstance(symbol,str) or not symbol.strip() or not isinstance(series,list) or len(series)>50:
        raise ValueError("invalid_context_request")
    if type(news_days) is not int or not 1<=news_days<=90 or type(news_limit) is not int or not 1<=news_limit<=200:
        raise ValueError("invalid_news_policy")
    # Macro dates lack time and time zone. A two-day UTC buffer is conservative
    # even for releases late in the source-local day; exact timestamps preferred.
    macro_day = stamp.date()-timedelta(days=2)
    out = dict(market=market,symbol=symbol,cutoff=stamp.isoformat(),
               macro_release_cutoff=macro_day.isoformat(),macro=[],news=[],
               alerts=[],status="research_only",sources_independently_verified=False,
               point_in_time_vintages_verified=False,live_data_verified=False,
               real_orders=False,execution_allowed=False)
    seen = set()
    with closing(sqlite3.connect(Path(database).resolve().as_uri()+"?mode=ro",uri=True)) as db, db:
        db.execute("BEGIN")
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for spec in series:
            source, name, unit = (spec[k] for k in ("source","series","unit"))
            identity = (source,name,unit)
            age_limit = spec["max_age_days"]
            threshold = Decimal(str(spec["change_threshold"]))
            if source not in ("TCMB EVDS","FRED") or not all(isinstance(v,str) and v.strip() for v in identity) or identity in seen:
                raise ValueError("invalid_or_duplicate_series")
            if type(age_limit) is not int or age_limit<1 or not threshold.is_finite() or threshold<=0:
                raise ValueError("invalid_macro_policy")
            seen.add(identity)
            rows = db.execute("SELECT period,released,value FROM fund_macro WHERE source=? AND series=? AND unit=? AND released<=? ORDER BY period,released",
                              identity+(macro_day.isoformat(),)).fetchall() if "fund_macro" in tables else []
            vintages = {}
            for period,released,value in rows:
                p,r = date.fromisoformat(period),date.fromisoformat(released)
                v = Decimal(value)
                if not p<=r<=macro_day or not v.is_finite():
                    raise ValueError("invalid_macro_observation")
                vintages[p]=(r,v)
            item=dict(source=source,series=name,unit=unit,status="missing")
            if vintages:
                periods=sorted(vintages)
                p=periods[-1]
                r,v=vintages[p]
                age=(stamp.date()-r).days
                item.update(period=p.isoformat(),released=r.isoformat(),value=str(v),
                            age_days=age,period_age_days=(stamp.date()-p).days,
                            status="stale" if age>age_limit or (stamp.date()-p).days>age_limit else "available")
                if len(periods)>1:
                    old=vintages[periods[-2]][1]
                    change=v-old
                    item["change_in_source_units"]=str(change)
                    if abs(change)>=threshold:
                        out["alerts"].append(dict(code="macro_change_review",series=name,
                                                  source=source,change=str(change),unit=unit))
            if item["status"]!="available":
                out["alerts"].append(dict(code="macro_unavailable",series=name,source=source))
            out["macro"].append(item)
        if "fund_news" in tables:
            lower=stamp-timedelta(days=news_days)
            rows=db.execute("SELECT id,symbol,source,title,url,published FROM fund_news WHERE market=? AND symbol IN (?, '*') AND published>=? AND published<=? ORDER BY published DESC,id LIMIT ?",
                            (market,symbol,lower.isoformat(),stamp.isoformat(),news_limit+1)).fetchall()
            out["news_truncated"]=len(rows)>news_limit
            for key,sym,src,title,url,published in rows[:news_limit]:
                event_time=utc_stamp(published)
                if not lower<=event_time<=stamp:
                    raise ValueError("invalid_news_timestamp")
                out["news"].append(dict(id=key,symbol=sym,source=src,title=title,url=url,
                                        published=event_time.isoformat(),source_verified=False))
            out["news_archive_available"]=True
        else:
            out["news_archive_available"]=False
            out["news_truncated"]=False
            out["alerts"].append(dict(code="news_archive_missing"))
    if out["news"]:
        out["alerts"].append(dict(code="disclosure_review",count=len(out["news"])))
    if out["news_truncated"]:
        out["alerts"].append(dict(code="news_truncated"))
    if not series:
        out["alerts"].append(dict(code="macro_not_configured"))
    if out["alerts"]:
        out["status"]="review_required"
    return out


def contextual_decision(metrics, ranking, information, *, held=False):
    """Context may defer new exposure, never override an existing risk exit."""
    base=decide(metrics,ranking,held=held)
    result=dict(base,base_action=base["action"],context_alerts=information.get("alerts",[]),
                context_verified=False,execution_allowed=False,real_orders=False)
    aligned=(information.get("market")==metrics.get("market") and
             information.get("symbol")==metrics.get("symbol"))
    # Historical context must not be applied to an observation that was not yet known.
    try:
        aligned=aligned and date.fromisoformat(metrics["last_session"])<utc_stamp(information["cutoff"]).date()
    except (KeyError,TypeError,ValueError):
        aligned=False
    if not aligned or information.get("status")!="research_only":
        if base["action"]=="BUY_REVIEW":
            result.update(action="WAIT",reason_tr="Makro/haber bağlamı eksik veya inceleme gerektiriyor; yeni alım değerlendirmesi ertelendi.")
    return result


if __name__=="__main__":
    import argparse
    import json
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ("database","market","symbol","cutoff","manifest"):
        p.add_argument("--"+arg,required=True)
    a=p.parse_args()
    with open(a.manifest,encoding="utf-8") as f:
        specs=json.load(f)
    print(json.dumps(context(a.database,a.market,a.symbol,a.cutoff,specs),
                     ensure_ascii=False,indent=2,allow_nan=False))
