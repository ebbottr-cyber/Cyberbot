"""Opt-in foreground supervisor. A child performs a single bounded observation cycle."""
import os,sys,time,json,subprocess,sqlite3
from pathlib import Path
from contextlib import contextmanager,closing
from .db_paths import checked,pilot_path,resolved,same
from .pilot_loop import enabled,selected,run_cycle,MIN_INTERVAL
from .worker import worker_path
from .observed_pilot import PilotError

MAX_CHILD_SECONDS=90
MAX_FAILURES=3
INTERVAL=20
RESTART_DELAY=60

def lock_path():
    p=worker_path();lock=p.with_name(p.name+".supervisor.lock")
    protected=[*checked().values(),pilot_path(),resolved("var/fx-provider.json"),resolved("var/fx-provider-quota.sqlite3")]
    for k in ("CYBERBOT_EBBOT_DB","CYBERBOT_FX_FILE"):
        if os.getenv(k):protected.append(resolved(os.environ[k]))
    if lock.is_symlink() or any(same(lock.resolve(),x) for x in protected):raise PilotError("Gözetmen kilit yolu çakışıyor.")
    return lock

@contextmanager
def single_instance():
    p=lock_path();p.parent.mkdir(parents=True,exist_ok=True)
    # OS-owned advisory lock is released on process exit, including abnormal termination.
    # Never truncate, unlink or treat the presence of a lock file as a running process.
    with p.open("a+b") as stream:
        if os.fstat(stream.fileno()).st_size==0:stream.write(b"\0");stream.flush()
        stream.seek(0)
        try:
            if os.name=="nt":
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:raise PilotError("Başka gözetmen kilidi tutuyor.") from None
        try:yield
        finally:
            stream.seek(0)
            if os.name=="nt":msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)

def child():
    # Degraded feed status is expected and its persisted backoff must remain intact.
    report=run_cycle()
    return 2 if report["status"]=="clock_regressed" else 0

def spawn():
    # subprocess.run kills and waits for the direct child on timeout. No shell, no child output.
    try:
        r=subprocess.run([sys.executable,"-m","tools.pilot_supervisor","--child"],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=MAX_CHILD_SECONDS,check=False)
        return "ok" if r.returncode==0 else "clock_regressed" if r.returncode==2 else "child_failed"
    except subprocess.TimeoutExpired:return "timeout"

def supervise(*,cycles=None,runner=spawn,sleep=time.sleep,emit=None):
    if not enabled() or os.getenv("CYBERBOT_PILOT_SUPERVISOR_ENABLED")!="1":raise PilotError("Gözetmen ve pilot izinleri kapalı.")
    selected()
    if cycles is not None and (type(cycles) is not int or not 1<=cycles<=240):raise PilotError("Gözetmen döngü sınırı.")
    failures=0;count=0
    with single_instance():
        while cycles is None or count<cycles:
            outcome=runner();count+=1
            if emit:emit({"status":outcome,"cycles":count,"automatic_entry_enabled":False,"real_orders":False})
            if outcome=="clock_regressed":return 2
            if outcome=="ok":failures=0
            else:
                failures+=1
                if failures>=MAX_FAILURES:return 1
            if cycles is None or count<cycles:sleep(INTERVAL if outcome=="ok" else RESTART_DELAY)
    return 0 if failures==0 else 1
