"""Explicitly started local research worker; Ctrl+C stops loop."""
import argparse
import json
import time
from cyberbot.worker import run_cycle

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--loop",action="store_true")
    p.add_argument("--interval",type=int,default=900,help="Seconds between completed cycles")
    p.add_argument("--market",choices=["BIST","NASDAQ","XETRA"])
    p.add_argument("--symbol")
    p.add_argument("--daily-backup",action="store_true")
    a=p.parse_args()
    if not 900<=a.interval<=86400:p.error("Interval must be 900–86400 seconds.")
    if bool(a.market)!=bool(a.symbol):p.error("Supply market and symbol together.")
    try:
        while True:
            result=run_cycle(market=a.market,symbol=a.symbol,backup_daily=a.daily_backup)
            print(json.dumps(result,ensure_ascii=True),flush=True)
            if not a.loop:return 0 if result["status"]=="ok" else 1
            time.sleep(a.interval)
    except KeyboardInterrupt:return 0

if __name__=="__main__":raise SystemExit(main())
