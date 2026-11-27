"""Validate archived exact-quantity DexTerm exits without requesting any quotes."""
import re
from cyberbot.solana_pilot import address
from tools.dexterm_route_accounting import USDC
from tools.dexterm_paper_replay import instant,leg_amounts,FALSE_FLAGS
SOURCE="dexterm_exact_quantity_exit_quote"
MIN_AGE=180
MAX_AGE=3600
MAX_QUOTES=3

def validate_report(report):
    if report.get("source")!=SOURCE or report.get("research_only") is not True:
        raise ValueError("Invalid exit report source")
    if any(report.get(k) is not False for k in (*FALSE_FLAGS,"transport_mocked","quote_source_timestamp_verified","fee_semantics_verified","api_key_used")):
        raise ValueError("Unexpected exit report flags")
    status=report.get("status")
    rows=report["quotes"]
    if status not in ("exit_quotes_complete","exit_quotes_partial","no_due_entries") or not isinstance(rows,list) or len(rows)>MAX_QUOTES:
        raise ValueError("Invalid exit report")
    if status=="no_due_entries" and rows or status=="exit_quotes_complete" and not rows:
        raise ValueError("Inconsistent exit report")
    if type(report.get("attempted_quotes")) is not int or not len(rows)<=report["attempted_quotes"]<=MAX_QUOTES:
        raise ValueError("Invalid quote attempt count")
    if status=="exit_quotes_complete" and report["attempted_quotes"]!=len(rows):
        raise ValueError("Incomplete quote report")
    seen=set()
    for row in rows:
        mint=row["mint"];digest=row["entry_source_digest"];index=row["entry_source_index"]
        if not address(mint) or mint==USDC or not isinstance(digest,str) or not re.fullmatch("[0-9a-f]{64}",digest) or type(index) is not int or not 0<=index<=2:
            raise ValueError("Invalid exit provenance")
        start=instant(row["entry_timestamp"]);end=instant(row["retrieved_at"])
        if not MIN_AGE<=(end-start).total_seconds()<=MAX_AGE:raise ValueError("Exit outside research horizon")
        amount,received,delta=leg_amounts(row["sell"],mint,USDC)
        if row["quantity_raw"]!=str(amount):raise ValueError("Exit quantity mismatch")
        key=(digest,index)
        if key in seen:raise ValueError("Duplicate entry reference")
        seen.add(key)
    return rows

