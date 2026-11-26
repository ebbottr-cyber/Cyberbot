"""Offline next-observation return forecasts. No trade or model promotion."""
from statistics import mean
from math import isfinite

WINDOW=60
MIN_HISTORY=120

def fit_predict(history):
    """Ridge-regularized AR(1) on trailing returns only."""
    sample=history[-WINDOW:]
    x,y=sample[:-1],sample[1:]
    mx,my=mean(x),mean(y)
    slope=sum((a-mx)*(b-my) for a,b in zip(x,y))/(sum((a-mx)**2 for a in x)+0.001)
    return max(-0.5,min(0.5,my+slope*(sample[-1]-mx)))

def evaluate(prices,*,mode):
    if mode not in ("synthetic","historical_unverified") or not MIN_HISTORY<=len(prices)<=6000:
        raise ValueError("120–6000 kapanış gözlemi gerekli.")
    p=[float(x) for x in prices]
    if any(not isfinite(x) or not 1e-12<=x<=1e9 for x in p):
        raise ValueError("Geçersiz fiyat.")
    returns=[b/a-1 for a,b in zip(p,p[1:])]
    if any(abs(x)>10 for x in returns):
        raise ValueError("Aşırı fiyat değişimi; veri kalitesi incelemesi gerekli.")
    errors={k:[] for k in ("zero","mean","ar1")}
    directions={k:[] for k in errors}
    sign=lambda x:(x>0)-(x<0)
    for i in range(WINDOW,len(returns)):
        past=returns[:i]
        actual=returns[i]
        guesses={"zero":0.0,"mean":mean(past[-WINDOW:]),"ar1":fit_predict(past)}
        for k,v in guesses.items():
            errors[k].append(abs(actual-v))
            directions[k].append(sign(actual)==sign(v))
    n=len(returns)-WINDOW
    return {"mode":mode,"observations":len(p),"test_observations":n,
            "models":[{"id":k,"mae_pct":round(mean(errors[k])*100,6),"direction_accuracy_pct":round(mean(directions[k])*100,2)} for k in errors],
            "next_observation_estimates_pct":{"zero":0,"mean":round(mean(returns[-WINDOW:])*100,6),"ar1":round(fit_predict(returns)*100,6)},
            "trained_model":"rolling_ar1","chronos_connected":False,"promotion_enabled":False,"real_orders":False,
            "limitations":["Her tahmin yalnız önceki 60 getiriyle hesaplanır.","Hata ölçümü işlem getirisi değildir; işlem maliyetleri dahil değildir.","Sentetik veya doğrulanmamış arşiv; tahminler yatırım sinyali değildir."]}

class LocalModelError(ValueError):pass

def summarize(report,model,*,transport=None):
    """Only fixed localhost Ollama endpoint, no tools, no arbitrary URLs."""
    import json,re,httpx
    if not isinstance(model,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,99}",model):
        raise LocalModelError("Yerel model adı geçersiz.")
    prompt=("Aşağıdaki hesaplanmış sentetik araştırma raporunu Türkçe, kısa ve ihtiyatlı özetle. "
            "Veri yoksa belirt. Yeni sayı, haber, fiyat veya kaynak uydurma. Al/sat önerisi verme. "
            "Bu içerik yatırım tavsiyesi değil, sadece araştırma özeti. JSON: "+json.dumps(report,ensure_ascii=False))
    payload={"model":model,"prompt":prompt,"stream":False,"options":{"temperature":0,"num_predict":384}}
    try:
        if transport is not None:
            data=transport(payload)
        else:
            with httpx.Client(timeout=httpx.Timeout(60,connect=3),follow_redirects=False,trust_env=False) as client:
                with client.stream("POST","http://127.0.0.1:11434/api/generate",json=payload) as response:
                    response.raise_for_status()
                    raw=bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw)>128000:raise LocalModelError("Model yanıtı çok büyük.")
                    data=json.loads(raw)
        text=data.get("response") if isinstance(data,dict) else None
        if not isinstance(text,str) or not text.strip() or len(text)>12000:
            raise LocalModelError("Model yanıtı geçersiz.")
        return {"text":text,"model":model,"verified":False,"mode":"synthetic","real_orders":False,"promotion_enabled":False}
    except (httpx.HTTPError,ValueError,TypeError) as e:
        raise LocalModelError("Yerel model yanıt vermedi veya yanıt geçersiz.") from None
