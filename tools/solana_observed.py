"""One-shot quote diagnostics. No apply mode, wallet or transaction submission."""
import argparse,json
from cyberbot.providers.solana_observed import run
def main():
    p=argparse.ArgumentParser(description=__doc__);p.parse_args()
    try:print(json.dumps(run(),ensure_ascii=True));return 0
    except (ValueError,KeyError,TypeError,OSError,ArithmeticError) as e:print(json.dumps({"status":"rejected","type":type(e).__name__,"reason":str(e) if type(e).__name__=="PilotError" else "Invalid diagnostic response"}));return 1
if __name__=="__main__":raise SystemExit(main())
