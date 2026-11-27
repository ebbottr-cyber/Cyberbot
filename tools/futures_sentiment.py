"""One-shot Futures sentiment report; no execution options."""
import argparse,json
from cyberbot.providers.futures_sentiment import run
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--include-top",action="store_true",help="Opt in to Top Trader data endpoints")
    a=p.parse_args()
    try:print(json.dumps(run(include_top=a.include_top),ensure_ascii=True));return 0
    except (ValueError,OSError,ArithmeticError,KeyError,TypeError) as e:
        print(json.dumps({"status":"rejected","type":type(e).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
