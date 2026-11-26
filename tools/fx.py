"""Explicit local currency quote updater; Ctrl+C stops optional loop."""
import argparse,json,time
from cyberbot.fx_provider import refresh,FXError,INTERVAL

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--loop",action="store_true")
    args=p.parse_args()
    try:
        while True:
            try:
                report=refresh()
            except (FXError,OSError) as e:
                report={"status":"unavailable","reason":str(e) if isinstance(e,FXError) else "Yerel kur dosyası hatası."}
            except Exception:
                report={"status":"unavailable","reason":"Kur güncellemesi başarısız."}
            print(json.dumps(report,ensure_ascii=True),flush=True)
            if not args.loop:return 0 if report["status"]=="updated" else 1
            time.sleep(INTERVAL)
    except KeyboardInterrupt:return 0

if __name__=="__main__":raise SystemExit(main())
