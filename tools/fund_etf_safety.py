"""Fund-only path ownership and cooperative writer locks."""
import os
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

PRICE_TABLES={"fund_prices","tefas_catalog","etf_catalog","fund_macro","fund_news",
              "fund_paper_accounts","fund_paper_positions","fund_paper_trades"}
PAPER_TABLES={"fund_auto_accounts","fund_auto_orders","fund_auto_prices","fund_auto_journal"}
DEV_TABLES={"fund_development"}


def same(a,b):
    return a==b or (a.exists() and b.exists() and a.samefile(b))


def protected():
    from cyberbot import db_paths as p
    paths=list(p.layout().values())
    for name in ("pilot_path","futures_ai_memory_path","futures_training_path",
                 "futures_forward_path","futures_diagnostics_path"):
        paths.append(getattr(p,name)())
    paths.extend(Path(v).expanduser().resolve() for k,v in os.environ.items()
                 if k.startswith("CYBERBOT_") and k.endswith("_DB") and v
                 and not k.startswith("CYBERBOT_FUND_ETF_"))
    paths.extend(Path(v).resolve() for v in ("var/fx-provider.json","var/fx-provider-quota.sqlite3"))
    if os.getenv("CYBERBOT_FX_FILE"):
        paths.append(Path(os.environ["CYBERBOT_FX_FILE"]).resolve())
    return paths


def check_database(path,allowed):
    if not path.exists():
        return
    if not path.is_file():
        raise ValueError("invalid_database_path")
    with closing(sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
        tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if not tables<=allowed:
            raise ValueError("foreign_database_schema")


def archive_paths(database):
    db=Path(database).expanduser().resolve()
    paths=[db,db.with_name(db.name+".auto-paper.sqlite3").resolve(),
           db.with_name(db.name+".development.sqlite3").resolve()]
    for i,p in enumerate(paths):
        if any(same(p,q) for q in paths[:i]+protected()):
            raise ValueError("fund_database_path_collision")
        check_database(p,(PRICE_TABLES,PAPER_TABLES,DEV_TABLES)[i])
    return paths


def check_paths(database,config,output,status=None):
    db,ledger,dev=archive_paths(database)
    cfg=Path(config).resolve()
    out=Path(output).resolve()
    files=[cfg,out]+([Path(status).resolve()] if status is not None else [])
    reserved=[db,ledger,dev]+protected()
    for i,p in enumerate(files):
        if any(same(p,q) for q in reserved+files[:i]):
            raise ValueError("fund_file_path_collision")
    for p in files[1:]:
        if p.suffix.lower()!=".json":
            raise ValueError("json_output_required")
        if p.exists():
            if not p.is_file():
                raise ValueError("invalid_output_path")
            with p.open("rb") as f:
                if f.read(16)==b"SQLite format 3\x00":
                    raise ValueError("sqlite_output_collision")
    locks=[db.with_name(db.name+".worker.lock").resolve(),out.with_name(out.name+".lock").resolve()]
    if any(same(lock,p) for lock in locks for p in reserved+files) or same(*locks):
        raise ValueError("fund_lock_path_collision")
    return locks


@contextmanager
def exclusive(path):
    with open(path,"a+b") as f:
        f.seek(0,os.SEEK_END)
        if f.tell()==0:
            f.write(b"0");f.flush()
        f.seek(0)
        if os.name=="nt":
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            try:
                yield
            finally:
                f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            try:
                yield
            finally:
                fcntl.flock(f.fileno(),fcntl.LOCK_UN)
