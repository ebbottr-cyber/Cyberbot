"""Opt-in local fund/ETF research worker. No order execution or paid fallback."""
import argparse
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from tools.fund_etf_cycle import cycle, publish
from tools.fund_etf_backup import daily_backup


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def exclusive(path):
    """OS-backed advisory lock; automatically released when process exits."""
    with open(path,"a+b") as f:
        f.seek(0,os.SEEK_END)
        if f.tell()==0:
            f.write(b"0"); f.flush()
        f.seek(0)
        if os.name=="nt":
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            try:
                yield
            finally:
                f.seek(0); msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            try:
                yield
            finally:
                fcntl.flock(f.fileno(),fcntl.LOCK_UN)


def run_once(database, config_path, output, status_path, *, yahoo_enabled=False):
    started=now()
    publish(dict(status="running",started_at=started,real_orders=False,
                 execution_allowed=False),status_path)
    try:
        with open(config_path,encoding="utf-8-sig") as f:
            config=json.load(f)
        result=cycle(database,config,yahoo_enabled=yahoo_enabled)
        policy=config.get("backup",{})
        backup_status={"status":"disabled"}
        if policy.get("enabled") is True:
            try:
                backup_status=daily_backup(database,policy.get("destination","var/fund-etf-backups"))
            except Exception as exc:
                backup_status={"status":"failed","error_type":type(exc).__name__}
                result.setdefault("errors",[]).append("backup_failed")
                if result["status"]=="research_only":
                    result["status"]="partial"
        # Keep local backup paths out of the public snapshot.
        result["backup"]={k:v for k,v in backup_status.items() if k!="bundle"}
        publish(result,output)
        status=dict(status=result["status"],counts=result.get("counts",{}),
                    errors=result.get("errors",[]),backup=backup_status)
    except Exception as exc:
        status=dict(status="failed",error_type=type(exc).__name__)
        # Replace obsolete signals with an explicit failure snapshot, never
        # silently leave a previous successful scan looking current.
        try:
            publish(dict(schema_version=1,generated_at=now(),status="blocked",
                         mode="research_only",markets=[],groups=[],instruments=[],
                         portfolios=[],errors=["worker_cycle_failed"],
                         real_orders=False,execution_allowed=False,
                         live_data_verified=False),output)
        except (OSError,ValueError):
            status["snapshot_publish_failed"]=True
    status.update(started_at=started,finished_at=now(),real_orders=False,
                  execution_allowed=False)
    publish(status,status_path)
    return status


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database",default="var/fund-etf.sqlite3")
    p.add_argument("--config",default="var/fund-etf-config.json")
    p.add_argument("--output",default="var/fund-etf-snapshot.json")
    p.add_argument("--status-file",default="var/fund-etf-worker.json")
    p.add_argument("--loop",action="store_true")
    p.add_argument("--interval",type=int,default=3600)
    p.add_argument("--enable-yahoo",action="store_true")
    p.add_argument("--status",action="store_true")
    a=p.parse_args()
    if not 900<=a.interval<=86400:
        p.error("interval must be 900–86400 seconds")
    paths=[Path(v).resolve() for v in (a.database,a.config,a.output,a.status_file)]
    if len(set(paths))!=4:
        p.error("input and output paths must be distinct")
    db,config,output,status=paths
    lock=output.parent/(output.name+".lock")
    if lock in paths:
        p.error("lock path collision")
    if a.status:
        try:
            with status.open(encoding="utf-8") as f:
                info=json.load(f)
            info["running_verified"]=False
        except (OSError,ValueError):
            info={"status":"unavailable","running_verified":False}
        print(json.dumps(info,ensure_ascii=True))
        return 0
    for path in (output,status):
        path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with exclusive(lock):
            try:
                while True:
                    result=run_once(db,config,output,status,yahoo_enabled=a.enable_yahoo)
                    print(json.dumps(result,ensure_ascii=True),flush=True)
                    if not a.loop:
                        return 0 if result["status"]=="research_only" else 2
                    time.sleep(a.interval)
            except KeyboardInterrupt:
                publish(dict(status="stopped",finished_at=now(),real_orders=False,
                             execution_allowed=False),status)
                return 0
    except OSError:
        print(json.dumps({"status":"lock_or_io_error","real_orders":False}))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
