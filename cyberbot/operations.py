"""Local application health and consistent SQLite backups. No network."""
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

DATABASES={"paper":("CYBERBOT_DB","var/paper.sqlite3",{"state","trades","equity_history"}),
           "learning":("CYBERBOT_LEARNING_DB","var/learning.sqlite3",{"experiments"})}

def sources():
    return {k:Path(os.getenv(env,default)).expanduser().resolve() for k,(env,default,_) in DATABASES.items()}

def inspect_db(path,required):
    if not path.is_file():return "not_initialized"
    try:
        with closing(sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=2)) as db:
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not required.issubset(tables):return "schema_mismatch"
            return "ok" if db.execute("PRAGMA quick_check(1)").fetchone()==("ok",) else "integrity_error"
    except (sqlite3.Error,OSError):return "unreadable"

def health():
    dbs={k:inspect_db(p,DATABASES[k][2]) for k,p in sources().items()}
    return {"status":"ok" if all(v in ("ok","not_initialized") for v in dbs.values()) else "degraded",
            "databases":dbs,"mode":"synthetic_paper","bulk_price_download_enabled":False,"real_orders":False,
            "remote_configured":os.getenv("CYBERBOT_TAILSCALE_ENABLED")=="1",
            "local_llm_configured":os.getenv("CYBERBOT_LOCAL_LLM_ENABLED")=="1" and bool(os.getenv("CYBERBOT_OLLAMA_MODEL")),
            "chronos_configured":os.getenv("CYBERBOT_CHRONOS_ENABLED")=="1" and bool(os.getenv("CYBERBOT_CHRONOS_PATH")),
            "model_runtime_verified":False}

def backup(root):
    root=Path(root).expanduser().resolve()
    paths=sources()
    archive=os.getenv("CYBERBOT_EBBOT_DB")
    if archive and Path(archive).expanduser().resolve() in paths.values():
        raise ValueError("EBBot arşivi yedekleme kapsamına alınamaz.")
    if len(set(paths.values()))!=len(paths):raise ValueError("Uygulama veritabanları ayrı olmalı.")
    root.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix=".partial-",dir=root))
    manifest={"created_at":datetime.now(timezone.utc).isoformat(),"files":[],"skipped":[],"scope":"cyberbot_only"}
    try:
        for name,source in paths.items():
            state=inspect_db(source,DATABASES[name][2])
            if state=="not_initialized":
                manifest["skipped"].append(name)
                continue
            if state!="ok":raise ValueError(name+": "+state)
            target=stage/(name+".sqlite3")
            with closing(sqlite3.connect(source.as_uri()+"?mode=ro",uri=True,timeout=5)) as src, closing(sqlite3.connect(target)) as dst:
                src.backup(dst,pages=128,sleep=.05)
            if inspect_db(target,DATABASES[name][2])!="ok":raise ValueError("Yedek doğrulanamadı.")
            with target.open("rb") as stream:
                digest=hashlib.file_digest(stream,"sha256").hexdigest()
            manifest["files"].append({"name":target.name,"bytes":target.stat().st_size,"sha256":digest})
        if not manifest["files"]:raise ValueError("Yedeklenecek uygulama veritabanı yok.")
        (stage/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
        target=root/("cyberbot-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        stage.rename(target)
        return target
    except BaseException:
        shutil.rmtree(stage,ignore_errors=True)
        raise
