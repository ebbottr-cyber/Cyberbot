"""Scheduled research refresh with isolated staging and fail-closed quality checks."""
import argparse
import json
import re
import sqlite3
import tempfile
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path

from tools.fund_etf_import import ingest
from tools.fund_etf_yahoo import yahoo
from tools.fund_etf_tefas import fetch as tefas
from tools.fund_etf_stooq import run as stooq

SCHEMA = """CREATE TABLE IF NOT EXISTS fund_prices (
market TEXT, symbol TEXT, session TEXT, currency TEXT, close TEXT, source TEXT,
PRIMARY KEY(market,symbol,session,currency,source))"""


def validate(rows, market, symbol, currency, source, *, max_age_days=7,
             min_rows=2, jump_limit="0.30", today=None):
    today = today or date.today()
    limit = Decimal(str(jump_limit))
    if not limit.is_finite() or not 0 < limit <= 1 or min_rows < 2 or max_age_days < 0:
        raise ValueError("invalid_quality_policy")
    if len(rows) < min_rows:
        raise ValueError("insufficient_history")
    previous = None
    seen = set()
    latest = None
    for m, s, session, c, close, src in sorted(rows, key=lambda r: r[2]):
        if (m, s, c, src) != (market, symbol, currency, source):
            raise ValueError("identity_mismatch")
        day = date.fromisoformat(session)
        price = Decimal(close)
        if day > today or day in seen or not price.is_finite() or price <= 0:
            raise ValueError("invalid_observation")
        if previous is not None and abs(price / previous - 1) > limit:
            raise ValueError("price_jump_review_required")
        previous, latest = price, day
        seen.add(day)
    age = (today - latest).days
    if age > max_age_days:
        raise ValueError("stale_data")
    return {"rows": len(rows), "last_session": latest.isoformat(), "age_days": age}


def refresh(database, job, *, yahoo_enabled=False):
    market = job["market"]
    symbol = job["symbol"].strip().upper()
    currency = job["currency"]
    provider = job["provider"]
    if market not in ("TEFAS", "ETF") or not re.fullmatch(r"[A-Z0-9][A-Z0-9.=-]{0,24}", symbol):
        raise ValueError("invalid_job")
    if currency not in ("TRY", "USD", "EUR", "GBP") or (market == "TEFAS" and currency != "TRY"):
        raise ValueError("invalid_currency")
    with tempfile.TemporaryDirectory() as folder:
        stage = Path(folder) / "stage.sqlite3"
        if provider == "csv":
            source = job["source"].strip()
            if not source:
                raise ValueError("source_required")
            # Check duplicate rows before the existing importer can discard them.
            import csv
            with open(job["csv"], encoding="utf-8-sig", newline="") as f:
                keys = set()
                for row in csv.DictReader(f):
                    key = (row["symbol"].strip().upper(), date.fromisoformat(row["date"]))
                    if key in keys:
                        raise ValueError("duplicate_input")
                    keys.add(key)
            ingest(stage, job["csv"], market, source, currency)
        elif provider == "yahoo" and market == "ETF" and yahoo_enabled:
            source = "Yahoo Finance"
            yahoo(stage, symbol, currency, enabled=True)
        elif provider == "tefas" and market=="TEFAS" and job.get("rights_confirmed") is True and job.get("free_access_confirmed") is True:
            source="TEFAS"
            tefas(stage,symbol,months=job.get("months",60),enabled=True)
        elif provider=="stooq" and market=="ETF" and job.get("rights_confirmed") is True and job.get("free_access_confirmed") is True and job.get("identity_reviewed") is True:
            source="Stooq"
            stooq(stage,job["provider_symbol"],currency,enabled=True,canonical_symbol=symbol)
        else:
            raise ValueError("provider_disabled_or_unsupported")
        with closing(sqlite3.connect(stage)) as db:
            rows = db.execute("SELECT * FROM fund_prices").fetchall()
        policy = dict(max_age_days=int(job.get("max_age_days", 7)),
                      min_rows=int(job.get("min_rows", 2)),
                      jump_limit=job.get("jump_limit", "0.30"))
        quality = validate(rows, market, symbol, currency, source, **policy)
        with closing(sqlite3.connect(database, timeout=20)) as db, db:
            db.execute(SCHEMA)
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM fund_prices WHERE market=? AND symbol=? AND currency=? AND source=?",
                             (market, symbol, currency, source)).fetchall()
            combined = {r[2]: r for r in old}
            for row in rows:
                existing = combined.get(row[2])
                if existing is not None and Decimal(existing[4]) != Decimal(row[4]):
                    raise ValueError("historical_revision_review_required")
                combined[row[2]] = row
            validate(list(combined.values()), market, symbol, currency, source, **policy)
            before = db.total_changes
            db.executemany("INSERT INTO fund_prices VALUES (?,?,?,?,?,?) ON CONFLICT DO NOTHING", rows)
            inserted = db.total_changes - before
        return dict(quality, status="quality_checked", inserted=inserted, source=source,
                    live_data_verified=False, real_orders=False)


def run(database, jobs, *, yahoo_enabled=False):
    if not isinstance(jobs, list) or not jobs or len(jobs) > 100:
        raise ValueError("manifest_requires_1_to_100_jobs")
    results = []
    for job in jobs:
        item = {"market": job.get("market"), "symbol": job.get("symbol")} if isinstance(job, dict) else {}
        try:
            item.update(refresh(database, job, yahoo_enabled=yahoo_enabled))
            item["provider"]=job["provider"]
        except Exception as exc:
            item.update(status="blocked", provider=job.get("provider") if isinstance(job,dict) else None, error_type=type(exc).__name__,
                        reason=str(exc) if isinstance(exc, ValueError) else "provider_or_archive_error",
                        live_data_verified=False, real_orders=False)
        results.append(item)
    return {"status": "blocked" if any(r["status"] == "blocked" for r in results) else "quality_checked",
            "results": results, "live_data_verified": False, "real_orders": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--enable-yahoo", action="store_true", help="Only after provider terms review")
    args = p.parse_args()
    with open(args.manifest, encoding="utf-8") as f:
        jobs = json.load(f)
    report = run(args.database, jobs, yahoo_enabled=args.enable_yahoo)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if report["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
