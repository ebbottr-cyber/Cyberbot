"""One-shot public quote check; apply is explicitly opt-in."""
import argparse,json,sqlite3
from cyberbot.providers.binance_observed import run
def main():
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group();g.add_argument("--apply",action="store_true");g.add_argument("--context-probe",action="store_true");a=p.parse_args()
    try:print(json.dumps(run(apply=a.apply,context_probe=a.context_probe),ensure_ascii=True));return 0
    except (ValueError,OSError,ArithmeticError,sqlite3.Error,KeyError,TypeError) as e:print(json.dumps({"status":"rejected","type":type(e).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
