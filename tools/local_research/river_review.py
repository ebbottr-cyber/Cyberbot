"""River prequential research. No network, persistence or trade execution."""
import math
from statistics import mean
from .lightgbm_review import samples

WARMUP = 60
MIN_SCORED = 20
MAX_PRICES = 100_000


def evaluate(prices, *, model_factory=None):
    """Replay one contiguous series. Predict and score before learning its target.

    Caller is responsible for timestamps, provenance and usage rights.
    Separate invocation per instrument and timeframe; never share model state.
    """
    if len(prices) > MAX_PRICES:
        raise ValueError("split into bounded research batches")
    rows = samples(prices)
    if len(rows) < WARMUP + MIN_SCORED:
        raise ValueError("insufficient history")
    if model_factory is None:
        from river import linear_model, preprocessing
        model = preprocessing.StandardScaler() | linear_model.LinearRegression()
    else:
        model = model_factory()
    errors = {"naive": [], "river": []}
    for i, (values, actual) in enumerate(rows):
        x = {f"r{j}": v for j, v in enumerate(values)}
        predicted = model.predict_one(x)
        if not isinstance(predicted, (float, int)) or not math.isfinite(predicted) or predicted <= -1:
            raise ValueError("invalid online prediction")
        if i >= WARMUP:
            errors["naive"].append(abs(actual))
            errors["river"].append(abs(actual-predicted))
        model.learn_one(x, actual)
    return {"version": "river-replay-1", "warmup": WARMUP,
            "scored": len(errors["river"]), "updates": len(rows),
            "paired_mae_pct": {n: mean(v)*100 for n,v in errors.items()},
            "evidence_status": "EXPLORATORY_UNVERIFIED",
            "live_learning_enabled": False, "automatic_promotion": False,
            "profitability_verified": False, "real_orders": False}


def self_test():
    prices = [100.]
    for i in range(180):
        prices.append(prices[-1]*(1+0.001*math.sin(i/7)))
    result = evaluate(prices)
    assert result["scored"] == 100
    assert result["updates"] == 160
    assert all(math.isfinite(v) for v in result["paired_mae_pct"].values())
    print("RIVER_SYNTHETIC: PASS")


if __name__ == "__main__":
    self_test()
