"""Linux VPS heavy research admission guard. Not a hard memory limiter."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

MIB = 1024 * 1024
RESERVE_MIB = 2048
MIN_FREE_DISK_MIB = 5120
MAX_LOAD_1M = 4.0
JOBS = {"chronos": (2048, 900), "lightgbm": (3072, 1800)}


def decision(model, available_mib, disk_mib, load):
    if model not in JOBS:
        raise ValueError("unknown heavy job")
    import math
    if any(not math.isfinite(v) or v < 0 for v in (available_mib, disk_mib, load)):
        raise ValueError("invalid resource reading")
    if available_mib < RESERVE_MIB + JOBS[model][0]:
        return "WAIT_MEMORY"
    if disk_mib < MIN_FREE_DISK_MIB:
        return "WAIT_DISK"
    if load >= MAX_LOAD_1M:
        return "WAIT_CPU"
    return "READY"


def available_memory():
    meminfo = Path("/proc/meminfo").read_text()
    value = next(int(line.split()[1])//1024 for line in meminfo.splitlines()
                 if line.startswith("MemAvailable:"))
    # Account for finite cgroup v2 limits, including ancestor limits.
    base = Path("/sys/fs/cgroup")
    path = next(line.split(":", 2)[2] for line in Path("/proc/self/cgroup").read_text().splitlines()
                if line.startswith("0::"))
    group = (base / path.lstrip("/")).resolve()
    if not group.is_relative_to(base) or not group.is_dir():
        raise ValueError("cgroup unavailable")
    for node in (group, *group.parents):
        if not node.is_relative_to(base):
            break
        limit = node / "memory.max"
        if not limit.is_file():
            continue
        raw = limit.read_text().strip()
        if raw != "max":
            remaining = max(0, int(raw)-int((node/"memory.current").read_text()))
            value = min(value, remaining//MIB)
    return value


def run(model, command, state):
    """All heavy research launchers must share this private lock directory."""
    if sys.platform != "linux":
        raise RuntimeError("Ubuntu/Linux required")
    if model not in JOBS or not command:
        raise ValueError("invalid job")
    import fcntl
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    if state.is_symlink() or state.stat().st_uid != os.getuid() or state.stat().st_mode & 0o077:
        raise ValueError("private lock directory required")
    with (state/"heavy.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("WAIT_HEAVY_JOB", flush=True)
            return 75
        status = decision(model, available_memory(), shutil.disk_usage(state).free//MIB,
                          os.getloadavg()[0])
        print(status, flush=True)
        if status != "READY":
            return 75
        env = os.environ.copy()
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                     "NUMEXPR_NUM_THREADS"):
            env[name] = "2"
        env["CUDA_VISIBLE_DEVICES"] = ""
        proc = subprocess.Popen(command, env=env, start_new_session=True)
        try:
            return proc.wait(timeout=JOBS[model][1])
        except subprocess.TimeoutExpired:
            return 124
        finally:
            # Clean up the process group even if a wrapper spawned descendants.
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()


def self_test():
    cases = [
        ("chronos", 4095, 6000, 1, "WAIT_MEMORY"),
        ("chronos", 4096, 6000, 1, "READY"),
        ("lightgbm", 5119, 6000, 1, "WAIT_MEMORY"),
        ("lightgbm", 5120, 5000, 1, "WAIT_DISK"),
        ("lightgbm", 5120, 6000, 4, "WAIT_CPU"),
        ("lightgbm", 5120, 6000, 3, "READY"),
    ]
    for model, mem, disk, load, expected in cases:
        assert decision(model, mem, disk, load) == expected
    for bad in (-1, float("nan"), float("inf")):
        try:
            decision("chronos", bad, 6000, 1)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid reading accepted")
    print("RESOURCE_POLICY_SELF_TEST: PASS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--model", choices=JOBS)
    parser.add_argument("--state", type=Path, default=Path.home()/".local/state/cyberbot-ai")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    return run(args.model, command, args.state)


if __name__ == "__main__":
    sys.exit(main())
