"""Explicitly consume one local observation envelope; no polling or download."""
import argparse,json,sqlite3
from cyberbot.pilot_ingress import read_file
def main():
    p=argparse.ArgumentParser();p.add_argument("--file",required=True);a=p.parse_args()
    try:print(json.dumps(read_file(a.file),ensure_ascii=True));return 0
    except (ValueError,OSError,ArithmeticError,sqlite3.Error) as e:print(json.dumps({"status":"rejected","type":type(e).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
