"""Opt-in Gemini research review of numeric Futures model metrics only.

No raw observations, account state, tools, orders or model promotion.
The two model evaluation protocols differ; no head-to-head winner is inferred.
"""
import argparse,json,os,re
from pathlib import Path
import httpx
from . import futures_lightgbm as batch,futures_river as online

VERSION="futures-gemini-1"
HOST="https://generativelanguage.googleapis.com/v1beta/models/"
MAX_BYTES=131072
CATEGORIES=("evaluation_protocol","baseline_comparison","drift_diagnostics","data_provenance")
REVIEW_CODES=("common_test_window","more_observations","check_baselines","inspect_drift","verify_data_provenance")
SCHEMA={"type":"object","properties":{"review_codes":{"type":"array","items":{"type":"string","enum":list(REVIEW_CODES)}}},
        "required":["review_codes"]}
TR={"common_test_window":"Her iki modeli aynı ileri test zaman aralığında değerlendirin.",
    "more_observations":"Daha geniş ve farklı piyasa rejimlerini içeren gözlemlerle araştırmayı tekrarlayın.",
    "check_baselines":"Model hata ölçümlerini kendi basit referanslarıyla karşılaştırın.",
    "inspect_drift":"River hata değişimi alarmlarını ve gözlem zamanlarını inceleyin.",
    "verify_data_provenance":"Özelliklerin kayıt anında gerçekten mevcut olduğunu doğrulayın."}
def integer(value,lo,hi):
    if type(value) is not int or not lo<=value<=hi:raise batch.ResearchError("Rapor sayı alanı geçersiz.")
    return value

def compact(report,model):
    version,status,metric,nkey=(batch.VERSION,"offline_research_only","lightgbm","test_examples") if model=="lightgbm" else (online.VERSION,"offline_prequential_research","river","scored_predictions")
    if (not isinstance(report,dict) or report.get("version")!=version or report.get("status")!=status
        or report.get("symbol") not in ("BTCUSDT","ETHUSDT") or report.get("actual_action")!="HOLD"
        or report.get("data_mode")!="local_observations_unverified" or report.get("horizon_minutes")!=5
        or any(report.get(k) is not False for k in ("paper_orders","real_orders","promotion_enabled","profitability_verified"))):
        raise batch.ResearchError("Model araştırma raporu kimliği geçersiz.")
    n=integer(report[nkey],50,6000)
    observations=integer(report["observations"],240,6000)
    if n>observations:raise batch.ResearchError("Model örnek sayısı tutarsız.")
    metrics={}
    for k in (metric,"zero","trailing_momentum"):
        m=report["metrics"][k]
        metrics[k]={"mae_pct":batch.numeric(m["mae_pct"],0,200),
                    "direction_accuracy_pct":batch.numeric(m["direction_accuracy_pct"],0,100)}
    result={"protocol":"fixed_purged_holdout" if model=="lightgbm" else "delayed_label_prequential",
            "scored_examples":n,"observations":observations,"metrics":metrics,
            "runtime_reported":report.get("runtime_verified") is True}
    if model=="river":
        events=report.get("drift_events")
        if not isinstance(events,list) or len(events)>n:raise batch.ResearchError("Drift sayısı tutarsız.")
        result["drift_event_count"]=len(events)
    return result

def evidence(lightgbm,river):
    a=compact(lightgbm,"lightgbm");b=compact(river,"river")
    if lightgbm["symbol"]!=river["symbol"]:raise batch.ResearchError("Model sembolleri uyuşmuyor.")
    return {"symbol":lightgbm["symbol"],"horizon_minutes":5,"lightgbm":a,"river":b,
            "same_test_window_verified":False,"feature_provenance_verified":False,
            "profitability_verified":False}

def payload(data):
    return {"systemInstruction":{"parts":[{"text":"Futures araştırma denetçisi. Yalnız verilen sayısal metrikleri incele. Protokoller farklıdır; kazanan, al/sat veya kârlılık çıkarma. Yalnız şemadaki uygun araştırma kontrol kodlarını seç. Emir yetkin yok."}]},
            "contents":[{"role":"user","parts":[{"text":json.dumps(data,allow_nan=False,separators=(",",":"))}]}],
            "generationConfig":{"temperature":0,"maxOutputTokens":512,"responseMimeType":"application/json","responseJsonSchema":SCHEMA}}

def parse(raw):
    try:
        rows=raw["candidates"]
        if not isinstance(rows,list) or len(rows)!=1 or rows[0].get("finishReason")!="STOP":raise ValueError()
        parts=rows[0]["content"]["parts"]
        if not isinstance(parts,list) or not 1<=len(parts)<=8:raise ValueError()
        text=[]
        for part in parts:
            if not isinstance(part,dict):raise ValueError()
            if part.get("thought") is True:continue
            if set(part)-{"text","thought","thoughtSignature"} or not isinstance(part.get("text"),str):raise ValueError()
            text.append(part["text"])
        value=json.loads("".join(text))
        if not isinstance(value,dict) or set(value)!={"review_codes"}:raise ValueError()
        codes=value["review_codes"]
        if not isinstance(codes,list) or not 1<=len(codes)<=len(REVIEW_CODES) or any(not isinstance(c,str) or c not in REVIEW_CODES for c in codes) or len(set(codes))!=len(codes):raise ValueError()
        return codes
    except (ValueError,TypeError,KeyError,IndexError,AttributeError):
        raise batch.ResearchError("Gemini araştırma yanıtı geçersiz veya eksik.") from None

def request(model,key,body,*,transport=None):
    if not isinstance(model,str) or not re.fullmatch(r"gemini-[a-z0-9.-]{1,60}",model):
        raise batch.ResearchError("Açık Gemini model adı gerekli.")
    if not isinstance(key,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}",key):
        raise batch.ResearchError("Gemini API anahtarı gerekli.")
    url=HOST+model+":generateContent"
    try:
        with httpx.Client(timeout=httpx.Timeout(20,connect=5),follow_redirects=False,trust_env=False,transport=transport) as client:
            with client.stream("POST",url,headers={"x-goog-api-key":key},json=body) as response:
                response.raise_for_status();raw=bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw)>MAX_BYTES:raise batch.ResearchError("Gemini yanıtı çok büyük.")
            return parse(json.loads(raw))
    except (httpx.HTTPError,ValueError,OSError):
        raise batch.ResearchError("Gemini isteği reddedildi veya yanıt geçersiz; otomatik tekrar yok.") from None

def run(lightgbm,river,*,transport=None):
    if os.getenv("CYBERBOT_FUTURES_GEMINI_ENABLED")!="1" or os.getenv("CYBERBOT_GEMINI_METRICS_SHARING_CONFIRMED")!="1":
        raise batch.ResearchError("Gemini araştırma ve dış veri paylaşım izinleri kapalı.")
    data=evidence(lightgbm,river)
    model=os.getenv("CYBERBOT_GEMINI_MODEL","")
    key=os.getenv("CYBERBOT_GEMINI_API_KEY","")
    codes=request(model,key,payload(data),transport=transport)
    # Never render arbitrary provider text. Local Turkish templates only.
    required=["common_test_window","verify_data_provenance"]
    selected=list(dict.fromkeys(required+codes))
    return {"version":VERSION,"status":"research_review_only","symbol":data["symbol"],"model":model,
            "review_codes":selected,"review_tr":[TR[c] for c in selected],"metrics":data,
            "provider_output_verified":False,"transport_mocked":transport is not None,
            "requests_per_run":1,"max_output_tokens":512,"automatic_retry":False,
            "model_ranking":None,"promotion_enabled":False,"actual_action":"HOLD",
            "paper_orders":False,"real_orders":False,"profitability_verified":False}

def read_report(path):
    with Path(path).expanduser().open("rb") as f:raw=f.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise batch.ResearchError("Rapor dosyası çok büyük.")
    return json.loads(raw)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lightgbm-report",required=True);p.add_argument("--river-report",required=True)
    a=p.parse_args()
    try:
        print(json.dumps(run(read_report(a.lightgbm_report),read_report(a.river_report)),ensure_ascii=False,allow_nan=False));return 0
    except (ValueError,OSError,ArithmeticError,KeyError,TypeError) as exc:
        print(json.dumps({"status":"rejected","type":type(exc).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
