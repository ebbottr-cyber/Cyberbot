"""Opt-in, local-only Chronos-2 quantile research; no order access."""
import os
from pathlib import Path
from math import isfinite
from statistics import mean
from functools import lru_cache
from .models import fit_predict

CONTEXT=60
MAX_TEST=32

class ChronosError(ValueError):pass

def configured():
    return os.getenv("CYBERBOT_CHRONOS_ENABLED")=="1" and bool(os.getenv("CYBERBOT_CHRONOS_PATH"))

@lru_cache(maxsize=1)
def load_pipeline(path):
    # Offline-only model loading; require an existing operator-provided model directory.
    root=Path(path).expanduser().resolve(strict=True)
    if not root.is_dir() or not (root/"config.json").is_file() or not list(root.glob("*.safetensors")):
        raise ChronosError("Yerel Chronos 2 model dosyaları eksik.")
    os.environ["HF_HUB_OFFLINE"]="1"
    os.environ["TRANSFORMERS_OFFLINE"]="1"
    from chronos import Chronos2Pipeline
    return Chronos2Pipeline.from_pretrained(str(root),device_map="cpu",local_files_only=True,use_safetensors=True,trust_remote_code=False)

def local_predict(contexts):
    if not configured():raise ChronosError("Chronos 2 yapılandırılmadı.")
    try:
        import torch
        pipeline=load_pipeline(os.environ["CYBERBOT_CHRONOS_PATH"])
        inputs=[torch.tensor(c,dtype=torch.float32) for c in contexts]
        with torch.inference_mode():
            quantiles,_=pipeline.predict_quantiles(inputs,prediction_length=1,quantile_levels=[0.1,0.5,0.9],cross_learning=False,batch_size=8)
        return [q[0,0,:].tolist() for q in quantiles]
    except Exception as e:
        raise ChronosError("Yerel Chronos 2 yükleme veya tahmin hatası: "+type(e).__name__) from None

def benchmark(prices,*,mode,predict=local_predict,windows=16):
    if mode not in ("synthetic","historical_unverified") or not 120<=len(prices)<=6000:
        raise ChronosError("120–6000 kapanış gözlemi gerekli.")
    if type(windows) is not int or not 8<=windows<=MAX_TEST:
        raise ChronosError("8–32 test penceresi gerekli.")
    p=[float(v) for v in prices]
    if any(not isfinite(v) or not 1e-12<=v<=1e9 for v in p):
        raise ChronosError("Geçersiz fiyat.")
    returns=[b/a-1 for a,b in zip(p,p[1:])]
    if any(abs(v)>10 for v in returns):raise ChronosError("Aşırı fiyat değişimi.")
    # Each target uses only the preceding returns. Joint cross-series learning is disabled.
    indices=list(range(len(returns)-windows,len(returns)))
    contexts=[returns[i-CONTEXT:i] for i in indices]
    preds=predict(contexts+[returns[-CONTEXT:]])
    if not isinstance(preds,list) or len(preds)!=len(contexts)+1:
        raise ChronosError("Tahmin sayısı uyumsuz.")
    clean=[]
    for row in preds:
        if not isinstance(row,(list,tuple)) or len(row)!=3:
            raise ChronosError("Tahmin biçimi geçersiz.")
        lo,mid,hi=map(float,row)
        if not all(isfinite(v) for v in (lo,mid,hi)) or not lo<=mid<=hi:
            raise ChronosError("Geçersiz tahmin aralığı.")
        clean.append((lo,mid,hi))
    errors={k:[] for k in ("zero","mean","ar1","chronos2")}
    directions={k:[] for k in errors}
    covered=[]; widths=[]
    sign=lambda v:(v>0)-(v<0)
    for i,ctx,(lo,mid,hi) in zip(indices,contexts,clean):
        actual=returns[i]
        guesses={"zero":0.0,"mean":mean(ctx),"ar1":fit_predict(ctx),"chronos2":mid}
        for k,v in guesses.items():
            errors[k].append(abs(actual-v))
            directions[k].append(sign(actual)==sign(v))
        covered.append(lo<=actual<=hi);widths.append(hi-lo)
    lo,mid,hi=clean[-1]
    return {"mode":mode,"test_observations":windows,"context_returns":CONTEXT,
            "models":[{"id":k,"mae_pct":round(mean(errors[k])*100,6),"direction_accuracy_pct":round(mean(directions[k])*100,2)} for k in errors],
            "interval_coverage_pct":round(mean(covered)*100,2),"mean_interval_width_pct":round(mean(widths)*100,6),
            "next_quantiles_pct":{"p10":round(lo*100,6),"p50":round(mid*100,6),"p90":round(hi*100,6)},
            "real_orders":False,"promotion_enabled":False,"profitability_verified":False,
            "limitations":["P10–P90 tahmin aralığı garanti değildir.","Kısa test, model üstünlüğü kanıtı değildir.","Tahmin hatası işlem getirisi değildir."]} 
