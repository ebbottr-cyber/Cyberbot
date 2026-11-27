"""Read-only, Turkish-panel-compatible Solana research snapshot. No server or trade endpoint."""
import argparse
import json
import sqlite3
from datetime import datetime,timezone
from tools.solana_paper_replay import instant,FALSE_FLAGS
from tools.solana_gemini_review import load,count,number
from tools.solana_model_history import normalize

SCHEMA_VERSION=1
MAX_AGE_SECONDS=3600

def snapshot(report,*,now=None):
    now=datetime.now(timezone.utc) if now is None else now
    if now.tzinfo is None:raise ValueError("Timezone required")
    if report.get("research_only") is not True or any(report.get(k) is not False for k in (*FALSE_FLAGS,"training_allowed","weights_updated","model_promoted","model_saved","gemini_api_called")):
        raise ValueError("Unexpected research authority")
    status=report["status"];stage=report["stage"]
    if (status,stage) not in (("learning_cycle_complete","complete"),("learning_cycle_partial","complete"),("learning_cycle_partial","collection")):
        raise ValueError("Unexpected cycle status")
    finished=instant(report["finished_utc"]) if report.get("finished_utc") else None
    if finished and (finished>now or (report.get("started_utc") and instant(report["started_utc"])>finished)):
        raise ValueError("Invalid report chronology")
    age=int((now-finished).total_seconds()) if finished else None
    out={"schema_version":SCHEMA_VERSION,"market":"solana","mode":"research_only",
         "status":status,"stage":stage,"report_finished_utc":finished.isoformat() if finished else None,
         "report_age_seconds":age,"report_freshness":"unknown" if age is None else "stale" if age>MAX_AGE_SECONDS else "recent_report",
         "market_data_freshness_verified":False,"live_trading_enabled":False,"production_learning_enabled":False,
         "network_requests":False,"research_only":True,"models":[],"dataset":None,"coverage":None,
         "consensus":None,"adaptive":None,"gemini_status":"not_prepared","history_status":None,
         "training_allowed":False,"model_promoted":False,"weights_updated":False,**FALSE_FLAGS}
    if stage=="collection":
        out["status_label_tr"]="Veri toplama tamamlanmadı"
        return out
    e=report["experiment"];body=normalize(e)
    ds=report["dataset"]
    if ds["dataset_sha256"]!=body["dataset_sha256"]:raise ValueError("Dataset mismatch")
    partitions={}
    for name in ("earlier","later"):
        p=ds["partitions"][name]
        partitions[name]={k:count(p[k]) for k in ("examples","unique_mints","positive_labels","nonpositive_labels")}
        if partitions[name]["positive_labels"]+partitions[name]["nonpositive_labels"]!=partitions[name]["examples"]:
            raise ValueError("Invalid partition counts")
    n=count(ds["example_count"])
    if sum(v["examples"] for v in partitions.values())!=n:raise ValueError("Invalid dataset counts")
    out["dataset"]={"sha256":body["dataset_sha256"],"examples":n,"partitions":partitions}
    cov=report["readiness"]["coverage"]["full_history"]
    coverage={k:count(cov[k]) for k in ("observations","eligible_entries","exact_quantity_matches","different_quantity_only","no_later_mint_quote","right_censored_entries","ambiguous_observations")}
    eligible=coverage["eligible_entries"];matched=coverage["exact_quantity_matches"]
    if eligible!=matched+coverage["different_quantity_only"]+coverage["no_later_mint_quote"] or coverage["observations"]!=eligible+coverage["right_censored_entries"]+coverage["ambiguous_observations"]:
        raise ValueError("Invalid coverage counts")
    coverage["exact_match_pct"]=round(100*matched/eligible,4) if eligible else None
    out["coverage"]=coverage
    out["models"]=body["summary"]["models"]
    out["blockers"]=body["summary"]["blockers"]
    out["experiment_status"]=body["summary"]["experiment_status"]
    out["optional_model_status"]=body["optional_model_status"]
    out["consensus"]=body["consensus"]
    a=e.get("adaptive_weights",{})
    if a.get("status")=="adaptive_weights_diagnostic_complete":
        if a.get("trade_eligible") is not False or a.get("weights_updated") is not False:raise ValueError("Unexpected adaptive authority")
        out["adaptive"]={"status":a["status"],"adaptive_brier":number(a["adaptive_brier"],1),
                         "equal_weight_brier":number(a["equal_weight_brier"],1),
                         "adaptive_samples":count(a["adaptive_samples"]),"sample_count":count(a["sample_count"])}
        if out["adaptive"]["adaptive_samples"]>out["adaptive"]["sample_count"]:raise ValueError("Invalid adaptive counts")
    packet=report["manual_review_packet"]
    if packet.get("status")=="manual_review_packet_ready" and packet.get("api_called") is False:
        out["gemini_status"]="manual_packet_ready"
    h=report["history_write"]["status"]
    if h not in ("experiment_archived","duplicate_ignored"):raise ValueError("Unexpected history status")
    out["history_status"]=h
    out["status_label_tr"]="Eğitim engellendi" if e["status"]=="experiment_blocked" else "Deney kısmen tamamlandı" if e["status"]=="experiment_partial" else "Araştırma tamamlandı"
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cycle-report",required=True)
    a=p.parse_args()
    try:
        print(json.dumps(snapshot(load(a.cycle_report)),indent=2,ensure_ascii=False,allow_nan=False))
        return 0
    except (ValueError,TypeError,KeyError,AttributeError,ArithmeticError,OSError,sqlite3.Error) as e:
        print(json.dumps({"schema_version":SCHEMA_VERSION,"market":"solana","status":"rejected","error_type":type(e).__name__,"live_trading_enabled":False,**FALSE_FLAGS}))
        return 1

if __name__=="__main__":raise SystemExit(main())
