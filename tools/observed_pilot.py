"""Explicit local commands only; no providers, network requests or automatic entry."""
import argparse,json
from pathlib import Path
from cyberbot.observed_pilot import observe,request,snapshot
def main():
    p=argparse.ArgumentParser();p.add_argument("action",choices=["status","observe","buy","sell"]);p.add_argument("--market",choices=["BIST","NASDAQ"]);p.add_argument("--file");a=p.parse_args()
    try:
        if a.action=="status":d=snapshot()
        elif a.action=="observe":
            if not a.file or not a.market:p.error("observe requires --market and --file")
            with Path(a.file).open("rb") as f:raw=f.read(8193)
            if len(raw)>8192:raise ValueError("Quote file too large")
            d=observe(a.market,json.loads(raw))
        else:
            if not a.market:p.error("market required")
            d=request(a.market,a.action)
        print(json.dumps(d,ensure_ascii=True));return 0
    except (ValueError,OSError,ArithmeticError) as e:print(json.dumps({"status":"failed","type":type(e).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
