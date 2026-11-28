"""Common offline model evaluation and Turkish research explanation."""
import json
import math
import sqlite3
import tempfile
from datetime import date
from pathlib import Path

from tools.fund_etf_analysis import analyze
from tools.fund_etf_learning import evaluate as logistic
from tools.fund_etf_multi_learning import evaluate as challengers
from tools.fund_etf_champion import compare
from tools.fund_etf_decision import decide
from tools.fund_etf_gemini import explain

EXPECTED = {"LogisticRegression", "LightGBM", "XGBoost", "River"}


def model_review(database, market, symbol, currency, source, *, min_train=100,
                 horizon=5, step=20, min_samples=100):
    """Freeze one price series so all models evaluate exactly the same observations."""
    if market not in ("TEFAS", "ETF") or min_train < 100 or horizon < 1 or step < 1 or min_samples < 100:
        raise ValueError("invalid_evaluation_policy")
    identity = (market, symbol, currency, source)
    result = dict(market=market, symbol=symbol, currency=currency, source=source,
                  status="blocked", candidate=None, model_promoted=False,
                  real_orders=False, live_data_verified=False, ai_prediction=False)
    try:
        with sqlite3.connect(Path(database).resolve().as_uri()+"?mode=ro", uri=True) as db:
            rows = db.execute("SELECT session,close FROM fund_prices WHERE market=? AND symbol=? AND currency=? AND source=? ORDER BY session", identity).fetchall()
    except sqlite3.Error:
        return dict(result, reason_tr="Fiyat arşivi okunamadı.")
    try:
        days = [date.fromisoformat(r[0]) for r in rows]
        prices = [float(r[1]) for r in rows]
        if days != sorted(set(days)) or any(d > date.today() for d in days):
            raise ValueError("invalid_sessions")
        if any(not math.isfinite(p) or p <= 0 for p in prices):
            raise ValueError("invalid_prices")
    except (ValueError, TypeError, OverflowError):
        return dict(result, reason_tr="Geçersiz fiyat veya tarih bulundu.")
    if len(rows) < 20+min_train+2*horizon+min_samples:
        return dict(result, reason_tr="Ortak model testi için yeterli geçmiş veri yok.",
                    observations=len(rows))
    policy = dict(min_train=min_train, horizon=horizon, step=step)
    errors = {}
    reports = {}
    with tempfile.TemporaryDirectory() as folder:
        snapshot = Path(folder)/"evaluation.sqlite3"
        with sqlite3.connect(snapshot) as db:
            db.execute("CREATE TABLE fund_prices (market TEXT,symbol TEXT,currency TEXT,source TEXT,session TEXT,close TEXT)")
            db.executemany("INSERT INTO fund_prices VALUES (?,?,?,?,?,?)",
                           [identity+tuple(r) for r in rows])
        metrics = analyze(snapshot, *identity)
        try:
            reports["LogisticRegression"] = logistic(snapshot, *identity, **policy)
        except Exception as exc:
            errors["LogisticRegression"] = type(exc).__name__
        try:
            reports.update(challengers(snapshot, *identity, **policy))
        except Exception as exc:
            errors["challengers"] = type(exc).__name__
    result.update(observations=len(rows), last_session=days[-1].isoformat(),
                  metrics=metrics, errors=errors,
                  models={name: {"status": r.get("status"), "samples": len(r.get("predictions", []))}
                          for name,r in reports.items()})
    if errors or set(reports) != EXPECTED:
        return dict(result, reason_tr="Model seti eksik; ortak karşılaştırma engellendi.")
    try:
        # Use disjoint label windows, while retaining identical evaluation dates.
        for report in reports.values():
            predictions = report.get("predictions", [])
            if report.get("status") != "offline_research":
                return dict(result, reason_tr="En az bir modelin değerlendirmesi yetersiz.")
            report["predictions"] = predictions[::horizon]
        ranking = compare(reports, min_samples=min_samples)
    except (ValueError, KeyError, TypeError, OverflowError):
        return dict(result, reason_tr="Model çıktıları doğrulanamadı.")
    result.update(status=ranking["status"], candidate=ranking.get("candidate"),
                  ranking=ranking, sampling_stride=horizon,
                  reason_tr=("Geçmiş testte incelemeye uygun aday bulundu; canlı tahmin değildir."
                             if ranking.get("candidate") else
                             "Karşılaştırma koşullarını geçen model adayı bulunamadı."))
    return result


def research_decision(metrics, ranking, *, held=False, gemini_enabled=False,
                      free_tier_confirmed=False, gemini_model=None):
    """The deterministic risk decision is authoritative; generated text is not."""
    decision = decide(metrics, ranking, held=held)
    commentary = explain(decision, metrics, enabled=gemini_enabled,
                         free_tier_confirmed=free_tier_confirmed, model=gemini_model)
    labels = {"BUY_REVIEW":"Alım incelemesi", "SELL_REVIEW":"Satım incelemesi",
              "HOLD":"Beklet", "WAIT":"Bekle"}
    return {"decision": decision, "action_tr": labels[decision["action"]],
            "verified_reason_tr": decision["reason_tr"],
            "commentary": commentary.get("commentary"),
            "commentary_provider": commentary.get("provider"),
            "commentary_verified": False,
            "execution_allowed": False, "real_orders": False}


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("database", "market", "symbol", "currency", "source"):
        p.add_argument("--"+arg, required=True)
    p.add_argument("--min-samples", type=int, default=100)
    args = vars(p.parse_args())
    print(json.dumps(model_review(**args), ensure_ascii=False, indent=2, allow_nan=False))
