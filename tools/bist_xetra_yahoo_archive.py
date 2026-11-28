"""Private historical research collection. No trading, no access-control bypass."""
import argparse, datetime as dt, json, math, sqlite3, time, tempfile, zipfile
from pathlib import Path
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

UTC=dt.timezone.utc
START="2026-10-03"
END="2026-11-27"
FIELDS=("Open","High","Low","Close","Volume")
def write(p,data):
    t=p.with_suffix(".tmp")
    t.write_text(json.dumps(data,indent=2,ensure_ascii=False))
    t.replace(p)
def plan(source,out):
    out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp,zipfile.ZipFile(source) as z:
        p=z.extract("Cyberbot_3_Piyasa_Gunluk.sqlite3",tmp)
        with sqlite3.connect(p) as db:
            symbols={s for s, in db.execute("SELECT code FROM attempts")}
    inv={"BIST":sorted(s for s in symbols if s.endswith(".IS")),"XETRA":sorted(s for s in symbols if s.endswith(".DE"))}
    assert {k:len(v) for k,v in inv.items()}=={"BIST":803,"XETRA":1749}
    write(out/"inventory.json",inv)
def collect(source,out,market,shard):
    out.mkdir(parents=True,exist_ok=True)
    inv=json.loads(source.read_text())
    symbols=inv[market][shard*200:(shard+1)*200]
    assert symbols
    cutoff=dt.datetime.now(UTC)
    report={"market":market,"shard":shard,"source":"Yahoo Finance via yfinance","start":START,"end_exclusive":END,"interval":"5m","research_only":True,"provider_rights_independently_verified":False,"auto_adjust":False,"venue_verified":False,"orders":False,"expected":len(symbols),"symbols":{},"stopped":False}
    db=sqlite3.connect(out/"candles.sqlite3")
    db.execute("CREATE TABLE candles_5m(market TEXT,ticker TEXT,ts_utc TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,fetched_at_utc TEXT,PRIMARY KEY(market,ticker,ts_utc))")
    for ticker in symbols:
        try:
            frame=yf.Ticker(ticker).history(start=START,end=END,interval="5m",auto_adjust=False,prepost=False,timeout=20,raise_errors=True)
            if frame.empty: raise ValueError("Empty response")
            if frame.index.tz is None: raise ValueError("Missing timezone")
            rows=[]; seen=set(); rejected=0
            fetched=dt.datetime.now(UTC).isoformat()
            for stamp,r in frame.iterrows():
                t=stamp.to_pydatetime().astimezone(UTC)
                o,h,l,c,v=(float(r[k]) for k in FIELDS)
                if t in seen or t.second or t.microsecond or t.minute%5 or t+dt.timedelta(minutes=5)>cutoff or not all(map(math.isfinite,(o,h,l,c,v))) or min(o,h,l,c)<=0 or v<0 or h<max(o,l,c) or l>min(o,h,c):
                    rejected+=1;continue
                seen.add(t);rows.append((market,ticker,t.isoformat(),o,h,l,c,v,fetched))
            with db: db.executemany("INSERT INTO candles_5m VALUES (?,?,?,?,?,?,?,?,?)",rows)
            report["symbols"][ticker]={"rows":len(rows),"rejected":rejected,"status":"ok" if rows else "no_valid_rows"}
        except Exception as exc:
            msg=str(exc)
            report["symbols"][ticker]={"rows":0,"status":"error","error_type":type(exc).__name__,"error":msg[:500]}
            if isinstance(exc,YFRateLimitError) or any(k in msg.lower() for k in ("429","403","401","rate limit","too many requests","unauthorized","forbidden","access denied")):
                report["stopped"]=True
        write(out/"coverage.json",report)
        if report["stopped"]:break
        time.sleep(3)
    report["integrity_check"]=db.execute("PRAGMA integrity_check").fetchone()[0]
    report["rows"]=db.execute("SELECT count(*) FROM candles_5m").fetchone()[0]
    db.close()
    write(out/"coverage.json",report)
    print(json.dumps({k:v for k,v in report.items() if k!="symbols"}),flush=True)
    if report["stopped"] or report["integrity_check"]!="ok":raise SystemExit("Access limit or integrity failure: stop; no automatic retry")
def summary(source,out):
    out.mkdir(parents=True,exist_ok=True)
    inv=json.loads((source/"bist-xetra-inventory"/"inventory.json").read_text())
    reports={}
    for market,expected in inv.items():
        seen={};bad=[];rows=0
        for f in source.glob(f"bist-xetra-{market}-*/coverage.json"):
            p=json.loads(f.read_text())
            if p.get("integrity_check")!="ok":
                bad.append(f.parent.name);continue
            db=sqlite3.connect((f.parent/"candles.sqlite3").resolve().as_uri()+"?mode=ro",uri=True)
            assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
            counts=dict(db.execute("SELECT ticker,count(*) FROM candles_5m GROUP BY ticker"))
            db.close()
            assert sum(counts.values())==p["rows"]
            assert all(counts.get(s,0)==v["rows"] for s,v in p["symbols"].items())
            assert not (set(seen)&set(p["symbols"])) and set(p["symbols"])<=set(expected)
            seen.update(p["symbols"]);rows+=p["rows"]
        missing=[s for s in expected if seen.get(s,{}).get("rows",0)==0]
        reports[market]={"target":len(expected),"attempted":len(seen),"downloaded":len(expected)-len(missing),"rows":rows,"missing":missing,"unverified_shards":bad,"symbols":seen}
    write(out/"summary.json",reports)
    print(json.dumps({m:{k:v for k,v in r.items() if k not in ("missing","symbols")} for m,r in reports.items()}))
    if any(r["missing"] or r["unverified_shards"] for r in reports.values()):raise SystemExit("Coverage incomplete; inspect report")
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("mode",choices=["plan","collect","summary"]);p.add_argument("--input",type=Path,required=True);p.add_argument("--output",type=Path,required=True);p.add_argument("--market",choices=["BIST","XETRA"]);p.add_argument("--shard",type=int,default=0);a=p.parse_args()
    if a.mode=="plan":plan(a.input,a.output)
    elif a.mode=="summary":summary(a.input,a.output)
    else:collect(a.input,a.output,a.market,a.shard)
