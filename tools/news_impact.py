"""Run an explicit offline event study with an authorized local JSON file."""
import argparse,json
from cyberbot.news_impact import run_local
def main():
    p=argparse.ArgumentParser();p.add_argument("--file",required=True);p.add_argument("--record",required=True);p.add_argument("--market",required=True);p.add_argument("--symbol",required=True);a=p.parse_args()
    try:print(json.dumps(run_local(a.file,a.record,a.market,a.symbol),ensure_ascii=True));return 0
    except (ValueError,OSError,KeyError,TypeError,ArithmeticError) as e:print(json.dumps({"status":"failed","type":type(e).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
