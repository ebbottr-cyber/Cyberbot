"""Read-only preflight. Blocked is a report, not a start instruction."""
import json,sqlite3
from cyberbot.pilot_preflight import snapshot
def main():
    try:print(json.dumps(snapshot(),ensure_ascii=True,indent=2));return 0
    except (ValueError,OSError,KeyError,TypeError,ArithmeticError,sqlite3.Error) as e:print(json.dumps({"status":"blocked","error_type":type(e).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
