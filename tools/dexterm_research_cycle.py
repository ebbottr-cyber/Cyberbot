"""Bounded foreground DexTerm research cycle, isolated from all trading engines."""
import argparse,json,os,sqlite3,time,uuid
from pathlib import Path
from datetime import datetime,timezone
from tools.dexterm_readonly_probe import probe,ProbeFailure
from tools.dexterm_candidate_review import review
from tools.dexterm_pool_bridge import run as bridge,FLAGS
from tools.dexterm_research_archive import archive,APP_ID
from tools.solana_public_scan import REFERENCE_MINTS

def permissions():
    if os.getenv("CYBERBOT_PILOT_KILL_SWITCH")!="1" or os.getenv("CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED")!="1":
        raise ValueError("Research permissions required")

def priority(database,mints):
    path=Path(database).resolve()
    if not path.exists():return list(mints)
    con=sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=10)
    try:
        if con.execute("PRAGMA application_id").fetchone()[0]!=APP_ID or con.execute("PRAGMA user_version").fetchone()[0]!=1:
            raise ValueError("Unexpected research archive")
        counts={(m,k):n for m,k,n in con.execute(
            "SELECT mint,kind,COUNT(*) FROM research_observations WHERE kind IN ('pool_lookup','snapshot') GROUP BY mint,kind")}
        return sorted(mints,key=lambda m:(counts.get((m,"pool_lookup"),0),counts.get((m,"snapshot"),0)))
    finally:
        con.close()

def cycle(root,database,report_dir,*,probe_fn=probe,review_fn=review,bridge_fn=bridge,archive_fn=archive):
    permissions()
    folder=Path(report_dir)
    folder.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")+"-"+uuid.uuid4().hex[:12]
    paths=[]
    def save(kind,data):
        path=folder/("dexterm-cycle-"+stamp+"-"+kind+".json")
        with path.open("x",encoding="utf-8") as f:
            json.dump(data,f,indent=2,allow_nan=False)
        paths.append(str(path))
        return archive_fn(database,[path])
    # Check existing archive before requesting data.
    priority(database,[])
    raw=probe_fn(root,True)
    state=save("scan",raw)
    result={"status":"cycle_partial","stage":"screener","reports":paths,
            "candidate_count":raw["candidate_count"],"archive":state,**FLAGS}
    if raw["status"]!="diagnostic_complete":return result
    reviewed=review_fn(raw)
    result["archive"]=save("review",reviewed)
    result["shortlist_count"]=reviewed["shortlist_count"]
    ordered=priority(database,[m for m in reviewed["shortlist_mints"] if m not in REFERENCE_MINTS.values()])
    permissions()
    data=bridge_fn(raw,lookup_limit=3,priority_mints=ordered)
    result["archive"]=save("bridge",data)
    result.update(stage="bridge",bridge_status=data["status"],matched_pool_count=data["matched_pool_count"],
                  completed_mints=(data.get("scan") or {}).get("completed_mints",0),
                  stop_reason=(data.get("scan") or {}).get("stop_reason"))
    if data["status"]=="diagnostic_complete":result["status"]="cycle_complete"
    elif data["status"] in ("no_eligible_pools","no_nonreference_candidates"):result["status"]="cycle_no_candidates"
    return result

def run(root,database,report_dir,*,cycles=1,interval=180,cycle_fn=cycle,sleep=time.sleep):
    if type(cycles) is not int or not 1<=cycles<=3 or type(interval) is not int or not 180<=interval<=3600:
        raise ValueError("Invalid bounded cycle configuration")
    runs=[]
    for i in range(cycles):
        permissions()
        if i:sleep(interval)
        permissions()
        result=cycle_fn(root,database,report_dir)
        runs.append(result)
        if result["status"]=="cycle_partial":break
    return {"status":"research_run_complete" if len(runs)==cycles and all(r["status"]!="cycle_partial" for r in runs) else "research_run_partial",
            "requested_cycles":cycles,"completed_cycles":len(runs),"runs":runs,**FLAGS}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dexterm-root",required=True)
    p.add_argument("--database",required=True)
    p.add_argument("--report-dir",required=True)
    p.add_argument("--cycles",type=int,default=1)
    p.add_argument("--interval",type=int,default=180)
    a=p.parse_args()
    try:
        d=run(a.dexterm_root,a.database,a.report_dir,cycles=a.cycles,interval=a.interval)
        print(json.dumps(d,indent=2,allow_nan=False))
        return 0 if d["status"]=="research_run_complete" else 1
    except (ValueError,TypeError,KeyError,AttributeError,OSError,ArithmeticError,sqlite3.Error) as e:
        print(json.dumps({"status":"rejected","error_type":type(e).__name__,
                          "reason":e.reason if isinstance(e,ProbeFailure) else None,**FLAGS}))
        return 1
if __name__=="__main__":raise SystemExit(main())
