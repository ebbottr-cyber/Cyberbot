"""Local Windows resource and research health diagnostics. No network or DB writes."""
import argparse
import ctypes
import json
import os
import shutil
import time
from pathlib import Path
from tools.solana_pwa_publish import read
from tools.solana_paper_replay import FALSE_FLAGS

MIB=1024**2
MIN_FREE_DISK=2048*MIB
MIN_AVAILABLE_RAM=512*MIB

class MemoryStatus(ctypes.Structure):
    _fields_=[("length",ctypes.c_uint32),("load",ctypes.c_uint32)]+[
        (name,ctypes.c_uint64) for name in ("total_phys","available_phys","total_page",
        "available_page","total_virtual","available_virtual","available_extended")]

class FileTime(ctypes.Structure):
    _fields_=[("low",ctypes.c_uint32),("high",ctypes.c_uint32)]
    def ticks(self):return (self.high<<32)|self.low

def windows_resources():
    if os.name!="nt":return None,None,None
    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    mem=MemoryStatus();mem.length=ctypes.sizeof(mem)
    mem_ok=kernel.GlobalMemoryStatusEx(ctypes.byref(mem))
    def times():
        idle,kernel_time,user=FileTime(),FileTime(),FileTime()
        if not kernel.GetSystemTimes(ctypes.byref(idle),ctypes.byref(kernel_time),ctypes.byref(user)):return None
        return idle.ticks(),kernel_time.ticks()+user.ticks()
    first=times();time.sleep(.25);last=times()
    cpu=None
    if first and last:
        total=last[1]-first[1];idle=last[0]-first[0]
        if total>0 and 0<=idle<=total:cpu=round(100*(total-idle)/total,1)
    return (int(mem.total_phys) if mem_ok else None,
            int(mem.available_phys) if mem_ok else None,cpu)

def policy(free,available,cpu):
    blockers=[];warnings=[]
    if free<MIN_FREE_DISK:blockers.append("low_disk_space")
    if available is None:blockers.append("ram_measurement_unavailable")
    elif available<MIN_AVAILABLE_RAM:blockers.append("low_available_ram")
    if cpu is None:warnings.append("cpu_measurement_unavailable")
    elif cpu>=90:warnings.append("high_cpu_sample")
    return blockers,warnings

def health(data_root):
    root=Path(data_root).resolve(strict=True)
    if not root.is_dir():raise ValueError("Research directory required")
    disk=shutil.disk_usage(root)
    total,available,cpu=windows_resources()
    blockers,warnings=policy(disk.free,available,cpu)
    db=root/"solana-research.sqlite3"
    stop=db.with_name(db.name+".research.stop").exists()
    lock=db.with_name(db.name+".research.lock").exists()
    if stop:blockers.append("operator_review_stop_marker")
    if lock:blockers.append("scheduler_lock_present")
    try:
        panel=read(root/"reports")
        state=panel["publication_state"]
        stale=panel.get("publication_stale")
        if stale:warnings.append("publication_stale")
        if state in ("error","partial"):warnings.append("last_research_incomplete")
    except (ValueError,TypeError,KeyError,AttributeError,ArithmeticError,OSError):
        state="invalid";stale=None;warnings.append("invalid_publication")
    sizes={}
    for name in ("solana-research.sqlite3","solana-model-history.sqlite3"):
        path=root/name
        sizes[name]=path.stat().st_size if path.is_file() and not path.is_symlink() else None
    return {"status":"preflight_blocked" if blockers else "preflight_ok",
            "platform":"windows" if os.name=="nt" else "unsupported",
            "research_only":True,"resource_scope":"host_not_bot_process",
            "cpu_sample_pct":cpu,"total_ram_bytes":total,"available_ram_bytes":available,
            "disk_free_bytes":disk.free,"disk_total_bytes":disk.total,
            "minimum_free_disk_bytes":MIN_FREE_DISK,"minimum_available_ram_bytes":MIN_AVAILABLE_RAM,
            "database_file_bytes":sizes,"publication_state":state,"publication_stale":stale,
            "stop_marker_present":stop,"lock_marker_present":lock,"process_liveness_verified":False,
            "blockers":blockers,"warnings":warnings,"network_requests":False,
            "real_orders":False,**FALSE_FLAGS}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root",required=True)
    p.add_argument("--preflight",action="store_true")
    a=p.parse_args()
    try:
        result=health(a.data_root)
        print(json.dumps(result,indent=2,allow_nan=False))
        return 2 if a.preflight and result["blockers"] else 0
    except (ValueError,TypeError,AttributeError,OSError) as e:
        print(json.dumps({"status":"health_unavailable","error_type":type(e).__name__,**FALSE_FLAGS}))
        return 1

if __name__=="__main__":raise SystemExit(main())
