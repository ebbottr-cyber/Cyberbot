"""Fund/ETF SQLite backup, verification and non-destructive recovery.

Only the three dedicated databases are included; no secrets, config or live
orders. Stop all writers for a cross-database consistent manual backup.
"""
import argparse
import hashlib
import json
import shutil
import sqlite3
import tempfile
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

VERSION=1
FILES={"prices":"fund-etf.sqlite3","paper":"fund-etf.sqlite3.auto-paper.sqlite3",
       "development":"fund-etf.sqlite3.development.sqlite3"}
TABLES={"prices":{"fund_prices","tefas_catalog","etf_catalog","fund_macro","fund_news"},
        "paper":{"fund_auto_accounts","fund_auto_orders","fund_auto_prices","fund_auto_journal"},
        "development":{"fund_development"}}


def sources(database):
    p=Path(database).resolve()
    return {"prices":p,"paper":p.with_name(p.name+".auto-paper.sqlite3"),
            "development":p.with_name(p.name+".development.sqlite3")}


def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def integrity(path,role):
    if not path.is_file() or path.is_symlink():
        raise ValueError("missing_or_unsafe_database")
    with closing(sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True,timeout=5)) as db:
        if db.execute("PRAGMA integrity_check").fetchall()!=[("ok",)]:
            raise ValueError("database_integrity_failed")
        tables={x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not tables.intersection(TABLES[role]) or (role=="paper" and not TABLES[role]<=tables):
            raise ValueError("unexpected_database_schema")
    return True


def verify(bundle):
    root=Path(bundle)
    manifest=root/"manifest.json"
    if not manifest.is_file() or manifest.is_symlink() or manifest.stat().st_size>100_000:
        raise ValueError("invalid_manifest")
    with manifest.open(encoding="utf-8") as f:
        m=json.load(f)
    if m.get("version")!=VERSION or m.get("real_orders") is not False or m.get("execution_allowed") is not False:
        raise ValueError("invalid_manifest")
    entries=m["files"]
    if not isinstance(entries,dict) or "prices" not in entries or not set(entries)<=set(FILES):
        raise ValueError("invalid_backup_roles")
    if sorted(m.get("missing_optional",[]))!=sorted(set(FILES)-set(entries)):
        raise ValueError("invalid_missing_roles")
    for role,entry in entries.items():
        if entry["name"]!=FILES[role]:
            raise ValueError("invalid_backup_filename")
        p=root/FILES[role]
        if not p.is_file() or p.is_symlink() or p.stat().st_size!=entry["bytes"] or digest(p)!=entry["sha256"]:
            raise ValueError("backup_checksum_failed")
        integrity(p,role)
    return m


def backup(database, destination):
    origin=sources(database)
    if not origin["prices"].is_file():
        raise ValueError("price_archive_missing")
    root=Path(destination).resolve()
    root.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc)
    target=root/(stamp.strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:12])
    temp=Path(tempfile.mkdtemp(prefix=".fund-backup-",dir=root))
    try:
        entries={}
        for role,src in origin.items():
            if not src.exists() and role!="prices":
                continue
            if not src.is_file() or src.is_symlink():
                raise ValueError("invalid_source_database")
            dst=temp/FILES[role]
            with closing(sqlite3.connect(src.as_uri()+"?mode=ro",uri=True,timeout=5)) as source, closing(sqlite3.connect(dst)) as out:
                source.backup(out,pages=256,sleep=.05)
                out.commit()
            integrity(dst,role)
            entries[role]=dict(name=dst.name,bytes=dst.stat().st_size,sha256=digest(dst))
        m=dict(version=VERSION,created_at=stamp.isoformat(),files=entries,
               missing_optional=sorted(set(FILES)-set(entries)),real_orders=False,
               execution_allowed=False,cross_database_atomic=False)
        (temp/"manifest.json").write_text(json.dumps(m,indent=2),encoding="utf-8")
        verify(temp)
        temp.rename(target)
        return dict(status="verified",bundle=str(target),created_at=m["created_at"],
                    roles=sorted(entries),missing_optional=m["missing_optional"],
                    cross_database_atomic=False,real_orders=False)
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def daily_backup(database,destination):
    """Reuse today's verified bundle, but never silently ignore corruption."""
    root=Path(destination).resolve()
    prefix=datetime.now(timezone.utc).strftime("%Y%m%dT")
    candidates=sorted((p for p in root.glob(prefix+"*") if p.is_dir()),reverse=True)
    # An older bundle without newly created optional ledgers is not sufficient.
    expected={role for role,p in sources(database).items() if p.is_file()}
    if candidates:
        m=verify(candidates[0])
        if set(m["files"])==expected:
            return dict(status="verified_existing",bundle=str(candidates[0]),
                        roles=sorted(expected),created_at=m["created_at"],real_orders=False)
    return backup(database,root)


def restore(bundle,destination):
    """Recover into a new directory only. Original files are never replaced."""
    m=verify(bundle)
    root=Path(destination).resolve()
    if root.exists():
        raise FileExistsError("restore_destination_exists")
    root.mkdir(parents=False,exist_ok=False)
    try:
        for role,entry in m["files"].items():
            dst=root/FILES[role]
            shutil.copyfile(Path(bundle)/FILES[role],dst)
            if digest(dst)!=entry["sha256"]:
                raise ValueError("restore_checksum_failed")
            integrity(dst,role)
        # Completion marker is written last. It is not a worker config.
        (root/"manifest.json").write_text(json.dumps(m,indent=2),encoding="utf-8")
        verify(root)
    except Exception:
        shutil.rmtree(root)
        raise
    return dict(status="recovered",directory=str(root),roles=sorted(m["files"]),
                real_orders=False,automatic_activation=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="command",required=True)
    b=sub.add_parser("backup")
    b.add_argument("--database",default="var/fund-etf.sqlite3")
    b.add_argument("--destination",default="var/fund-etf-backups")
    v=sub.add_parser("verify");v.add_argument("--bundle",required=True)
    r=sub.add_parser("restore");r.add_argument("--bundle",required=True);r.add_argument("--destination",required=True)
    a=p.parse_args()
    if a.command=="backup":
        result=backup(a.database,a.destination)
    elif a.command=="verify":
        result=dict(status="verified",manifest=verify(a.bundle))
    else:
        result=restore(a.bundle,a.destination)
    print(json.dumps(result,ensure_ascii=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
