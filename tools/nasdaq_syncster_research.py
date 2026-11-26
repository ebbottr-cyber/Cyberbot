"""Private research archive only; no Yahoo requests, no trading."""
import argparse,csv,hashlib,json,os,re,sqlite3,tempfile,time,zipfile
from pathlib import Path
import pandas as pd
import numpy as np
from huggingface_hub import HfApi,hf_hub_download
from huggingface_hub.errors import HfHubHTTPError

REPO="syncster-data/historical-market-data"
SHA="419a364141b485042eb0dd53d1b213a4ac95bfe3764e1ba90fe3541f769a1a73"
REVIEW=set("AAPG ASML BRBI BZ CDZIP CHWM CIGI CMPS DDI DGXX DOO ELVR GAIN GOOD GOOG GVH HAO IVA KSPI LOGI MDBH MNSBP NBTX NCTY NVX OBAI ORGO PAYP QNTM SHOP SIFY SLN STHO SY WAFDP XNDU YJ YXT Z".split())
START=pd.Timestamp("2026-08-26",tz="UTC")
END=pd.Timestamp("2026-10-25",tz="UTC")
def plan(archive,out):
    with tempfile.TemporaryDirectory() as tmp,zipfile.ZipFile(archive) as z:
        p=z.extract("Cyberbot_3_Piyasa_Gunluk.sqlite3",tmp)
        with sqlite3.connect(p) as db:
            symbols=sorted({s for s, in db.execute("SELECT code FROM attempts") if not s.endswith((".IS",".DE"))})
    assert len(symbols)==3400 and hashlib.sha256(("\n".join(symbols)+"\n").encode()).hexdigest()==SHA
    api=HfApi()
    revision=api.dataset_info(REPO).sha
    files=set(api.list_repo_files(REPO,repo_type="dataset",revision=revision))
    rows=[]
    for s in symbols:
        assert re.fullmatch(r"[A-Z][A-Z0-9]{0,4}",s)
        path=f"data/stocks/1m/{s[0]}/{s}.parquet"
        rows.append(dict(symbol=s,path=path,listed=path in files,type_review=s in REVIEW))
    report=dict(revision=revision,source=REPO,inventory_sha256=SHA,start=str(START),end_exclusive=str(END),candidates=len(rows),source_files_found=sum(r["listed"] for r in rows),type_review=len(REVIEW),rows=rows)
    out.mkdir(parents=True,exist_ok=True)
    (out/"plan.json").write_text(json.dumps(report,indent=2))
    print({k:v for k,v in report.items() if k!="rows"})
def aggregate(f,s):
    frame=pd.read_parquet(f,columns=["ts","symbol","open","high","low","close","volume"])
    if not frame["symbol"].astype(str).eq(s).all(): raise ValueError("symbol_mismatch")
    ts=pd.to_datetime(frame.pop("ts"),utc=True,errors="raise")
    frame.index=pd.DatetimeIndex(ts)
    frame=frame.loc[(frame.index>=START)&(frame.index<END)].copy()
    raw=len(frame)
    cols=["open","high","low","close","volume"]
    for k in cols: frame[k]=pd.to_numeric(frame[k],errors="coerce")
    ok=np.isfinite(frame[cols]).all(axis=1)&(frame[["open","high","low","close"]]>0).all(axis=1)&(frame.volume>=0)&(frame.high>=frame[["open","low","close"]].max(axis=1))&(frame.low<=frame[["open","high","close"]].min(axis=1))
    ok=ok&(~frame.index.duplicated(keep=False))&(frame.index.second==0)&(frame.index.microsecond==0)&(frame.index.nanosecond==0)
    frame=frame.loc[ok,cols].sort_index()
    grouped=frame.resample("5min",label="left",closed="left")
    bars=grouped.agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"})
    counts=grouped.size()
    bars=bars.loc[counts==5].copy()
    bars.index.name="ts_utc"
    return bars,dict(raw_1m=raw,invalid_1m=raw-len(frame),incomplete_5m=int(((counts>0)&(counts<5)).sum()),bars_5m=len(bars))
def collect(planfile,out,index,shards,pilot=False):
    p=json.loads(planfile.read_text()); assert p["inventory_sha256"]==SHA
    out.mkdir(parents=True,exist_ok=True)
    rows=[r for i,r in enumerate(p["rows"]) if i%shards==index]
    if pilot: rows=[r for r in p["rows"] if r["symbol"] in {"AAPL","MSFT","NVDA"}]
    reports=[]
    for r in rows:
        s=r["symbol"]
        rec={"symbol":s,"type_review":r["type_review"]}
        if not r["listed"]: rec["status"]="not_in_source"
        else:
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    f=hf_hub_download(REPO,r["path"],repo_type="dataset",revision=p["revision"],local_dir=tmp)
                    bars,stats=aggregate(f,s)
                    rec.update(stats)
                    rec["status"]="downloaded" if len(bars) else "no_complete_bars_in_window"
                    if len(bars):
                        folder=out/("type_review" if r["type_review"] else "equity_candidates")
                        folder.mkdir(exist_ok=True)
                        bars.to_parquet(folder/(s+".parquet"),compression="zstd")
            except Exception as exc:
                rec["status"]="error";rec["error_type"]=type(exc).__name__
                if isinstance(exc,HfHubHTTPError) and exc.response is not None:
                    rec["http_status"]=exc.response.status_code
                if rec.get("http_status") in (401,403,429):
                    reports.append(rec)
                    (out/"coverage.json").write_text(json.dumps(reports,indent=2))
                    raise RuntimeError("Provider access or rate-limit stop; no bypass")
            time.sleep(0.3)
        reports.append(rec)
        (out/"coverage.json").write_text(json.dumps(reports,indent=2))
    print(dict(attempted=len(reports),downloaded=sum(r["status"]=="downloaded" for r in reports),bars=sum(r.get("bars_5m",0) for r in reports)))
    if pilot and (len(reports)!=3 or not all(r["status"]=="downloaded" for r in reports)): raise RuntimeError("Pilot incomplete")
def summarize(root,out):
    reports=[]
    for i in range(12):
        f=root/f"nasdaq-5m-shard-{i}"/"coverage.json"
        if f.exists(): reports.extend(json.loads(f.read_text()))
    p=json.loads((root/"nasdaq-5m-plan"/"plan.json").read_text())
    expected={r["symbol"] for r in p["rows"]}
    seen={r["symbol"] for r in reports}
    assert seen<=expected and len(seen)==len(reports)
    summary=dict(source=REPO,revision=p["revision"],inventory_sha256=SHA,candidates=3400,source_files_found=p["source_files_found"],attempted=len(seen),downloaded=sum(r["status"]=="downloaded" for r in reports),bars_5m=sum(r.get("bars_5m",0) for r in reports),review_downloaded=sum(r["type_review"] and r["status"]=="downloaded" for r in reports),missing_or_failed=sorted((expected-seen)|{r["symbol"] for r in reports if r["status"]!="downloaded"}),start=str(START),end_exclusive=str(END),license="research and education only; other; underlying rights not independently verified",session_coverage_verified=False,live_trading=False,rows=reports)
    out.mkdir(exist_ok=True,parents=True);(out/"summary.json").write_text(json.dumps(summary,indent=2))
    print({k:v for k,v in summary.items() if k not in ("rows","missing_or_failed")})
    if len(seen)!=3400 or summary["missing_or_failed"]: raise SystemExit("Archive incomplete; inspect summary")
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("mode",choices=["plan","pilot","collect","summary"]);p.add_argument("--input",type=Path,required=True);p.add_argument("--output",type=Path,required=True);p.add_argument("--index",type=int,default=0);a=p.parse_args()
    if a.mode=="plan":plan(a.input,a.output)
    elif a.mode=="summary":summarize(a.input,a.output)
    else:collect(a.input,a.output,a.index,12,a.mode=="pilot")
