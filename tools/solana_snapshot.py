"""Tek seferlik herkese açık Solana gözlemi; emir ve cüzdan anahtarı yok."""
from pathlib import Path
from dataclasses import asdict
import json,time
from cyberbot.providers.solana_meme import SolanaMemeFeed

def run(out):
    out=Path(out)
    out.mkdir(parents=True,exist_ok=True)
    feed=SolanaMemeFeed()
    rows=[]
    errors={}
    stamp=int(time.time()*1000)
    for name,fetch in (("geckoterminal",lambda:feed.new_pools(stamp)),("dexscreener",lambda:feed.latest_profiles(stamp,limit=8))):
        try: rows.extend(asdict(q) for q in fetch())
        except Exception as e: errors[name]=type(e).__name__
    result={"observed_at_ms":stamp,"observations":len(rows),"unique_mints":len({r["mint"] for r in rows}),"errors":errors,"quotes":rows,
            "historical":False,"full_coverage_verified":False,"security_verified":False,"real_orders":False}
    (out/"solana.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="quotes"}))
    return result
if __name__=="__main__":
    run("var/inventory")
