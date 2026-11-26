"""Optional local official-news loop; explicit operator configuration required."""
import argparse,json,time
from cyberbot.news_feed import enabled_keys,refresh,FeedError,INTERVAL
def main():
    p=argparse.ArgumentParser();p.add_argument("--loop",action="store_true");a=p.parse_args()
    if not enabled_keys():print("Haber akışı kapalı veya izin listesi boş.");return 1
    try:
        while True:
            failed=False
            for key in enabled_keys():
                try:print(json.dumps(refresh(key),ensure_ascii=True),flush=True)
                except Exception as e:
                    failed=True
                    print(json.dumps({"source":key,"status":"failed","reason":str(e) if isinstance(e,FeedError) else type(e).__name__},ensure_ascii=True),flush=True)
            if not a.loop:return int(failed)
            time.sleep(INTERVAL)
    except KeyboardInterrupt:return 0
if __name__=="__main__":raise SystemExit(main())
