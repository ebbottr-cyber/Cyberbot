"""Optional Gemini commentary. Never changes decisions or submits orders."""
import json
import math
import os
import re

def explain(decision, metrics, *, enabled=False, free_tier_confirmed=False, model=None):
    action=decision.get("action")
    if action not in ("BUY_REVIEW","SELL_REVIEW","HOLD","WAIT"):
        raise ValueError("Invalid research decision")
    reason=str(decision.get("reason_tr",""))[:500]
    fallback={"action":action,"reason_tr":reason,"commentary":reason,"provider":"local_rules","real_orders":False}
    if enabled is not True or free_tier_confirmed is not True:
        return fallback
    key=os.environ.get("GEMINI_API_KEY")
    if not key or not model or not re.fullmatch(r"gemini-[a-zA-Z0-9.-]+",model):
        return fallback
    safe={}
    for field in ("age_days","last_20_observation_return_pct","observation_volatility_pct","max_drawdown_pct"):
        value=metrics.get(field)
        if type(value) in (int,float) and math.isfinite(value):
            safe[field]=value
    payload=json.dumps({"action":action,"metrics":safe},ensure_ascii=False)
    try:
        from google import genai
        from google.genai import types
        with genai.Client(api_key=key,http_options=types.HttpOptions(timeout=15000)) as client:
            response=client.models.generate_content(model=model,contents="Verilen araştırma kararını yalnızca sağlanan sayısal verilerle Türkçe açıkla. Kararı değiştirme, emir veya yatırım tavsiyesi verme, yeni veri uydurma. En fazla üç cümle. Veri: "+payload,config=types.GenerateContentConfig(max_output_tokens=300,temperature=0.2))
            commentary=(response.text or "").strip()
        if not commentary:
            return fallback
        return {**fallback,"commentary":commentary[:1500],"provider":"gemini","commentary_verified":False}
    except Exception:
        return fallback
