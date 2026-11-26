"""Local operator launch. Never creates a task, enables rights or submits an order."""
import argparse,json,sqlite3
from cyberbot.pilot_supervisor import supervise,child
def main():
    p=argparse.ArgumentParser();p.add_argument("--child",action="store_true");p.add_argument("--continuous",action="store_true");p.add_argument("--cycles",type=int,default=1);a=p.parse_args()
    try:
        if a.child:
            if a.continuous or a.cycles!=1:p.error("invalid child options")
            return child()
        return supervise(cycles=None if a.continuous else a.cycles,emit=lambda d:print(json.dumps(d,ensure_ascii=True),flush=True))
    except KeyboardInterrupt:return 130
    except (ValueError,OSError,sqlite3.Error,KeyError,TypeError,ArithmeticError) as e:
        print(json.dumps({"status":"rejected","type":type(e).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
