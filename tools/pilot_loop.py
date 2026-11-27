"""Opt-in local bounded foreground loop. Does not install or start background tasks."""
import argparse,json,time,sqlite3,math
from cyberbot.pilot_loop import run_cycle,snapshot,MIN_INTERVAL,selected

def aligned_delay(now, earliest=None):
    """Align UTC starts to :10/:30/:50 without catching up missed slots."""
    target=max(now, earliest if earliest is not None else now)
    slot=10+20*math.ceil((target-10)/20)
    return max(0,slot-now)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--status",action="store_true")
    p.add_argument("--cycles",type=int,default=1)
    p.add_argument("--interval",type=int,default=20)
    p.add_argument("--align-minute",action="store_true",help="Futures-only UTC :10/:30/:50 observation slots (20-second cadence)")
    a=p.parse_args()
    if not 1<=a.cycles<=240 or not MIN_INTERVAL<=a.interval<=300:p.error("cycles 1–240; interval 15–300 seconds")
    try:
        if a.status:print(json.dumps(snapshot(),ensure_ascii=True));return 0
        if a.align_minute:
            if a.interval!=20 or selected()!=["FUTURES"]:p.error("--align-minute requires FUTURES only and --interval 20")
            time.sleep(aligned_delay(time.time()))
        for i in range(a.cycles):
            report=run_cycle();print(json.dumps(report,ensure_ascii=True),flush=True)
            if report["status"]=="clock_regressed":return 1
            if i+1<a.cycles:
                if a.align_minute:
                    # The engine enforces its cooldown from the previous finish, not start.
                    # Skip any slot that would violate it; do not burst or relax the guard.
                    now=time.time()
                    time.sleep(aligned_delay(now,now+MIN_INTERVAL+.25))
                else:
                    time.sleep(a.interval)
        return 0 if report["status"]=="ok" else 1
    except KeyboardInterrupt:return 130
    except (ValueError,OSError,sqlite3.Error,KeyError,TypeError,ArithmeticError) as exc:print(json.dumps({"status":"rejected","type":type(exc).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
