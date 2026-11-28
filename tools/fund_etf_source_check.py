"""Independent ETF source comparison. Never splice vendor histories."""
from contextlib import closing
from decimal import Decimal
from pathlib import Path
import sqlite3
from datetime import date
from tools.fund_etf_refresh import validate


def compare_sources(database, *, market, symbol, currency, primary, secondary,
                    tolerance="0.01", min_overlap=20, max_age_days=7):
    if market not in ("ETF","TEFAS") or primary==secondary or not primary or not secondary:
        raise ValueError("invalid_sources")
    threshold=Decimal(str(tolerance))
    if not threshold.is_finite() or not 0<threshold<=Decimal(".05") or type(min_overlap) is not int or min_overlap<20:
        raise ValueError("invalid_comparison_policy")
    base=dict(market=market,symbol=symbol,currency=currency,primary=primary,secondary=secondary,
              status="blocked",real_orders=False,source_switched=False,live_data_verified=False)
    series=[]
    with closing(sqlite3.connect(Path(database).resolve().as_uri()+"?mode=ro",uri=True)) as db:
        db.execute("BEGIN")
        for source in (primary,secondary):
            rows=db.execute("SELECT market,symbol,session,currency,close,source FROM fund_prices WHERE market=? AND symbol=? AND currency=? AND source=? ORDER BY session",(market,symbol,currency,source)).fetchall()
            try:
                validate(rows,market,symbol,currency,source,min_rows=min_overlap,max_age_days=max_age_days)
            except ValueError:
                return dict(base,reason="Kaynak verisi eksik, eski veya kalite kontrolünde engellendi.",failed_source=source)
            series.append({r[2]:Decimal(r[4]) for r in rows})
    common=sorted(series[0].keys() & series[1].keys())
    if len(common)<min_overlap or common[-1]!=max(series[0]) or common[-1]!=max(series[1]):
        return dict(base,reason="Ortak ve güncel gözlem sayısı yetersiz.",overlap=len(common))
    # Compare absolute prices, not rescaled returns; adjusted/unadjusted data
    # must not be silently treated as equivalent.
    worst=max(abs(series[1][d]/series[0][d]-1) for d in common[-min_overlap:])
    return dict(base,status="research_agreement" if worst<=threshold else "blocked",
                overlap=len(common),last_session=common[-1],max_difference_pct=str(worst*100),
                reason="Son ortak fiyatlar eşik içinde." if worst<=threshold else "Kaynaklar arasında fiyat farkı var; inceleme gerekli.")
