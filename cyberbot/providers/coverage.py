"""Salt okunur, operatörün yerel kapsam raporundan sayısal özet."""
import json
from pathlib import Path

def coverage(path):
    missing={"status":"unavailable","by_market":{},"license_verified":False}
    if not path:return missing
    try:
        with Path(path).open("rb") as f: raw=f.read(2000001)
        if len(raw)>2000000:return missing
        doc=json.loads(raw)
        markets={}
        keys=("candidates","with_any_bars","rows_in_range")
        for m in ("tr","us","de"):
            v=doc["by_market"][m]
            if any(type(v[k]) is not int or v[k]<0 for k in keys):return missing
            if v["with_any_bars"]>v["candidates"] or v["rows_in_range"]<v["with_any_bars"]:return missing
            markets[m]={k:v[k] for k in keys}
        return {"status":"report_only","by_market":markets,"license_verified":False,
                "pilot":doc.get("pilot") is True,"shards":doc.get("shards",1) if type(doc.get("shards",1)) is int else 1}
    except (OSError,ValueError,TypeError,KeyError):return missing
