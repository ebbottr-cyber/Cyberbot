"""Offline Futures-only backup, verification and isolated recovery staging.

No network, active database replacement, or automatic restoration of trading
permissions. Trust the local operator and filesystem; hashes are not signatures.
"""
import argparse,hashlib,json,os,shutil,sqlite3,tempfile,time
from contextlib import closing
from pathlib import Path
from . import db_paths,observed_pilot as stocks,futures_pilot as pilot
from . import futures_training as training,futures_ai_memory as memory
from . import futures_forward_memory as forward,futures_health as health
from . import futures_supervisor as supervisor

VERSION="futures-backup-1"
MAX_FILE=512*1024*1024
MAX_MANIFEST=16384
TABLES={"training":{training.TABLE},"ai_memory":memory.TABLES,
        "forward":{forward.TABLE},"diagnostics":{health.TABLE},
        "pilot":{"observed_accounts","observed_events"}}
def sources():
    db_paths.checked()
    return {"training":db_paths.futures_training_path(),"ai_memory":db_paths.futures_ai_memory_path(),
            "forward":db_paths.futures_forward_path(),"diagnostics":db_paths.futures_diagnostics_path(),
            "pilot":db_paths.pilot_path()}
def permitted():
    if os.getenv("CYBERBOT_FUTURES_BACKUP_RIGHTS_CONFIRMED")!="1":
        raise ValueError("Futures yedekleme hakkı onaylanmadı.")
def readonly(path):
    return sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=3)
def check(db,name):
    db.execute("PRAGMA trusted_schema=OFF")
    names={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    if names!=TABLES[name] or db.execute("PRAGMA quick_check(1)").fetchone()!=("ok",):
        raise ValueError("Veritabanı bütünlüğü veya şema uyuşmuyor.")
    if db.execute("PRAGMA page_count").fetchone()[0]*db.execute("PRAGMA page_size").fetchone()[0]>MAX_FILE:
        raise ValueError("Veritabanı boyut sınırı.")
def digest(path):
    if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=MAX_FILE:
        raise ValueError("Geçersiz yedek dosyası.")
    with path.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def inspect(path,name):
    with closing(readonly(path)) as db:
        db.execute("PRAGMA query_only=ON");check(db,name)
        if name=="pilot":
            for table in ("observed_accounts","observed_events"):
                if db.execute("SELECT 1 FROM "+table+" WHERE market!='FUTURES' LIMIT 1").fetchone():
                    raise ValueError("Futures dışı pilot kaydı.")
def copy_db(source,target,name):
    with closing(readonly(source)) as src,closing(sqlite3.connect(target)) as dst:
        src.execute("PRAGMA query_only=ON");src.execute("BEGIN");check(src,name)
        if name=="pilot":
            dst.execute("CREATE TABLE observed_accounts(market TEXT PRIMARY KEY,payload TEXT NOT NULL)")
            dst.execute("CREATE TABLE observed_events(id INTEGER PRIMARY KEY,market TEXT NOT NULL,at TEXT NOT NULL,event TEXT NOT NULL,payload TEXT NOT NULL)")
            for row in src.execute("SELECT market,payload FROM observed_accounts WHERE market='FUTURES'"):
                s=json.loads(row[1])
                if s.get("version")!=pilot.VERSION or s.get("symbol") not in ("BTCUSDT","ETHUSDT"):
                    raise ValueError("Futures kasa kimliği geçersiz.")
                dst.execute("INSERT INTO observed_accounts VALUES(?,?)",row)
            dst.executemany("INSERT INTO observed_events VALUES(?,?,?,?,?)",src.execute(
                "SELECT id,market,at,event,payload FROM observed_events WHERE market='FUTURES' ORDER BY id"))
            dst.commit()
        else:
            deadline=time.monotonic()+60
            def progress(status,remaining,total):
                if time.monotonic()>deadline:raise TimeoutError("SQLite yedekleme süresi.")
            src.backup(dst,pages=128,progress=progress,sleep=.05)
    inspect(target,name)
def file_entry(path,name):
    return {"name":name,"file":name+".sqlite3","bytes":path.stat().st_size,"sha256":digest(path)}
def new_stage(root,prefix):
    root=Path(root).expanduser().resolve()
    root.mkdir(parents=True,exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix,dir=root))
def publish(stage,prefix):
    target=stage.with_name(prefix+stage.name.removeprefix(".partial-"))
    if target.exists():raise ValueError("Hedef zaten var.")
    stage.rename(target);return target
def backup(root,*,offline_confirmed=False,clock=stocks.utc):
    permitted()
    if not offline_confirmed:raise ValueError("Tüm yerel yazıcılar durdurulmalı.")
    paths=sources()
    if paths["pilot"].is_file() and os.getenv("CYBERBOT_PILOT_BACKUP_RIGHTS_CONFIRMED")!="1":
        raise ValueError("Pilot yedekleme hakkı onaylanmadı.")
    # Cooperative supervisor locks; offline confirmation also covers other writers.
    with supervisor.lease(kind="watchdog"),supervisor.lease():
        stage=new_stage(root,".partial-")
        try:
            entries=[];skipped=[]
            for name,source in paths.items():
                if not source.is_file():skipped.append(name);continue
                target=stage/(name+".sqlite3")
                copy_db(source,target,name);entries.append(file_entry(target,name))
            if not entries:raise ValueError("Yedeklenecek Futures kaydı yok.")
            manifest={"version":VERSION,"scope":"futures_only","created_at":clock().isoformat(),
                      "files":entries,"skipped":skipped,"cross_database_atomic":False,
                      "shared_control_history_included":False,"real_orders":False}
            (stage/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
            verify(stage)
            target=publish(stage,"futures-backup-")
            return {"status":"backup_created","directory":str(target),"files":len(entries),"skipped":skipped,"real_orders":False}
        except BaseException:shutil.rmtree(stage,ignore_errors=True);raise
def verify(directory):
    root=Path(directory).expanduser().resolve()
    mp=root/"manifest.json"
    if mp.is_symlink() or not mp.is_file() or not 0<mp.stat().st_size<=MAX_MANIFEST:
        raise ValueError("Geçersiz yedek manifesti.")
    m=json.loads(mp.read_text(encoding="utf-8"))
    if (m.get("version")!=VERSION or m.get("scope")!="futures_only" or m.get("real_orders") is not False
        or not isinstance(m.get("files"),list) or not 1<=len(m["files"])<=len(TABLES)):
        raise ValueError("Yedek kimliği geçersiz.")
    names=set()
    for e in m["files"]:
        name=e["name"]
        if name not in TABLES or name in names or e["file"]!=name+".sqlite3":
            raise ValueError("Yedek dosya listesi geçersiz.")
        names.add(name);p=root/e["file"]
        if digest(p)!=e["sha256"] or p.stat().st_size!=e["bytes"]:raise ValueError("Yedek özeti uyuşmuyor.")
        inspect(p,name)
    if not isinstance(m.get("skipped"),list) or len(m["skipped"])!=len(set(m["skipped"])) or set(m["skipped"])!=set(TABLES)-names:
        raise ValueError("Eksik dosya bildirimi uyuşmuyor.")
    if {p.name for p in root.iterdir()}!={"manifest.json",*(n+".sqlite3" for n in names)}:
        raise ValueError("Beklenmeyen yedek dosyası.")
    return m
def stage_recovery(directory,root,*,clock=stocks.utc):
    permitted()
    m=verify(directory);source=Path(directory).expanduser().resolve()
    stage=new_stage(root,".partial-")
    try:
        copied=[]
        for e in m["files"]:
            name=e["name"];p=stage/e["file"]
            shutil.copyfile(source/e["file"],p)
            if digest(p)!=e["sha256"]:raise ValueError("Yedek kopyası değişti.")
            inspect(p,name)
            if name=="pilot":
                with closing(sqlite3.connect(p)) as db:
                    row=db.execute("SELECT payload FROM observed_accounts WHERE market='FUTURES'").fetchone()
                    if row:
                        s=json.loads(row[0]);pending=s.get("pending")
                        if pending and pending.get("side") in ("LONG","SHORT"):
                            s["pending"]=None
                            db.execute("UPDATE observed_accounts SET payload=? WHERE market='FUTURES'",(json.dumps(s,allow_nan=False),))
                            db.execute("INSERT INTO observed_events(market,at,event,payload) VALUES('FUTURES',?,'entry_cancelled',?)",
                                       (clock().isoformat(),json.dumps({"reason":"recovery_stage","cancelled":pending})))
                    db.execute("INSERT INTO observed_events(market,at,event,payload) VALUES('CONTROL',?,'entry_control',?)",
                               (clock().isoformat(),json.dumps({"halted":True,"reason":"recovery_stage"})))
                    db.commit()
            copied.append(file_entry(p,name))
        recovery={"version":VERSION,"scope":"isolated_recovery_stage","created_at":clock().isoformat(),
                  "files":copied,"source_created_at":m["created_at"],"entry_brake_required":True,
                  "active_paths_changed":False,"automatic_entry_enabled":False,"real_orders":False}
        (stage/"recovery.json").write_text(json.dumps(recovery,indent=2),encoding="utf-8")
        target=publish(stage,"futures-recovery-")
        return {"status":"recovery_staged","directory":str(target),"files":len(copied),
                "active_paths_changed":False,"manual_reconciliation_required":True,"automatic_entry_enabled":False,"real_orders":False}
    except BaseException:shutil.rmtree(stage,ignore_errors=True);raise
def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="mode",required=True)
    b=sub.add_parser("backup");b.add_argument("--root",required=True);b.add_argument("--offline-confirmed",action="store_true")
    v=sub.add_parser("verify");v.add_argument("--directory",required=True)
    r=sub.add_parser("stage");r.add_argument("--directory",required=True);r.add_argument("--root",required=True)
    a=p.parse_args()
    try:
        if a.mode=="backup":d=backup(a.root,offline_confirmed=a.offline_confirmed)
        elif a.mode=="verify":d={"status":"verified","manifest":verify(a.directory),"real_orders":False}
        else:d=stage_recovery(a.directory,a.root)
        print(json.dumps(d,ensure_ascii=True,allow_nan=False));return 0
    except (ValueError,OSError,ArithmeticError,KeyError,TypeError,sqlite3.Error) as e:
        print(json.dumps({"status":"rejected","type":type(e).__name__,"real_orders":False}));return 1
if __name__=="__main__":raise SystemExit(main())
