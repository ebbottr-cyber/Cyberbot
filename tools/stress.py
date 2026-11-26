import argparse
import json
from cyberbot.stress import suite
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--steps",type=int,default=240)
    a=p.parse_args()
    results=suite(a.steps)
    print(json.dumps([{k:v for k,v in r.items() if k!="curve"} for r in results],ensure_ascii=True))
    return 0 if all(r["passed"] for r in results) else 1
if __name__=="__main__":raise SystemExit(main())
