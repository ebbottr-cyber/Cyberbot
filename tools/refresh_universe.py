"""EBBot'un üç piyasa listeleyicisi; her kaynak bağımsız hata raporlar."""
from pathlib import Path
import json
from datetime import datetime,timezone
from vendor.ebbot import four_market_universe_builder as b

def run(out):
    out=Path(out)
    out.mkdir(parents=True,exist_ok=True)
    payloads={}
    errors={}
    for name,fetch in (("nasdaq",b.download_official_nasdaq),("bist",b.download_official_bist),("xetra",b.download_official_xetra)):
        try:
            payloads[name+"_payload"]=fetch()
        except Exception as e:
            errors[name]=type(e).__name__
    # A malformed response from one exchange must not discard the other two.
    parsers={"nasdaq":b.parse_nasdaq_directory,"bist":b.parse_kap_bist_page,"xetra":b.parse_xetra_equities}
    for name,parse in parsers.items():
        key=name+"_payload"
        if key in payloads:
            try:
                values,_=parse(payloads[key])
                if not values: raise ValueError("empty")
            except Exception as e:
                errors[name]=type(e).__name__
                del payloads[key]
    stocks,report=b.build_universe(Path("vendor/ebbot/seed.csv"),**payloads)
    report.update({"source_errors":errors,"listing_sources_refreshed":sorted(k.removesuffix("_payload") for k in payloads),
                   "as_of_utc":datetime.now(timezone.utc).isoformat(),"price_rows_downloaded":0,
                   "full_coverage_verified":False})
    b.write_universe(out/"universe.csv",stocks)
    (out/"inventory.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
    return report

if __name__=="__main__":
    run("var/inventory")
