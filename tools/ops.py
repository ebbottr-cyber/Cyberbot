"""Local commands: python -m tools.ops health | backup."""
import argparse
import json
from cyberbot.operations import health,backup
from cyberbot.recovery import recover

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=["health","backup","recover"])
    parser.add_argument("--output",default="var/backups")
    parser.add_argument("--source")
    args=parser.parse_args()
    if args.action=="health":
        report=health()
        print(json.dumps(report,ensure_ascii=True,indent=2))
        return 0 if report["status"]=="ok" else 1
    try:
        if args.action=="recover":
            if not args.source:parser.error("recover requires --source")
            print(str(recover(args.source,args.output)))
        else:print(str(backup(args.output)))
        return 0
    except (ValueError,OSError) as e:
        print("Operation failed:",type(e).__name__)
        return 1

if __name__=="__main__":raise SystemExit(main())
