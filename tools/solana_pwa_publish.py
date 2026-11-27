"""Atomic local publication of research status; no public files or network writes."""
import json
import os
import tempfile
from datetime import datetime,timezone
from pathlib import Path
from tools.solana_gemini_review import load
from tools.solana_pwa_status import snapshot,MAX_AGE_SECONDS
from tools.solana_paper_replay import FALSE_FLAGS,instant
from tools.dexterm_research_archive import MAX_BYTES

NAME="solana-research-latest.json"
STATES={"running":"Araştırma sürüyor","partial":"Araştırma eksik kaldı",
        "stopped":"Araştırma durduruldu","error":"Araştırma hatası",
        "unavailable":"Araştırma raporu bulunamadı","ready":"Araştırma raporu hazır"}

def publish(folder,state,report=None):
    if state not in STATES or (state=="ready")!=(report is not None):
        raise ValueError("Invalid publication state")
    now=datetime.now(timezone.utc)
    if report is not None:snapshot(report,now=now)
    body={"version":1,"state":state,"published_utc":now.isoformat(),"report":report}
    data=json.dumps(body,ensure_ascii=False,allow_nan=False,separators=(",",":")).encode("utf-8")
    if len(data)>MAX_BYTES:raise ValueError("Publication too large")
    folder=Path(folder).resolve(strict=True)
    fd,tmp=tempfile.mkstemp(prefix=".solana-publish-",dir=folder)
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(tmp,folder/NAME)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def unavailable(state="unavailable"):
    return {"schema_version":1,"market":"solana","mode":"research_only",
            "publication_state":state,"status_label_tr":STATES[state],
            "report_freshness":"unknown","dataset":None,"models":[],"coverage":None,
            "research_only":True,"live_trading_enabled":False,
            "market_data_freshness_verified":False,"training_allowed":False,
            "production_learning_enabled":False,"model_promoted":False,"weights_updated":False,**FALSE_FLAGS}

def read(folder,*,now=None):
    now=datetime.now(timezone.utc) if now is None else now
    if not folder:return unavailable()
    path=Path(folder)/NAME
    try:body=load(path)
    except FileNotFoundError:return unavailable()
    if body.get("version")!=1 or body.get("state") not in STATES:raise ValueError("Invalid publication")
    state=body["state"];published=instant(body["published_utc"])
    if published>now:raise ValueError("Future publication")
    age=int((now-published).total_seconds())
    if state=="ready":
        out=snapshot(body["report"],now=now)
        if out["report_finished_utc"] and instant(out["report_finished_utc"])>published:
            raise ValueError("Report newer than publication")
    else:
        if body.get("report") is not None:raise ValueError("Unexpected report")
        out=unavailable(state)
    out.update(publication_state=state,published_utc=published.isoformat(),
               publication_age_seconds=age,publication_stale=age>MAX_AGE_SECONDS)
    return out
