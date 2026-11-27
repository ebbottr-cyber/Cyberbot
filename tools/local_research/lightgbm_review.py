"""Optional CPU LightGBM research model. No downloads, storage or execution."""
import math
from statistics import mean, pstdev

CONTEXT = 20
MIN_TRAIN = 60
MIN_TEST = 20


def features(returns):
    if len(returns) != CONTEXT or any(not math.isfinite(x) or abs(x) > 10 for x in returns):
        raise ValueError("invalid return context")
    return [*returns[-5:], mean(returns[-5:]), mean(returns),
            pstdev(returns[-5:]), pstdev(returns),
            min(returns), max(returns)]


def samples(prices):
    """Caller must supply a single chronological, validated contiguous segment."""
    if any(type(p) not in (int, float) or not math.isfinite(p) or p <= 0 for p in prices):
        raise ValueError("invalid prices")
    r = [b/a-1 for a, b in zip(prices, prices[1:])]
    if any(not math.isfinite(x) or abs(x) > 10 for x in r):
        raise ValueError("extreme return")
    return [(features(r[i-CONTEXT:i]), r[i]) for i in range(CONTEXT, len(r))]


def split(rows):
    boundary = len(rows)*7//10
    train = rows[:boundary-CONTEXT] if boundary >= CONTEXT else []
    test = rows[boundary:]
    if len(train) < MIN_TRAIN or len(test) < MIN_TEST:
        raise ValueError("insufficient embargoed history")
    return train, test


def evaluate(prices):
    """Fit once on early targets, compare on later paired targets; no promotion."""
    train, test = split(samples(prices))
    import numpy as np
    import lightgbm as lgb

    x = np.array([r[0] for r in train], dtype=np.float64)
    y = np.array([r[1] for r in train], dtype=np.float64)
    model = lgb.train({"objective": "regression_l1", "verbosity": -1,
                       "num_threads": 2, "seed": 42, "deterministic": True,
                       "force_col_wise": True, "num_leaves": 7,
                       "min_data_in_leaf": 10, "learning_rate": 0.05},
                      lgb.Dataset(x, label=y), num_boost_round=40)
    predictions = model.predict(np.array([r[0] for r in test], dtype=np.float64), num_threads=2)
    if len(predictions) != len(test) or any(not math.isfinite(float(p)) or p <= -1 for p in predictions):
        raise ValueError("invalid model prediction")
    return {"model": "lightgbm", "train_samples": len(train), "test_samples": len(test),
            "embargo_returns": CONTEXT,
            "paired_mae_pct": {"naive": mean(abs(y) for _, y in test)*100,
                               "lightgbm": mean(abs(y-float(p)) for (_, y), p in zip(test, predictions))*100},
            "evidence_status": "EXPLORATORY_UNVERIFIED", "automatic_promotion": False,
            "profitability_verified": False, "real_orders": False}


def self_test():
    p = [100.0]
    for i in range(300):
        p.append(p[-1]*(1+0.002*math.sin(i/7)))
    rows = samples(p)
    assert rows[0][0] == samples(p[:22])[0][0]
    changed = p[:21]+[p[21]*1.01]
    assert samples(changed)[0][0] == rows[0][0]
    assert samples(changed)[0][1] != rows[0][1]
    train, test = split(rows)
    assert len(rows)-len(train)-len(test) == CONTEXT
    for bad in ([1, 0], [1, float('nan')], [1]*30):
        try:
            split(samples(bad))
        except ValueError:
            pass
        else:
            raise AssertionError("invalid input accepted")
    result = evaluate(p)
    assert result["test_samples"] == len(test)
    assert all(math.isfinite(v) for v in result["paired_mae_pct"].values())
    assert result["real_orders"] is False
    print("SYNTHETIC_LIGHTGBM_SELF_TEST: PASS")


if __name__ == "__main__":
    self_test()
