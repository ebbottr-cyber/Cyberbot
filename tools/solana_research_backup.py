"""Local SQLite backup and non-destructive recovery of dedicated Solana research DBs."""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import time
import uuid
from contextlib import closing
from datetime import datetime,timezone,timedelta
from pathlib import Path
from tools.dexterm_research_archive import APP_ID as RESEARCH_ID
from tools.solana_model_history import APP_ID as HISTORY_ID
from tools.solana_paper_replay import FALSE_FLAGS,instant
from tools.solana_research_scheduler import exclusive

FILES={"solana-research.sqlite3":(RESEARCH_ID,"research_reports","digest"),
       "solana-model-history.sqlite3":(HISTORY_ID,"experiments","id")}
MANIFEST="manifest.json"
MIN_RESERVE=2*1024**3
MAX_DB_BYTES=1024**3
MAX_SETS=60

def regular(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected regular research file")
    return path

def fingerprint(path):
    h=hashlib.sha256()
    with regular(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def open_read(path):
    return sqlite3.connect(regular(path).resolve().as_uri()+"?mode=ro",uri=True,timeout=5)

def check(con,name):
    app,table,key=FILES[name]
    if con.execute("PRAGMA application_id").fetchone()[0]!=app or con.execute("PRAGMA user_version").fetchone()[0]!=1:
        raise ValueError("Unexpected database type")
    if con.execute("PRAGMA integrity_check").fetchall()!=[("ok",)]:
        raise ValueError("SQLite integrity check failed")
    if con.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise ValueError("Broken archive reference")
    n=0
    for ident,payload in con.execute(f"SELECT {key},payload FROM {table}"):
        if not isinstance(payload,str) or hashlib.sha256(payload.encode("utf-8")).hexdigest()!=ident:
            raise ValueError("Research payload digest mismatch")
        n+=1
    return n

def verify_db(path,name):
    if regular(path).stat().st_size>MAX_DB_BYTES:raise ValueError("Database exceeds backup budget")
    with closing(open_read(path)) as con:return check(con,name)

def copy_db(source,target,name):
    with closing(open_read(source)) as src:
        if src.execute("PRAGMA application_id").fetchone()[0]!=FILES[name][0] or src.execute("PRAGMA user_version").fetchone()[0]!=1:
            raise ValueError("Unexpected source database type")
        size=src.execute("PRAGMA page_count").fetchone()[0]*src.execute("PRAGMA page_size").fetchone()[0]
        if size>MAX_DB_BYTES:raise ValueError("Database exceeds backup budget")
        if shutil.disk_usage(target.parent).free<MIN_RESERVE+size*2:raise ValueError("Insufficient backup disk space")
        fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        deadline=time.monotonic()+60
        def progress(status,remaining,total):
            if time.monotonic()>deadline:raise TimeoutError("Backup time budget exceeded")
        with closing(sqlite3.connect(target,timeout=5)) as dst:
            src.backup(dst,pages=128,progress=progress,sleep=.05)
    n=verify_db(target,name)
    return {"sha256":fingerprint(target),"bytes":target.stat().st_size,"records":n}

def load_manifest(folder):
    path=regular(folder/MANIFEST)
    with path.open("rb") as f:raw=f.read(65537)
    if len(raw)>65536:raise ValueError("Manifest too large")
    m=json.loads(raw)
    if m.get("version")!=1 or m.get("kind")!="solana_research_backup" or set(m.get("files",{}))!=set(FILES):
        raise ValueError("Invalid backup manifest")
    instant(m["created_utc"])
    return m

def verify(folder):
    folder=Path(folder).resolve(strict=True)
    m=load_manifest(folder)
    for name in FILES:
        path=regular(folder/name);meta=m["files"][name]
        if path.stat().st_size!=meta["bytes"] or fingerprint(path)!=meta["sha256"]:
            raise ValueError("Backup checksum mismatch")
        if verify_db(path,name)!=meta["records"]:raise ValueError("Backup record count mismatch")
    return m

def backup(data_root,*,daily=False,now=None):
    if type(daily) is not bool:raise ValueError("Invalid backup mode")
    root=Path(data_root).resolve(strict=True)
    now=datetime.now(timezone.utc) if now is None else now
    if now.tzinfo is None:raise ValueError("Timezone required")
    now=now.astimezone(timezone.utc)
    lock=root/"solana-research.sqlite3.research.lock"
    with exclusive(lock):
        present=[(root/name).exists() for name in FILES]
        if not any(present):return {"status":"no_databases_yet",**FALSE_FLAGS}
        if not all(present):raise ValueError("Both research databases required")
        dest=root/"backups"
        if dest.is_symlink():raise ValueError("Invalid backup directory")
        dest.mkdir(exist_ok=True)
        sets=[x for x in dest.iterdir() if x.name.startswith("solana-") and x.is_dir() and not x.is_symlink()]
        if daily:
            for f in sorted(sets,key=lambda x:x.name,reverse=True):
                if not (f/MANIFEST).is_file():continue
                m=load_manifest(f);created=instant(m["created_utc"])
                if created>now:raise ValueError("Future backup timestamp")
                if now-created<timedelta(hours=24):
                    # A prior manifest is not a fresh integrity verification.
                    return {"status":"backup_not_due","last_backup_utc":created.isoformat(),
                            "integrity_rechecked":False,**FALSE_FLAGS}
                break
        if len(sets)>=MAX_SETS:raise ValueError("Backup capacity reached; review old sets manually")
        folder=dest/("solana-"+now.strftime("%Y%m%d-%H%M%S")+"-"+uuid.uuid4().hex)
        folder.mkdir(mode=0o700)
        try:
            entries={name:copy_db(root/name,folder/name,name) for name in FILES}
            m={"version":1,"kind":"solana_research_backup","created_utc":now.isoformat(),"files":entries,
               "cross_database_atomic_snapshot_verified":False}
            with (folder/MANIFEST).open("x",encoding="utf-8") as f:
                json.dump(m,f,indent=2,allow_nan=False);f.flush();os.fsync(f.fileno())
            verify(folder)
        except Exception:
            # Only clean up the fresh set owned by this invocation.
            shutil.rmtree(folder)
            raise
        return {"status":"backup_complete","backup_directory":str(folder),"files":entries,
                "integrity_rechecked":True,"cross_database_atomic_snapshot_verified":False,**FALSE_FLAGS}

def restore(backup_folder,destination,*,confirmed=False):
    if confirmed is not True:raise ValueError("Explicit restore permission required")
    source=Path(backup_folder).resolve(strict=True)
    target=Path(destination).resolve()
    if target.exists() or target==source or source in target.parents:
        raise ValueError("Restore requires a new directory outside backup set")
    m=verify(source)
    if shutil.disk_usage(target.parent).free<MIN_RESERVE+sum(x["bytes"] for x in m["files"].values()):
        raise ValueError("Insufficient restore disk space")
    target.mkdir(mode=0o700)
    try:
        for name in FILES:
            path=target/name
            with regular(source/name).open("rb") as src,path.open("xb") as dst:
                shutil.copyfileobj(src,dst,1024*1024);dst.flush();os.fsync(dst.fileno())
            if fingerprint(path)!=m["files"][name]["sha256"] or verify_db(path,name)!=m["files"][name]["records"]:
                raise ValueError("Restored database verification failed")
        # Restored data is intentionally not connected to any existing scheduler.
        (target/"solana-research.sqlite3.research.stop").touch(exist_ok=False)
    except Exception:
        shutil.rmtree(target)
        raise
    return {"status":"restore_complete","restored_directory":str(target),"source_overwritten":False,
            "existing_database_overwritten":False,"scheduler_enabled":False,"stop_marker_created":True,**FALSE_FLAGS}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="mode",required=True)
    b=sub.add_parser("backup");b.add_argument("--data-root",required=True);b.add_argument("--daily",action="store_true")
    v=sub.add_parser("verify");v.add_argument("--backup-folder",required=True)
    r=sub.add_parser("restore");r.add_argument("--backup-folder",required=True);r.add_argument("--destination",required=True);r.add_argument("--confirm-restore",action="store_true")
    a=p.parse_args()
    try:
        if a.mode=="backup":out=backup(a.data_root,daily=a.daily)
        elif a.mode=="verify":out={"status":"backup_verified","manifest":verify(a.backup_folder),**FALSE_FLAGS}
        else:out=restore(a.backup_folder,a.destination,confirmed=a.confirm_restore)
        print(json.dumps(out,indent=2,allow_nan=False));return 0
    except (ValueError,TypeError,KeyError,AttributeError,ArithmeticError,OSError,sqlite3.Error) as e:
        print(json.dumps({"status":"backup_or_restore_rejected","error_type":type(e).__name__,**FALSE_FLAGS}));return 1

if __name__=="__main__":raise SystemExit(main())
