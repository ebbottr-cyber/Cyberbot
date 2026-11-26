"""One-shot public quote check; apply is explicitly opt-in."""
import argparse,json,sqlite3
from cyberbot.providers.binance_observed import run
def main():
    p=argparse.ArgumentParser();p.add_argument("--apply",action="store_true");a=p.parse_args()
    try:print(json.dumps(run(apply=a.apply),ensure_ascii=True));return 0
    except (ValueError,OSError,ArithmeticError,sqlite3.Error,KeyError,TypeError) as e:print(json.dumps({"status":"rejected","type":type(e).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
