"""One-shot local licensed quote bridge or IEX diagnostic."""
import argparse,json,sqlite3
from cyberbot.providers.equity_observed import run_local,iex_probe,VENUES
def main():
    p=argparse.ArgumentParser();p.add_argument("--market",choices=VENUES);p.add_argument("--quote");p.add_argument("--schedule");p.add_argument("--apply",action="store_true");p.add_argument("--iex-probe",action="store_true");a=p.parse_args()
    try:
        if a.iex_probe:
            if a.apply or a.market or a.quote or a.schedule:p.error("IEX diagnostic cannot apply")
            d=iex_probe()
        else:
            if not a.market or not a.quote or not a.schedule:p.error("market, quote and schedule required")
            d=run_local(a.market,a.quote,a.schedule,apply=a.apply)
        print(json.dumps(d,ensure_ascii=True));return 0
    except (ValueError,OSError,KeyError,TypeError,ArithmeticError,sqlite3.Error) as e:print(json.dumps({"status":"rejected","type":type(e).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
