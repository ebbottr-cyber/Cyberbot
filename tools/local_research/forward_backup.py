"""Explicit local backup of the forward-research journal; never activate a copy."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time

from .vps_guard import MIB, MIN_FREE_DISK_MIB
from cyberbot.db_paths import checked, pilot_path, same

NAME = "forward-models-v2.sqlite3"
COLUMNS = ("market","symbol","source","target_minute","created_at","payload","status","outcome")
MAX_BYTES = 2 * 1024**3
MAX_BACKUPS = 7
MAX_BACKUP_TOTAL = 4 * 1024**3
MANIFEST_ALLOWANCE = 8192


class BackupCapacityDeferred(RuntimeError):
    pass


def unsafe(path):
    return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & 1024)


def inventory(destination, lock):
    copies = []
    total = 0
    for entry in destination.iterdir():
        if entry == lock:
            continue
        if unsafe(entry) or not entry.is_dir() or not entry.name.startswith('forward-'):
            raise ValueError('unexpected backup directory entry; manual review required')
        files = list(entry.iterdir())
        if {p.name for p in files} != {NAME, 'manifest.json'}:
            raise ValueError('unexpected backup contents; manual review required')
        for file in files:
            if unsafe(file) or not file.is_file() or file.stat().st_nlink != 1:
                raise ValueError('unsafe backup contents')
            size = file.stat().st_size
            if not 0 < size <= (MAX_BYTES if file.name == NAME else MANIFEST_ALLOWANCE):
                raise ValueError('invalid backup size')
            total += size
        copies.append(entry)
    return copies, total


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()


def connect_readonly(path):
    return sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=5)


def inspect(db):
    db.execute("PRAGMA query_only=ON")
    columns=tuple(r[1] for r in db.execute("PRAGMA table_info(forecasts)"))
    if columns != COLUMNS:
        raise ValueError("unexpected research schema")
    if db.execute("PRAGMA quick_check(1)").fetchone()!=("ok",):
        raise ValueError("research database integrity check failed")
    return db.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0]


def verify(folder):
    folder=Path(folder)
    if folder.is_symlink() or set(p.name for p in folder.iterdir())!={NAME,"manifest.json"}:
        raise ValueError("unexpected backup contents")
    source, manifest=folder/NAME,folder/"manifest.json"
    if any(p.is_symlink() or not p.is_file() or p.stat().st_nlink!=1 for p in (source,manifest)):
        raise ValueError("unsafe backup files")
    if manifest.stat().st_size>8192 or not 0<source.stat().st_size<=MAX_BYTES:
        raise ValueError("backup size outside limits")
    data=json.loads(manifest.read_text(encoding="utf-8"))
    if (data.get("scope")!="forward_research_only" or data.get("name")!=NAME
            or data.get("bytes")!=source.stat().st_size or data.get("sha256")!=digest(source)):
        raise ValueError("backup manifest mismatch")
    # A finalized SQLite backup is standalone; immutable prevents sidecar creation.
    with closing(sqlite3.connect(source.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)) as db:
        count=inspect(db)
    if count!=data.get("rows"):
        raise ValueError("backup row count mismatch")
    return data


def backup(root, *, skip_identical=False):
    if os.getenv("CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED")!="1":
        raise RuntimeError("local research rights confirmation required")
    root=Path(root).resolve(strict=True)
    var=root/"var"
    folder=var/"ai"
    source=folder/NAME
    destination=var/"ai-backups"
    if any(p.is_symlink() for p in (var,folder,source,destination)):
        raise ValueError("unsafe research path")
    if not source.is_file() or source.stat().st_nlink!=1:
        raise ValueError("local forward database required")
    if any(same(source.resolve(),p) for p in (*checked().values(),pilot_path())):
        raise ValueError("active database collision")
    if source.stat().st_size>MAX_BYTES:
        raise ValueError("manual backup review required")
    destination.mkdir(mode=0o700,exist_ok=True)
    if not destination.is_dir():
        raise ValueError("backup directory required")
    if unsafe(destination):
        raise ValueError("unsafe backup directory")
    lock=destination/".backup-lock"
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise BackupCapacityDeferred("backup lock exists; review if stale") from exc
    stage=None
    try:
        copies,total_bytes=inventory(destination,lock)
        if len(copies)>=MAX_BACKUPS or total_bytes>=MAX_BACKUP_TOTAL:
            raise BackupCapacityDeferred("backup capacity reached; review existing copies")
        reserve=MIN_FREE_DISK_MIB*MIB
        started=time.monotonic()
        with closing(connect_readonly(source.resolve())) as src:
            src.execute("PRAGMA query_only=ON")
            logical_size=src.execute("PRAGMA page_count").fetchone()[0]*src.execute("PRAGMA page_size").fetchone()[0]
            if logical_size>MAX_BYTES or shutil.disk_usage(destination).free<reserve+logical_size+MANIFEST_ALLOWANCE:
                raise RuntimeError("insufficient backup capacity")
            if total_bytes+logical_size+MANIFEST_ALLOWANCE>MAX_BACKUP_TOTAL:
                raise BackupCapacityDeferred("backup byte budget reached")
            stage=Path(tempfile.mkdtemp(prefix=".partial-",dir=destination))
            target=stage/NAME
            page_size=src.execute("PRAGMA page_size").fetchone()[0]
            def progress(status,remaining,total):
                if (time.monotonic()-started>120 or shutil.disk_usage(destination).free<reserve
                        or total*page_size>MAX_BYTES
                        or total_bytes+total*page_size+MANIFEST_ALLOWANCE>MAX_BACKUP_TOTAL):
                    raise RuntimeError("backup resource limit reached")
            with closing(sqlite3.connect(target)) as dst:
                src.backup(dst,pages=128,progress=progress,sleep=.05)
                dst.execute("PRAGMA journal_mode=DELETE")
                dst.commit()
                count=inspect(dst)
        data={"scope":"forward_research_only","name":NAME,"bytes":target.stat().st_size,
              "sha256":digest(target),"rows":count,"created_at":datetime.now(timezone.utc).isoformat(),
              "automatic_deletion":False,"activated":False,"real_orders":False}
        (stage/"manifest.json").write_text(json.dumps(data,indent=2,allow_nan=False),encoding="utf-8")
        verify(stage)
        if skip_identical and copies:
            latest=max(copies,key=lambda p:p.name)
            if (latest/NAME).stat().st_size==data["bytes"] and verify(latest)["sha256"]==data["sha256"]:
                return None
        if total_bytes+data["bytes"]+(stage/"manifest.json").stat().st_size>MAX_BACKUP_TOTAL:
            raise BackupCapacityDeferred("backup byte budget reached")
        final=destination/("forward-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        if final.exists():
            raise ValueError("backup target already exists")
        stage.rename(final)
        stage=None
        return final
    finally:
        try:
            if stage is not None:
                shutil.rmtree(stage,ignore_errors=True)
        finally:
            lock.rmdir()


def recover(root, folder):
    """Verify and copy a trusted local backup into an inactive staging area."""
    if os.getenv("CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED")!="1":
        raise RuntimeError("local research rights confirmation required")
    root=Path(root).resolve(strict=True)
    var=root/"var"
    backups=var/"ai-backups"
    destination=var/"ai-recovered"
    folder=Path(folder).expanduser()
    if any(p.is_symlink() for p in (var,backups,destination,folder)):
        raise ValueError("unsafe recovery path")
    folder=folder.resolve(strict=True)
    if folder.parent!=backups.resolve(strict=True) or not folder.name.startswith("forward-"):
        raise ValueError("expected finalized local backup")
    data=verify(folder)
    source=folder/NAME
    if any(same(source,p) for p in (*checked().values(),pilot_path(),var/"ai"/NAME)):
        raise ValueError("active database collision")
    destination.mkdir(mode=0o700,exist_ok=True)
    if shutil.disk_usage(destination).free<MIN_FREE_DISK_MIB*MIB+data["bytes"]:
        raise RuntimeError("insufficient recovery capacity")
    stage=Path(tempfile.mkdtemp(prefix=".partial-",dir=destination))
    try:
        for name in (NAME,"manifest.json"):
            shutil.copyfile(folder/name,stage/name)
        copied=verify(stage)
        if copied!=data or verify(folder)!=data:
            raise ValueError("backup changed during recovery")
        (stage/"recovery.json").write_text(json.dumps({
            "status":"verified_inactive_copy","sha256":data["sha256"],
            "rows":data["rows"],"activated":False,"real_orders":False,
            "active_database_modified":False,
            "created_at":datetime.now(timezone.utc).isoformat()
        },indent=2),encoding="utf-8")
        final=destination/("recovered-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        if final.exists():
            raise ValueError("recovery target already exists")
        stage.rename(final)
        return final
    except BaseException:
        shutil.rmtree(stage,ignore_errors=True)
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path.cwd())
    action=p.add_mutually_exclusive_group()
    action.add_argument("--verify",type=Path)
    action.add_argument("--recover",type=Path)
    action.add_argument("--scheduled",action="store_true")
    args=p.parse_args()
    if args.verify:
        print(json.dumps(verify(args.verify),indent=2))
    elif args.recover:
        print(str(recover(args.root,args.recover)))
    else:
        try:
            result=backup(args.root,skip_identical=args.scheduled)
        except BackupCapacityDeferred as exc:
            print("WAIT_BACKUP_CAPACITY:",str(exc))
            raise SystemExit(75)
        print("UNCHANGED_SNAPSHOT" if result is None else str(result))


if __name__=="__main__":
    main()
