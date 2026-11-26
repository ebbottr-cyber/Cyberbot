"""Read-only automatic-entry audit."""
import json,sqlite3
from cyberbot.pilot_authorization import snapshot
def main():
    try:print(json.dumps(snapshot(),ensure_ascii=True,indent=2));return 0
    except (ValueError,OSError,sqlite3.Error,KeyError,TypeError,ArithmeticError) as e:print(json.dumps({"authorization":"blocked","type":type(e).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
