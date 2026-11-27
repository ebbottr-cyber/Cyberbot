"""Opt-in bounded foreground Solana research scheduler. Does not install a service."""
import argparse
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta
from pathlib import Path
from tools.dexterm_research_cycle import run as collect_cycle,permissions
from tools.dexterm_research_archive import archive
from tools.solana_exact_exit_quotes import run as exit_cycle
from tools.solana_learning_cycle import run as learning_cycle
from tools.solana_paper_replay import FALSE_FLAGS

class StopRequested(ValueError):
    pass

@contextmanager
def exclusive(lock):
    token=uuid.uuid4().hex
    fd=os.open(lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,"w",encoding="ascii") as f:f.write(token)
        yield
    finally:
        # A stale lock after a crash must be reviewed manually. Never steal it.
        try:
            if lock.read_text(encoding="ascii")==token:lock.unlink()
        except FileNotFoundError:pass

def save(folder,kind,data):
    name=kind+"-"+uuid.uuid4().hex+".json"
    path=folder/name
    with path.open("x",encoding="utf-8") as f:
        json.dump(data,f,indent=2,allow_nan=False)
    return path

def run(root,database,history_database,report_dir,*,enabled=False,cycles=1,interval=300,
        window_hours=24,allow_experiment=False,include_lightgbm=False,include_river=False,
        include_adaptive=False,sleep=time.sleep,clock=lambda:datetime.now(timezone.utc)):
    for v in (enabled,allow_experiment,include_lightgbm,include_river,include_adaptive):
        if type(v) is not bool:raise ValueError("Explicit boolean options required")
    if not enabled:raise ValueError("Explicit scheduler opt-in required")
    for value,low,high in ((cycles,1,12),(interval,180,3600),(window_hours,1,48)):
        if type(value) is not int or not low<=value<=high:raise ValueError("Invalid bounded scheduler configuration")
    source=Path(database).resolve();target=Path(history_database).resolve();folder=Path(report_dir).resolve()
    if source==target or (source.exists() and target.exists() and source.samefile(target)):
        raise ValueError("Separate research and history databases required")
    lock=source.with_name(source.name+".research.lock")
    stop=source.with_name(source.name+".research.stop")
    if target in (lock,stop):raise ValueError("Reserved scheduler path")
    def guard():
        if stop.exists():raise StopRequested("Stop marker present")
        permissions()
    guard()
    source.parent.mkdir(parents=True,exist_ok=True)
    target.parent.mkdir(parents=True,exist_ok=True)
    folder.mkdir(parents=True,exist_ok=True)
    out={"status":"scheduler_partial","requested_cycles":cycles,"completed_cycles":0,
         "interval_seconds":interval,"window_hours":window_hours,"runs":[],
         "research_only":True,"service_installed":False,"production_training_performed":False,
         "weights_updated":False,"model_promoted":False,"training_allowed":False,**FALSE_FLAGS}
    with exclusive(lock):
        try:
            for i in range(cycles):
                if i:
                    remaining=interval
                    while remaining:
                        guard()
                        step=min(remaining,5);sleep(step);remaining-=step
                guard()
                item={"stage":"collection"}
                out["runs"].append(item)
                collected=collect_cycle(root,source,folder,cycles=1)
                item["collection_status"]=collected["status"]
                if collected["status"]!="research_run_complete":
                    out["stop_reason"]="collection_partial";break
                guard()
                item["stage"]="exit_quotes"
                quotes=exit_cycle(source,limit=3,skip_quoted=True)
                item["exit_status"]=quotes["status"]
                item["exit_quote_count"]=len(quotes["quotes"])
                if quotes["quotes"] or quotes["status"]=="exit_quotes_partial":
                    path=save(folder,"solana-exit",quotes)
                    item["exit_archive"]=archive(source,[path])["status"]
                if quotes["status"]=="exit_quotes_partial":
                    out["stop_reason"]="exit_quotes_partial";break
                guard()
                item["stage"]="learning"
                end=clock()
                if end.tzinfo is None:raise ValueError("Timezone required")
                window=((end-timedelta(hours=window_hours)).isoformat(),end.isoformat())
                learned=learning_cycle(source,target,window=window,allow_experiment=allow_experiment,
                                       include_lightgbm=include_lightgbm,include_river=include_river,
                                       include_adaptive=include_adaptive)
                item["report"]=str(save(folder,"solana-learning",learned))
                item["learning_status"]=learned["status"]
                item["experiment_blocked"]=learned["experiment_blocked"]
                if learned["status"]!="learning_cycle_complete":
                    out["stop_reason"]="learning_partial";break
                item["stage"]="complete"
                out["completed_cycles"]+=1
            if out["completed_cycles"]==cycles:out["status"]="scheduler_complete"
        except StopRequested:
            out["status"]="scheduler_stopped";out["stop_reason"]="stop_marker"
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dexterm-root",required=True)
    p.add_argument("--database",required=True)
    p.add_argument("--history-database",required=True)
    p.add_argument("--report-dir",required=True)
    p.add_argument("--enable-research-scheduler",action="store_true")
    p.add_argument("--cycles",type=int,default=1)
    p.add_argument("--interval",type=int,default=300)
    p.add_argument("--window-hours",type=int,default=24)
    p.add_argument("--allow-experiment",action="store_true")
    p.add_argument("--include-lightgbm",action="store_true")
    p.add_argument("--include-river",action="store_true")
    p.add_argument("--include-adaptive",action="store_true")
    a=p.parse_args()
    try:
        d=run(a.dexterm_root,a.database,a.history_database,a.report_dir,enabled=a.enable_research_scheduler,
              cycles=a.cycles,interval=a.interval,window_hours=a.window_hours,allow_experiment=a.allow_experiment,
              include_lightgbm=a.include_lightgbm,include_river=a.include_river,include_adaptive=a.include_adaptive)
        print(json.dumps(d,indent=2,allow_nan=False))
        return 0 if d["status"]=="scheduler_complete" else 2
    except (ValueError,TypeError,KeyError,ArithmeticError,AttributeError,OSError,sqlite3.Error) as e:
        print(json.dumps({"status":"rejected","error_type":type(e).__name__,"training_allowed":False,**FALSE_FLAGS}))
        return 1

if __name__=="__main__":raise SystemExit(main())
