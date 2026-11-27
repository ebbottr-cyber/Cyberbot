"""Explicit offline Chronos CPU runtime smoke. Uses synthetic input only."""
import argparse
from datetime import datetime, timezone
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import time


def check_path(value):
    path=Path(value).expanduser().resolve(strict=True)
    if not path.is_dir() or not (path/"config.json").is_file():
        raise ValueError("local model config required")
    if not any(p.is_file() for p in path.glob("*.safetensors")):
        raise ValueError("local safetensors weights required")
    return path


def smoke(path):
    path=check_path(path)
    for key in ("HF_HUB_OFFLINE","TRANSFORMERS_OFFLINE","HF_HUB_DISABLE_TELEMETRY"):
        os.environ[key]="1"
    os.environ["CUDA_VISIBLE_DEVICES"]=""
    for key in ("OMP_NUM_THREADS","MKL_NUM_THREADS","OPENBLAS_NUM_THREADS"):
        os.environ[key]="2"
    import torch
    from chronos import Chronos2Pipeline
    torch.set_num_threads(2)
    started=time.monotonic()
    model=Chronos2Pipeline.from_pretrained(str(path),device_map="cpu",
        local_files_only=True,use_safetensors=True,trust_remote_code=False)
    load_seconds=time.monotonic()-started
    timings=[]
    for i in range(3):
        context=torch.tensor([100+0.1*j+0.2*math.sin(j/3+i) for j in range(21)],dtype=torch.float32)
        start=time.monotonic()
        with torch.inference_mode():
            quantiles,_=model.predict_quantiles([context],prediction_length=1,
                quantile_levels=[0.1,0.5,0.9],batch_size=1)
        q=quantiles[0].reshape(-1).tolist()
        if len(q)!=3 or not all(math.isfinite(x) for x in q) or not 0<q[0]<=q[1]<=q[2]:
            raise ValueError("invalid synthetic forecast")
        timings.append(time.monotonic()-start)
    peak=None
    import sys
    if sys.platform=="linux":
        import resource
        peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    return {"runtime_verified":True,"created_at":datetime.now(timezone.utc).isoformat(),
            "model_path":str(path),"device":"cpu","torch_version":str(torch.__version__),
            "chronos_version":version("chronos-forecasting"),"threads":2,
            "context_bars":21,"prediction_bars":1,"synthetic_runs":3,
            "load_seconds":load_seconds,"inference_seconds":timings,
            "linux_process_peak_rss_mib":peak,"synthetic_only":True,
            "real_orders":False,"automatic_promotion":False}


def write_report(root,report):
    folder=Path(root).resolve(strict=True)/"var/ai"
    if not folder.is_dir() or folder.is_symlink() or folder.parent.is_symlink():
        raise ValueError("existing private var/ai directory required")
    stamp=datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    target=folder/("chronos-runtime-"+stamp+".json")
    # Publish a complete report without overwriting an existing report.
    tmp=target.with_suffix(".tmp")
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(report,f,allow_nan=False,indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.link(tmp,target)
    finally:
        tmp.unlink(missing_ok=True)
    return target


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model-path",type=Path,required=True)
    p.add_argument("--root",type=Path,default=Path.cwd())
    p.add_argument("--write-report",action="store_true")
    args=p.parse_args()
    result=smoke(args.model_path)
    if args.write_report:
        result["report_path"]=str(write_report(args.root,result))
    print(json.dumps(result,indent=2,allow_nan=False))


if __name__=="__main__":
    main()
