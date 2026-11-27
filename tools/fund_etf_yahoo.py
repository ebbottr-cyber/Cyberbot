"""Optional yfinance adapter; personal research only after terms review."""
import csv
import re
import tempfile
from pathlib import Path
from tools.fund_etf_import import ingest
from tools.fund_etf_stooq import run as stooq

def yahoo(database, symbol, currency, *, enabled=False):
    if enabled is not True:
        raise ValueError("Explicit provider permission required")
    if not re.fullmatch(r"[A-Za-z0-9^][A-Za-z0-9.=-]{0,24}",symbol):
        raise ValueError("Invalid symbol")
    import yfinance as yf
    ticker=yf.Ticker(symbol)
    data=ticker.history(period="5y",interval="1d",auto_adjust=False,timeout=20,raise_errors=True)
    if data.empty or len(data)>2000:
        raise ValueError("Missing or unexpected history")
    metadata=ticker.history_metadata
    if metadata.get("currency") != currency or metadata.get("instrumentType") != "ETF":
        raise ValueError("ETF type or currency not verified")
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/"prices.csv"
        with path.open("w",encoding="utf-8",newline="") as f:
            writer=csv.writer(f)
            writer.writerow(["symbol","date","close"])
            for stamp,row in data.iterrows():
                writer.writerow([symbol,stamp.date().isoformat(),row["Close"]])
        return ingest(database,path,"ETF","Yahoo Finance",currency)

def fetch(database, symbol, currency, *, yahoo_enabled=False, stooq_enabled=False, stooq_symbol=None):
    errors=[]
    if yahoo_enabled is True:
        try:
            return {"result":yahoo(database,symbol,currency,enabled=True),"errors":errors}
        except Exception as exc:
            errors.append({"provider":"Yahoo Finance","error_type":type(exc).__name__})
    if stooq_enabled is True and stooq_symbol:
        try:
            return {"result":stooq(database,stooq_symbol,currency,enabled=True),"errors":errors}
        except Exception as exc:
            errors.append({"provider":"Stooq","error_type":type(exc).__name__})
    return {"status":"data_unavailable","errors":errors,"live_data_verified":False,"real_orders":False}
