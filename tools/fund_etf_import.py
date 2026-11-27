"""Offline, personal research archive. No network, orders or paid fallback."""
import argparse
import csv
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

def ingest(database, filename, market, source, currency):
    if market not in ("TEFAS", "ETF"):
        raise ValueError("Unsupported market")
    if currency not in ("TRY", "USD", "EUR", "GBP"):
        raise ValueError("Unsupported currency")
    if market == "TEFAS" and currency != "TRY":
        raise ValueError("TEFAS requires TRY in this initial importer")
    if not source.strip():
        raise ValueError("Source required")
    rows = []
    with open(filename, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            symbol = row["symbol"].strip().upper()
            session = date.fromisoformat(row["date"])
            price = Decimal(row["close"])
            if not symbol or session > date.today() or not price.is_finite() or price <= 0:
                raise ValueError("Invalid observation")
            rows.append((market, symbol, session.isoformat(), currency, str(price), source))
    if not rows:
        raise ValueError("Empty input")
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE IF NOT EXISTS fund_prices (market TEXT, symbol TEXT, session TEXT, currency TEXT, close TEXT, source TEXT, PRIMARY KEY(market,symbol,session,currency,source))")
        db.executemany("INSERT INTO fund_prices VALUES (?,?,?,?,?,?) ON CONFLICT DO NOTHING", rows)
    return {"input_rows": len(rows), "market": market, "source": source, "live_data_verified": False, "real_orders": False}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database", required=True)
    p.add_argument("--csv", required=True)
    p.add_argument("--market", choices=["TEFAS", "ETF"], required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--currency", required=True)
    a = p.parse_args()
    print(ingest(Path(a.database), a.csv, a.market, a.source, a.currency))

if __name__ == "__main__":
    main()
