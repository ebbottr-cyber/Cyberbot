"""Explicit local Solana simulation CLI; no wallet or network."""
import argparse,json
from pathlib import Path
from cyberbot.solana_pilot import observe,request,snapshot
def main():
    p=argparse.ArgumentParser();p.add_argument("action",choices=["status","observe","buy","sell"]);p.add_argument("--file");a=p.parse_args()
    try:
        if a.action=="status":d=snapshot()
        elif a.action=="observe":
            if not a.file:p.error("observe requires --file")
            with Path(a.file).open("rb") as f:raw=f.read(8193)
            if len(raw)>8192:raise ValueError("Quote file too large")
            d=observe(json.loads(raw))
        else:d=request(a.action)
        print(json.dumps(d,ensure_ascii=True));return 0
    except (ValueError,OSError,ArithmeticError) as e:print(json.dumps({"status":"failed","type":type(e).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
