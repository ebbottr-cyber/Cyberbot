"""Opt-in Stooq daily price import. Verify provider terms before enabling."""
import argparse
import csv
import io
import re
import tempfile
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from tools.fund_etf_import import ingest

def run(database, symbol, currency, *, enabled=False, canonical_symbol=None):
    if enabled is not True:
        raise ValueError("Explicit provider permission required")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,24}", symbol):
        raise ValueError("Invalid Stooq symbol")
    canonical_symbol=canonical_symbol or symbol.upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.=-]{0,24}",canonical_symbol):
        raise ValueError("Invalid canonical symbol")
    url = "https://stooq.com/q/d/l/?" + urlencode({"s":symbol,"i":"d"})
    with urlopen(url, timeout=20) as response:
        if not response.geturl().startswith("https://stooq.com/"):
            raise ValueError("Unexpected response origin")
        raw=response.read(4_000_001)
    if len(raw)>4_000_000:
        raise ValueError("Response too large")
    reader=csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if not {"Date","Close"}.issubset(reader.fieldnames or []):
        raise ValueError("Provider data unavailable")
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/"prices.csv"
        with path.open("w",encoding="utf-8",newline="") as f:
            writer=csv.writer(f)
            writer.writerow(["symbol","date","close"])
            seen=set()
            for row in reader:
                if row["Date"] in seen:
                    raise ValueError("duplicate_stooq_session")
                seen.add(row["Date"])
                writer.writerow([canonical_symbol,row["Date"],row["Close"]])
        return ingest(database,path,"ETF","Stooq",currency)

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database",required=True)
    p.add_argument("--symbol",required=True)
    p.add_argument("--currency",required=True)
    p.add_argument("--enable",action="store_true")
    a=p.parse_args()
    print(run(a.database,a.symbol,a.currency,enabled=a.enable))
