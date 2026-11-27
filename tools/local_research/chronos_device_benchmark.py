"""Explicit offline Chronos benchmark; CPU and CUDA must run in separate processes."""
import argparse
import json
import math
import os
import statistics
import time

from .chronos_runtime_smoke import check_path
from importlib.metadata import version


def benchmark(path, device):
    if device not in ("cpu","cuda"):
        raise ValueError("unsupported device")
    path=check_path(path)
    for key in ("HF_HUB_OFFLINE","TRANSFORMERS_OFFLINE","HF_HUB_DISABLE_TELEMETRY"):
        os.environ[key]="1"
    if device=="cpu":
        os.environ["CUDA_VISIBLE_DEVICES"]=""
    for key in ("OMP_NUM_THREADS","MKL_NUM_THREADS","OPENBLAS_NUM_THREADS"):
        os.environ[key]="2"
    import torch
    from chronos import Chronos2Pipeline
    torch.set_num_threads(2)
    gpu=device=="cuda"
    if gpu and not torch.cuda.is_available():
        return {"status":"CUDA_UNAVAILABLE","device":device,"torch_version":str(torch.__version__),
                "torch_cuda_version":torch.version.cuda,"real_orders":False,
                "automatic_promotion":False}
    if gpu:
        torch.cuda.set_device(0)
        free,total=torch.cuda.mem_get_info(0)
        if free<2*1024**3:
            return {"status":"WAIT_GPU_MEMORY","device":device,"free_vram_bytes":free,
                    "real_orders":False,"automatic_promotion":False}
        torch.cuda.reset_peak_memory_stats(0)
    def sync():
        if gpu:
            torch.cuda.synchronize(0)
    sync()
    start=time.perf_counter()
    model=Chronos2Pipeline.from_pretrained(str(path),device_map="cuda:0" if gpu else "cpu",
        local_files_only=True,use_safetensors=True,trust_remote_code=False)
    sync()
    load=time.perf_counter()-start
    actual_device=str(model.model.device)
    if actual_device.split(":")[0]!=device:
        raise ValueError("model device mismatch")
    dtype=str(model.model.dtype)
    def forecast(i):
        context=torch.tensor([100+0.1*j+0.2*math.sin(j/3+i) for j in range(21)],dtype=torch.float32)
        sync()
        start=time.perf_counter()
        with torch.inference_mode():
            quantiles,_=model.predict_quantiles([context],prediction_length=1,
                quantile_levels=[0.1,0.5,0.9],batch_size=1)
        q=quantiles[0].reshape(-1).tolist()
        sync()
        elapsed=time.perf_counter()-start
        if len(q)!=3 or not all(math.isfinite(x) for x in q) or not 0<q[0]<=q[1]<=q[2]:
            raise ValueError("invalid synthetic forecast")
        return elapsed,q
    forecast(-1) # warm-up excluded from latency statistics
    samples=[forecast(i) for i in range(10)]
    times=[x[0] for x in samples]
    result={"status":"SYNTHETIC_BENCHMARK_OK","device":actual_device,"dtype":dtype,
            "torch_version":str(torch.__version__),"chronos_version":version("chronos-forecasting"),
            "torch_cuda_version":torch.version.cuda,"model_snapshot":path.name,
            "threads":2,"warmup_runs":1,"timed_runs":len(times),
            "context_bars":21,"prediction_bars":1,"load_seconds":load,
            "inference_seconds":times,"median_seconds":statistics.median(times),
            "max_seconds":max(times),"quantiles":[x[1] for x in samples],
            "synthetic_only":True,"real_orders":False,"automatic_promotion":False}
    if gpu:
        result.update(gpu_name=torch.cuda.get_device_name(0),total_vram_bytes=total,
            peak_allocated_bytes=torch.cuda.max_memory_allocated(0),
            peak_reserved_bytes=torch.cuda.max_memory_reserved(0))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model-path",required=True)
    p.add_argument("--device",choices=("cpu","cuda"),default="cpu")
    args=p.parse_args()
    print(json.dumps(benchmark(args.model_path,args.device),indent=2,allow_nan=False))


if __name__=="__main__":
    main()
