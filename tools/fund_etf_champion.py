"""Compare aligned out-of-sample predictions; never promote automatically."""
import math

def compare(reports, *, min_samples=100, min_brier_gain=0.01):
    if min_samples<100 or not 0<min_brier_gain<1:
        raise ValueError("Invalid evaluation policy")
    if len(reports)<2:
        return {"status":"insufficient_models","model_promoted":False}
    results=[]
    reference=None
    for name,report in reports.items():
        if report.get("status")!="offline_research":
            return {"status":"incomplete_evaluation","model_promoted":False}
        rows=report.get("predictions",[])
        keys=[(r["date"],r["actual"],r["baseline"]) for r in rows]
        if len(keys)<min_samples or len({k[0] for k in keys})!=len(keys) or keys!=sorted(keys):
            return {"status":"insufficient_or_invalid_samples","model_promoted":False}
        identity=(report.get("horizon_observations"),keys)
        if reference is None:
            reference=identity
        elif identity!=reference:
            return {"status":"unaligned_evaluation","model_promoted":False}
        if any(r["actual"] not in (0,1) or r["baseline"] not in (0,1) or not math.isfinite(r["probability"]) or not 0<=r["probability"]<=1 for r in rows):
            raise ValueError("Invalid predictions")
        n=len(rows)
        brier=sum((r["probability"]-r["actual"])**2 for r in rows)/n
        baseline=sum((r["baseline"]-r["actual"])**2 for r in rows)/n
        accuracy=sum((r["probability"]>=.5)==bool(r["actual"]) for r in rows)/n
        baseline_accuracy=1-baseline
        results.append({"model":name,"brier":brier,"accuracy":accuracy,"baseline_accuracy":baseline_accuracy,"eligible":baseline-brier>=min_brier_gain and accuracy>baseline_accuracy})
    results.sort(key=lambda r:(r["brier"],-r["accuracy"],r["model"]))
    candidate=next((r["model"] for r in results if r["eligible"]),None)
    return {"status":"review_required" if candidate else "no_eligible_model","candidate":candidate,"results":results,"model_promoted":False,"real_orders":False}
