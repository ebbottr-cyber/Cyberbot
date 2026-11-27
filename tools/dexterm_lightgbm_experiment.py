"""Optional CPU-only LightGBM research adapter; no automatic installation or model files."""
import math

PARAMS={"objective":"binary","metric":"binary_logloss","device_type":"cpu",
        "num_threads":1,"deterministic":True,"force_col_wise":True,
        "seed":42,"num_leaves":7,"max_depth":3,"min_data_in_leaf":20,
        "learning_rate":0.05,"lambda_l2":1.0,"verbosity":-1}
ROUNDS=50

class OptionalModelUnavailable(RuntimeError):
    pass

def fit_lightgbm(train,test):
    try:
        import lightgbm as lgb
        import numpy as np
    except (ImportError,OSError) as e:
        raise OptionalModelUnavailable("lightgbm_or_native_dependency_unavailable") from e
    try:
        x=np.asarray([x for x,y in train],dtype=np.float64)
        y=np.asarray([y for x,y in train],dtype=np.int32)
        data=lgb.Dataset(x,label=y)
        model=lgb.train(dict(PARAMS),data,num_boost_round=ROUNDS)
        predictions=model.predict(np.asarray([x for x,y in test],dtype=np.float64),num_threads=1)
    except (lgb.basic.LightGBMError,ValueError,OSError,TypeError) as e:
        raise OptionalModelUnavailable("lightgbm_fit_or_prediction_failed") from e
    values=[float(p) for p in predictions]
    if len(values)!=len(test) or any(not math.isfinite(p) or not 0<=p<=1 for p in values):
        raise OptionalModelUnavailable("lightgbm_invalid_predictions")
    return values,str(lgb.__version__)
