"""Opt-in TEFAS JSON price history. Community-documented web endpoint, not an SLA.

No authentication circumvention, retries, paid fallback or automatic access.
"""
import csv
import json
import re
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import httpx
from tools.fund_etf_import import ingest

URL="https://www.tefas.gov.tr/api/funds/fonFiyatBilgiGetir"


def parse_history(payload,symbol,*,today=None):
    today=today or date.today()
    if not isinstance(payload,dict) or payload.get("errorCode") or payload.get("errorMessage"):
        raise ValueError("tefas_provider_error")
    rows=payload.get("resultList")
    if not isinstance(rows,list) or not 2<=len(rows)<=2000:
        raise ValueError("tefas_empty_or_invalid_history")
    seen=set(); result=[]
    for row in rows:
        if row.get("fonKodu")!=symbol:
            raise ValueError("tefas_symbol_mismatch")
        raw=row["tarih"]
        if not isinstance(raw,str):
            raise ValueError("unsupported_tefas_date")
        try:
            day=date.fromisoformat(raw)
        except ValueError:
            day=datetime.strptime(raw,"%d.%m.%Y").date()
        price=Decimal(str(row["fiyat"]))
        if day>today or day in seen or not price.is_finite() or price<=0:
            raise ValueError("invalid_tefas_observation")
        seen.add(day)
        result.append((symbol,day.isoformat(),str(price)))
    return sorted(result,key=lambda r:r[1])


def fetch(database,symbol,*,months=60,enabled=False):
    if enabled is not True:
        raise ValueError("tefas_permission_required")
    if not re.fullmatch(r"[A-Z0-9]{3,12}",symbol) or type(months) is not int or months not in (1,3,6,12,36,60):
        raise ValueError("invalid_tefas_request")
    with httpx.Client(timeout=20,follow_redirects=False,headers={"User-Agent":"Cyberbot personal research","Accept":"application/json"}) as client:
        with client.stream("POST",URL,json={"fonKodu":symbol,"dil":"TR","periyod":str(months)}) as response:
            response.raise_for_status()
            if "application/json" not in response.headers.get("content-type","").lower():
                raise ValueError("unexpected_tefas_content")
            raw=bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw)>4_000_000:
                    raise ValueError("tefas_response_too_large")
    rows=parse_history(json.loads(raw,parse_float=Decimal),symbol)
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/"tefas.csv"
        with path.open("w",encoding="utf-8",newline="") as f:
            w=csv.writer(f);w.writerow(["symbol","date","close"]);w.writerows(rows)
        return ingest(database,path,"TEFAS","TEFAS", "TRY")
