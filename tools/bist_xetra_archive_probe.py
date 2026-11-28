"""Research-only coverage probe. Never enable trading or download unlicensed BIST data."""
import csv, hashlib, io, json, sqlite3, sys, tempfile, urllib.parse, urllib.request, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

OUT=Path("probe"); OUT.mkdir(exist_ok=True)
def save(name,obj):
    (OUT/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False))
def get(url,limit):
    with urllib.request.urlopen(url,timeout=45) as response:
        data=response.read(limit+1)
        if len(data)>limit: raise ValueError("size limit")
        return data
with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(sys.argv[1]) as z:
    p=z.extract("Cyberbot_3_Piyasa_Gunluk.sqlite3",tmp)
    with sqlite3.connect(p) as db:
        symbols={s for s, in db.execute("SELECT code FROM attempts")}
tr=sorted(s for s in symbols if s.endswith(".IS"))
de=sorted(s for s in symbols if s.endswith(".DE"))
assert len(tr)==803 and len(de)==1749,(len(tr),len(de))
save("inventory.json",{"BIST":tr,"Xetra":de,"source":"archive/daily-equities-20261126","counts":{"BIST":len(tr),"Xetra":len(de)},"membership_verified":False})
# Publicly advertised BIST archive metadata only; missing explicit data license.
try:
    url="https://huggingface.co/api/datasets/umarigan/stock_intraday_data"
    meta=json.loads(get(url,2000000))
    save("bist-source.json",{"source":url,"revision":meta.get("sha"),"card":meta.get("cardData"),"files":[x.get("rfilename") for x in meta.get("siblings",[])],"status":"rights_review_required","price_downloaded":False})
except Exception as e:
    save("bist-source.json",{"status":"metadata_access_failed","error":str(e),"price_downloaded":False})
# AWS registry expressly licenses this deprecated source for noncommercial use.
base="https://deutsche-boerse-xetra-pds.s3.eu-central-1.amazonaws.com/"
report={"source":base,"license":"noncommercial research only","price_downloaded":False,"full_archive":False,"identity_verified":False}
try:
    root=ET.fromstring(get(base+"?"+urllib.parse.urlencode({"list-type":"2","prefix":"2021-09-14/","max-keys":"100"}),1000000))
    ns={"s":"http://s3.amazonaws.com/doc/2006-03-01/"}
    objects=[(x.findtext("s:Key",namespaces=ns),int(x.findtext("s:Size",namespaces=ns))) for x in root.findall("s:Contents",ns)]
    report["listed_objects"]=len(objects)
    options=[(k,n) for k,n in objects if k.endswith(".csv") and 1000<n<20000000]
    if not options:
        report["status"]="no_nonempty_csv_in_sample_date"
    else:
        key,size=options[0]
        raw=get(base+urllib.parse.quote(key,safe="/"),20000000)
        rows=list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        required={"ISIN","Mnemonic","SecurityType","Currency","Date","Time","StartPrice","MaxPrice","MinPrice","EndPrice","TradedVolume"}
        if not rows or not required.issubset(rows[0]): raise ValueError("empty or unexpected CSV schema")
        matches=[r for r in rows if r["Mnemonic"]+".DE" in de]
        report.update(status="sample_downloaded",price_downloaded=True,key=key,sha256=hashlib.sha256(raw).hexdigest(),rows=len(rows),candidate_rows=len(matches),candidate_symbols=sorted({r["Mnemonic"]+".DE" for r in matches}),security_types=sorted({r["SecurityType"] for r in matches}))
        # Raw research sample, not canonical equity bars. No ticker identity inference.
        (OUT/"xetra-source-sample.csv").write_bytes(raw)
except Exception as e:
    report.update(status="access_or_validation_failed",error=str(e))
save("xetra-source.json",report)
print(json.dumps(report,ensure_ascii=False))
if not report["price_downloaded"]: sys.exit(2)
