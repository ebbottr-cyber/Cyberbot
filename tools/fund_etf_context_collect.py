"""Opt-in official macro HTTP adapters and authorized local KAP exports.

Observation dates are not release dates. Current-vintage observations are
recorded at first collection, never backdated into historical knowledge.
"""
import json
import os
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import httpx
from tools.fund_etf_news import ingest

FRED="https://api.stlouisfed.org/fred/series/observations"
EVDS="https://evds3.tcmb.gov.tr/igmevdsms-dis/"
MAX_BYTES=4_000_000


def request_json(url, *, params=None, headers=None):
    # Fixed official endpoints only; never follow redirects or log credentials.
    with httpx.Client(timeout=20,follow_redirects=False,trust_env=False) as client:
        with client.stream("GET",url,params=params,headers=headers) as response:
            if response.status_code!=200:
                raise ValueError("provider_http_"+str(response.status_code))
            if "json" not in response.headers.get("content-type","").lower():
                raise ValueError("unexpected_provider_content")
            raw=bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw)>MAX_BYTES:
                    raise ValueError("response_too_large")
    return json.loads(raw,parse_float=Decimal)


def parse(payload,provider,series,start,end):
    if not isinstance(payload,dict):
        raise ValueError("invalid_macro_response")
    if provider=="fred":
        records=payload.get("observations")
        if isinstance(records,list) and payload.get("count",len(records))!=len(records):
            raise ValueError("incomplete_fred_response")
        field,day_field="value","date"
    elif provider=="evds":
        records=payload.get("items")
        field,day_field=series.replace(".","_"),"Tarih"
    else:
        raise ValueError("invalid_provider")
    if not isinstance(records,list) or not 1<=len(records)<=2000:
        raise ValueError("invalid_macro_rows")
    result={}
    seen=set()
    for row in records:
        raw=row[day_field]
        if provider=="fred":
            day=date.fromisoformat(raw)
        else:
            # Daily EVDS series only. Do not guess monthly/quarterly formats.
            day=datetime.strptime(raw,"%d-%m-%Y").date()
        if day in seen or not start<=day<=end:
            raise ValueError("invalid_or_duplicate_period")
        seen.add(day)
        value=row[field]
        if value is None or value in ("","."):
            continue
        n=Decimal(str(value))
        if not n.is_finite():
            raise ValueError("nonfinite_macro_value")
        result[day.isoformat()]=str(n)
    if not result:
        raise ValueError("macro_values_missing")
    return result


def store(database,source,series,unit,values,collected):
    """Keep previous vintages; reject conflicting same-day values atomically."""
    inserted=0
    with closing(sqlite3.connect(database,timeout=20)) as db,db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS fund_macro (source TEXT,series TEXT,unit TEXT,period TEXT,released TEXT,value TEXT,PRIMARY KEY(source,series,unit,period,released))")
        for period,value in sorted(values.items()):
            if date.fromisoformat(period)>collected or not Decimal(value).is_finite():
                raise ValueError("invalid_collected_observation")
            last=db.execute("SELECT released,value FROM fund_macro WHERE source=? AND series=? AND unit=? AND period=? ORDER BY released DESC LIMIT 1",(source,series,unit,period)).fetchone()
            if last:
                if last[0]>collected.isoformat():
                    raise ValueError("collection_clock_regression")
                if Decimal(last[1])==Decimal(value):
                    continue
                if last[0]==collected.isoformat():
                    raise ValueError("same_day_revision_review_required")
            db.execute("INSERT INTO fund_macro VALUES (?,?,?,?,?,?)",(source,series,unit,period,collected.isoformat(),value))
            inserted+=1
    return inserted


def macro(database,job):
    provider=job["provider"]
    series=job["series"]
    unit=job["unit"]
    if not isinstance(unit,str) or not unit.strip() or len(unit)>100:
        raise ValueError("invalid_unit")
    if not re.fullmatch(r"[A-Za-z0-9_.]{1,80}",series):
        raise ValueError("invalid_series")
    days=job.get("lookback_days",365)
    if type(days) is not int or not 30<=days<=1500:
        raise ValueError("invalid_lookback")
    today=datetime.now(timezone.utc).date()
    start=today-timedelta(days=days)
    if provider=="fred":
        key=os.environ.get("FRED_API_KEY")
        if not key:
            raise ValueError("fred_key_missing")
        payload=request_json(FRED,params=dict(series_id=series,api_key=key,file_type="json",
                    observation_start=start.isoformat(),observation_end=today.isoformat(),
                    realtime_start=today.isoformat(),realtime_end=today.isoformat(),limit=2000))
        source="FRED"
    elif provider=="evds":
        key=os.environ.get("EVDS_API_KEY")
        if not key:
            raise ValueError("evds_key_missing")
        if job.get("frequency")!="daily":
            raise ValueError("evds_daily_only")
        url=EVDS+"series="+series+"&startDate="+start.strftime("%d-%m-%Y")+"&endDate="+today.strftime("%d-%m-%Y")+"&type=json"
        payload=request_json(url,headers={"key":key})
        source="TCMB EVDS"
    else:
        raise ValueError("unsupported_macro_provider")
    values=parse(payload,provider,series,start,today)
    inserted=store(database,source,series,unit,values,today)
    return dict(status="collected",provider=provider,series=series,observations=len(values),
                inserted=inserted,collected_on=today.isoformat(),release_dates_verified=False,
                vintage_policy="first_seen_utc_date",live_data_verified=False,real_orders=False)


def kap_export(database,job):
    """Only authorized local exports, not KAP private API or website scraping."""
    path=Path(job["file"])
    if not path.is_file() or path.stat().st_size>MAX_BYTES:
        raise ValueError("invalid_kap_export")
    with path.open(encoding="utf-8-sig") as f:
        obj=json.load(f)
    stamp=datetime.fromisoformat(obj["exported_at"].replace("Z","+00:00"))
    now=datetime.now(timezone.utc)
    if stamp.tzinfo is None or not 0<=(now-stamp).total_seconds()<=86400:
        raise ValueError("stale_kap_export")
    items=obj["items"]
    if not isinstance(items,list) or len(items)>5000:
        raise ValueError("invalid_kap_items")
    for item in items:
        published=datetime.fromisoformat(item["published"].replace("Z","+00:00"))
        if item["source"]!="KAP" or published.tzinfo is None or published>stamp:
            raise ValueError("invalid_kap_disclosure")
    return dict(status="collected",provider="kap_export",inserted=ingest(database,items),
                exported_at=stamp.isoformat(),coverage_verified=False,
                live_data_verified=False,real_orders=False)


def run(database,jobs):
    if not isinstance(jobs,list) or len(jobs)>20:
        raise ValueError("invalid_context_jobs")
    results=[]
    for job in jobs:
        try:
            if job.get("rights_confirmed") is not True or job.get("free_access_confirmed") is not True:
                raise ValueError("provider_permission_required")
            if job["provider"]=="kap_export":
                results.append(kap_export(database,job))
            else:
                results.append(macro(database,job))
        except Exception as exc:
            # HTTP exceptions can contain a URL with FRED credentials.
            results.append(dict(status="blocked",provider=job.get("provider") if isinstance(job,dict) else None,
                                error_type=type(exc).__name__,real_orders=False))
    return dict(status="blocked" if any(r["status"]=="blocked" for r in results) else "collected",
                results=results,real_orders=False,live_data_verified=False)
