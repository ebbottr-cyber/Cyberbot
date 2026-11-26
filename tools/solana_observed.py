"""One-shot quote diagnostics. No apply mode, wallet or transaction submission."""
import json
from cyberbot.providers.solana_observed import run
def main():
    try:print(json.dumps(run(),ensure_ascii=True));return 0
    except (ValueError,KeyError,TypeError,OSError,ArithmeticError) as e:print(json.dumps({"status":"rejected","type":type(e).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
