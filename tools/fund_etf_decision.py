"""Rule-based research gate, not a trained AI model or execution engine."""
import math

def decide(metrics, ranking, *, held=False, max_age_days=7, max_drawdown_pct=20, buy_threshold=75, sell_threshold=25):
    if not 0<=sell_threshold<buy_threshold<=100 or not 0<=max_drawdown_pct<=100 or max_age_days<0:
        raise ValueError("Invalid policy")
    def result(action, reason):
        return {"action":action,"reason_tr":reason,"research_only":True,"ai_prediction":False,"real_orders":False,"execution_allowed":False}
    if metrics.get("status")!="research_only":
        return result("WAIT","Yetersiz veri")
    try:
        age,dd,momentum,score,risk=[float(x) for x in (metrics["age_days"],metrics["max_drawdown_pct"],metrics["last_20_observation_return_pct"],ranking["research_score"],ranking["relative_risk_score"])]
    except (KeyError,TypeError,ValueError):
        return result("WAIT","Eksik analiz veya puan")
    if not all(math.isfinite(x) for x in (age,dd,momentum,score,risk)) or not 0<=age<=max_age_days or not 0<=dd<=100 or not 0<=score<=100 or not 0<=risk<=100:
        return result("WAIT","Eski veya geçersiz veri")
    if dd>max_drawdown_pct:
        return result("SELL_REVIEW" if held else "WAIT","Tarihsel maksimum düşüş risk sınırını aşıyor")
    if held and (score<=sell_threshold or momentum<0):
        return result("SELL_REVIEW","Göreceli performans veya momentum zayıf")
    if not held and score>=buy_threshold and momentum>0 and risk<=50:
        return result("BUY_REVIEW","Pozitif momentum ve göreceli risk/performans koşulları sağlandı")
    return result("HOLD" if held else "WAIT","Yeni işlem incelemesi için koşullar sağlanmadı")
