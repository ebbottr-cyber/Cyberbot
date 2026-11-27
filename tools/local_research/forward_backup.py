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


def backup(root):
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
    reserve=MIN_FREE_DISK_MIB*MIB
    stage=Path(tempfile.mkdtemp(prefix=".partial-",dir=destination))
    try:
        target=stage/NAME
        started=time.monotonic()
        with closing(connect_readonly(source.resolve())) as src:
            src.execute("PRAGMA query_only=ON")
            logical_size=src.execute("PRAGMA page_count").fetchone()[0]*src.execute("PRAGMA page_size").fetchone()[0]
            if logical_size>MAX_BYTES or shutil.disk_usage(destination).free<reserve+logical_size:
                raise RuntimeError("insufficient backup capacity")
            def progress(status,remaining,total):
                if time.monotonic()-started>120 or shutil.disk_usage(destination).free<reserve:
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
        final=destination/("forward-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        if final.exists():
            raise ValueError("backup target already exists")
        stage.rename(final)
        return final
    except BaseException:
        shutil.rmtree(stage,ignore_errors=True)
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path.cwd())
    p.add_argument("--verify",type=Path)
    args=p.parse_args()
    if args.verify:
        print(json.dumps(verify(args.verify),indent=2))
    else:
        print(str(backup(args.root)))


if __name__=="__main__":
    main()
