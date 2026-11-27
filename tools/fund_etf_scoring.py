"""Relative research scores, not probabilities or trading recommendations."""
import math

FIELDS=("last_20_observation_return_pct","observation_volatility_pct","max_drawdown_pct")

def rank_group(entries, min_peers=5):
    if min_peers<5:
        raise ValueError("At least five peers required")
    valid=[]
    for entry in entries:
        m=entry.get("metrics",{})
        if entry.get("research_eligible") is True and all(isinstance(m.get(k),(int,float)) and math.isfinite(m[k]) for k in FIELDS) and m[FIELDS[1]]>=0 and 0<=m[FIELDS[2]]<=100:
            valid.append(entry)
    if len(valid)<min_peers:
        return {"status":"insufficient_peers","scores":[],"real_orders":False}
    groups={(e.get("category") or e.get("sector"),e["metrics"].get("market"),e["metrics"].get("currency"),e["metrics"].get("source"),e["metrics"].get("last_session")) for e in valid}
    if len(groups)!=1 or any(v is None for v in next(iter(groups))):
        raise ValueError("Peers must share category, market, currency, source and last session")
    def percentile(value, values):
        return 100*(sum(x<value for x in values)+0.5*sum(x==value for x in values))/len(values)
    output=[]
    for e in valid:
        m=e["metrics"]
        momentum=percentile(m[FIELDS[0]],[x["metrics"][FIELDS[0]] for x in valid])
        volatility=percentile(m[FIELDS[1]],[x["metrics"][FIELDS[1]] for x in valid])
        drawdown=percentile(m[FIELDS[2]],[x["metrics"][FIELDS[2]] for x in valid])
        risk=(volatility+drawdown)/2
        score=.5*momentum+.5*(100-risk)
        output.append({"symbol":e["symbol"],"performance_score":round(momentum,2),"relative_risk_score":round(risk,2),"research_score":round(score,2),"explanation":{"momentum_percentile":momentum,"volatility_percentile":volatility,"drawdown_percentile":drawdown,"weights":{"momentum":.5,"low_volatility":.25,"low_drawdown":.25}},"real_orders":False})
    return {"status":"research_only","peer_count":len(valid),"scores":sorted(output,key=lambda x:(-x["research_score"],x["symbol"])),"real_orders":False}
