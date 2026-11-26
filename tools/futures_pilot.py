"""Explicit local simulation CLI; never calls the exchange."""
import argparse,json,sqlite3
from pathlib import Path
from cyberbot.futures_pilot import observe,request,snapshot
def main():
    p=argparse.ArgumentParser();p.add_argument("action",choices=["status","observe","long","short","close"]);p.add_argument("--file");a=p.parse_args()
    try:
        if a.action=="status":d=snapshot()
        elif a.action=="observe":
            if not a.file:p.error("observe requires --file")
            with Path(a.file).open("rb") as stream:raw=stream.read(32769)
            if len(raw)>32768:raise ValueError("Quote file too large")
            d=observe(json.loads(raw))
        else:d=request(a.action.upper())
        print(json.dumps(d,ensure_ascii=True));return 0
    except (ValueError,OSError,ArithmeticError,sqlite3.Error) as e:print(json.dumps({"status":"failed","type":type(e).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
