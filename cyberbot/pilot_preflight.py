"""Read-only local launch diagnostics. No permission changes, network or execution."""
import os,sys,sqlite3,shutil
from pathlib import Path
from contextlib import closing
from importlib.metadata import version,PackageNotFoundError
from . import observed_pilot as stocks,pilot_decisions as decisions,pilot_loop as loop
from . import futures_pilot as fut,solana_pilot as sol
from .providers import equity_observed as equity,binance_observed as binance
from .db_paths import checked,pilot_path,same,resolved
from .operations import inspect_db,required
from .pilot_control import snapshot as control_snapshot
from .pilot_ingress import source_for

VERSION="pilot-preflight-1"
MIN_FREE=256*1024*1024
def parent_exists(p):
    p=p.parent
    while not p.exists() and p!=p.parent:p=p.parent
    return p
def snapshot(*,clock=stocks.utc):
    now=clock()
    out={"version":VERSION,"as_of":now.isoformat(),"status":"blocked","python_supported":sys.version_info[:2] in ((3,11),(3,12)),"dependencies":{},"databases":{},"markets":[],"blockers":[],"network_probed":False,"tests_executed":False,"automatic_entry_enabled":False,"live_paper_verified":False,"real_orders":False,"bulk_price_download_enabled":False}
    for name in ("fastapi","uvicorn","httpx"):
        try:out["dependencies"][name]=version(name)
        except PackageNotFoundError:out["dependencies"][name]=None
    if not out["python_supported"] or any(v is None for v in out["dependencies"].values()):out["blockers"].append("python_or_dependencies")
    try:
        paths={**checked(),"observed_pilot":pilot_path()}
        for role,path in paths.items():
            if role=="worker":
                state="not_initialized"
                if path.is_file():
                    with closing(sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=2)) as db:
                        db.execute("PRAGMA query_only=ON")
                        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                        state="ok" if tables and not tables-{"cycles","settings","pilot_cycles","pilot_loop_state"} and db.execute("PRAGMA quick_check(1)").fetchone()==("ok",) else "review_required"
            else:state=inspect_db(path,required(role))
            parent=parent_exists(path)
            space=shutil.disk_usage(parent).free>=MIN_FREE
            writable=parent.is_dir() and os.access(parent,os.W_OK) and (not path.exists() or (path.is_file() and os.access(path,os.W_OK)))
            out["databases"][role]={"status":state,"space_check":space,"write_permission_indicated":writable}
            if state not in ("ok","not_initialized") or not space or not writable:out["blockers"].append("database_"+role)
        out["database_isolation"]="checked"
        out["entry_halted"]=control_snapshot()["halted"]
    except (ValueError,OSError,RuntimeError,sqlite3.Error,KeyError,TypeError,ArithmeticError):
        out["database_isolation"]="review_required";out["blockers"].append("database_isolation_or_integrity")
        return out
    try:selection=loop.selected()
    except stocks.PilotError:selection=[];out["blockers"].append("market_selection_missing")
    out["selected_markets"]=selection
    out["loop_permissions"]=loop.enabled()
    out["supervisor_permission"]=os.getenv("CYBERBOT_PILOT_SUPERVISOR_ENABLED")=="1"
    out["backup_rights_confirmed"]=os.getenv("CYBERBOT_PILOT_BACKUP_RIGHTS_CONFIRMED")=="1"
    if not out["loop_permissions"]:out["blockers"].append("loop_permissions")
    if not out["supervisor_permission"]:out["blockers"].append("supervisor_permission")
    if not out["backup_rights_confirmed"]:out["blockers"].append("backup_rights_not_confirmed")
    for m in loop.MARKETS:
        item={"market":m,"selected":m in selection,"pilot_permissions":decisions.market_enabled(m),"adapter_configured":False,"local_quote_validated":False,"provider_runtime_verified":False,"status":"blocked","blockers":[]}
        b=item["blockers"]
        if not item["selected"]:b.append("not_selected")
        if not item["pilot_permissions"]:b.append("pilot_permissions")
        try:
            if m in equity.VENUES:
                item["adapter_configured"]=equity.configured(m) and os.getenv("CYBERBOT_EQUITY_SESSION_REVIEWED_"+m)=="1"
                if item["selected"] and item["pilot_permissions"] and item["adapter_configured"]:
                    quote=loop.local_input(m,"QUOTE");schedule=loop.local_input(m,"SCHEDULE")
                    envelope=equity.prepare(m,quote,schedule,now)
                    if m=="XETRA" and envelope["quote"]["fx"]["source"]!=os.getenv("CYBERBOT_INGRESS_FX_SOURCE"):raise stocks.PilotError("FX source")
                    item["local_quote_validated"]=True
                if not item["local_quote_validated"]:b.append("local_quote_or_session_not_validated")
            elif m=="FUTURES":
                item["adapter_configured"]=binance.configured() and os.getenv("CYBERBOT_INGRESS_SOURCE_FUTURES")==binance.SOURCE
                fut.symbol()
                b.append("network_and_funding_probe_required")
            else:
                from .providers.solana_observed import configured
                item["adapter_configured"]=configured()
                if item["adapter_configured"]:sol.config()
                b.append("diagnostic_only_no_executable_quote")
        except (ValueError,OSError,KeyError,TypeError,ArithmeticError,sqlite3.Error):
            b.append("configuration_or_quote_review_required")
        if not item["adapter_configured"]:b.append("adapter_not_configured")
        b.extend(["provider_runtime_not_verified","same_engine_forward_test_missing"])
        out["markets"].append(item)
    out["blockers"].extend(["runtime_verification_required","automatic_entry_not_authorized"])
    out["limitations"]=["Yerel dosya ve izin denetimi; ağ sorgusu, yazma testi veya test paketi çalıştırmaz.","Yazma izni ve 256 MiB boş alan ön göstergedir; gerçek disk yazma garantisi değildir.","Kurulum, test ve gözlem çalışması ayrıdır. İzinler kendiliğinden açılmaz."]
    return out
