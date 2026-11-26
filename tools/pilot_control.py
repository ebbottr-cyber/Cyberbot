"""Local entry brake and forward diagnostic commands. No execution permission."""
import argparse,json,sqlite3
from cyberbot.pilot_control import change,snapshot
from cyberbot.pilot_outcomes import record,snapshot as outcomes
def main():
    p=argparse.ArgumentParser();p.add_argument("action",choices=["status","halt","resume","outcomes","measure"]);p.add_argument("--market",choices=["BIST","NASDAQ","XETRA","SOLANA","FUTURES"]);a=p.parse_args()
    try:
        if a.action=="measure":
            if not a.market:p.error("market required")
            d=record(a.market)
        elif a.action=="outcomes":d=outcomes()
        elif a.action=="status":d=snapshot()
        else:d=change(a.action=="halt")
        print(json.dumps(d,ensure_ascii=True));return 0
    except (ValueError,OSError,sqlite3.Error,KeyError,TypeError,ArithmeticError) as e:print(json.dumps({"status":"rejected","type":type(e).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
