"""Opt-in local bounded foreground loop. Does not install or start background tasks."""
import argparse,json,time,sqlite3
from cyberbot.pilot_loop import run_cycle,snapshot,MIN_INTERVAL
def main():
    p=argparse.ArgumentParser();p.add_argument("--status",action="store_true");p.add_argument("--cycles",type=int,default=1);p.add_argument("--interval",type=int,default=20);a=p.parse_args()
    if not 1<=a.cycles<=240 or not MIN_INTERVAL<=a.interval<=300:p.error("cycles 1–240; interval 15–300 seconds")
    try:
        if a.status:print(json.dumps(snapshot(),ensure_ascii=True));return 0
        for i in range(a.cycles):
            report=run_cycle();print(json.dumps(report,ensure_ascii=True),flush=True)
            if report["status"]=="clock_regressed":return 1
            if i+1<a.cycles:time.sleep(a.interval)
        return 0 if report["status"]=="ok" else 1
    except KeyboardInterrupt:return 130
    except (ValueError,OSError,sqlite3.Error,KeyError,TypeError,ArithmeticError) as exc:print(json.dumps({"status":"rejected","type":type(exc).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
