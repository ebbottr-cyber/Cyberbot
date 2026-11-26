"""Explicit one-shot shadow evaluation, never sends an order."""
import argparse,json,sqlite3
from cyberbot.pilot_decisions import record,snapshot,MARKETS
def main():
    p=argparse.ArgumentParser();p.add_argument("--market",choices=MARKETS);a=p.parse_args()
    try:print(json.dumps(record(a.market) if a.market else snapshot(),ensure_ascii=True));return 0
    except (ValueError,OSError,sqlite3.Error,KeyError,TypeError,ArithmeticError) as e:print(json.dumps({"status":"rejected","type":type(e).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
