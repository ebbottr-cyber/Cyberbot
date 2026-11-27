"""Foreground watchdog for the local Futures supervisor, never an exchange order client.

Owns only its child process. Recovery is observation-only, with the entry brake
set in the child's environment. No system service or permanent task installed.
"""
import argparse,json,os,queue,subprocess,sys,threading,time
from . import futures_supervisor as supervisor

VERSION="futures-watchdog-1"
HEARTBEAT_SECONDS=150
MAX_LINE=65536
MAX_RESTARTS=3
BACKOFF=(15,30,60)
WATCHED=("training_collect","paper_observe")

class Health:
    def __init__(self,symbol,started):
        self.symbol=symbol;self.last=started;self.failures={k:0 for k in WATCHED}
        self.completed=False
    def accept(self,event,now):
        if (not isinstance(event,dict) or event.get("version")!=supervisor.VERSION
            or event.get("symbol")!=self.symbol or event.get("real_orders") is not False):
            return "invalid_child_event"
        status=event.get("status");stage=event.get("stage")
        if status=="session_ended":
            self.completed=True;self.last=now;return None
        if not isinstance(stage,str) or not isinstance(status,str):return "invalid_child_event"
        self.last=now
        if stage in WATCHED:
            self.failures[stage]=self.failures[stage]+1 if status in ("rejected","missed_slot") else 0
            if self.failures[stage]>=3:return stage+"_unhealthy"
        return None
    def timeout(self,now):
        return "heartbeat_timeout" if now-self.last>=HEARTBEAT_SECONDS else None

def child_spec(symbol,minutes,paper,automatic,recovered,*,env=None):
    child_env=dict(os.environ if env is None else env)
    args=[sys.executable,"-u","-m","cyberbot.futures_supervisor","--symbol",symbol,"--minutes",str(minutes)]
    if paper:args.append("--paper")
    if automatic and not recovered:args.append("--automatic")
    else:
        child_env["CYBERBOT_FUTURES_AUTO_PAPER_ENABLED"]="0"
        child_env["CYBERBOT_FUTURES_AUTO_PAPER_CONFIRMED"]="0"
    if recovered:
        # Process-local: does not change other bots' persistent control records.
        child_env["CYBERBOT_PILOT_KILL_SWITCH"]="1"
    return args,child_env

def stop_child(child):
    if child.poll() is not None:return
    child.terminate()
    try:child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        child.kill();child.wait(timeout=5)

def monitor(symbol,minutes,paper,automatic,recovered,deadline,emit,*,monotonic=time.monotonic):
    args,env=child_spec(symbol,minutes,paper,automatic,recovered)
    child=subprocess.Popen(args,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL,shell=False)
    inbox=queue.Queue(maxsize=64);done=threading.Event()
    def offer(item):
        while not done.is_set():
            try:inbox.put(item,timeout=.2);return
            except queue.Full:continue
    def read():
        try:
            while not done.is_set():
                line=child.stdout.readline(MAX_LINE+1)
                if not line:break
                if len(line)>MAX_LINE:
                    offer(b"");break
                offer(line)
        except (OSError,ValueError):offer(b"")
        finally:offer(None)
    reader=threading.Thread(target=read,daemon=True)
    reader.start();health=Health(symbol,monotonic())
    try:
        while True:
            now=monotonic()
            if now>=deadline:return "session_deadline"
            reason=health.timeout(now)
            if reason:return reason
            try:line=inbox.get(timeout=min(1,max(.01,deadline-now)))
            except queue.Empty:continue
            if line is None:
                try:rc=child.wait(timeout=5)
                except subprocess.TimeoutExpired:return "child_stdout_closed"
                if rc==0 and health.completed:return "completed"
                if rc==130:return "interrupted"
                return "child_exit_without_completion"
            try:event=json.loads(line)
            except (ValueError,UnicodeError):return "invalid_child_event"
            reason=health.accept(event,monotonic())
            if reason:return reason
            # Child emits only bounded structured stage metadata, not credentials.
            emit(event)
    finally:
        done.set()
        try:stop_child(child)
        finally:
            reader.join(timeout=2)
            if not reader.is_alive():child.stdout.close()

def run(symbol,minutes,*,paper=False,automatic=False,restarts=MAX_RESTARTS,
        monotonic=time.monotonic,sleep=time.sleep,runner=monitor,emit=None):
    if os.getenv("CYBERBOT_FUTURES_WATCHDOG_ENABLED")!="1":raise ValueError("Watchdog izni kapalı.")
    if type(restarts) is not int or not 0<=restarts<=MAX_RESTARTS:raise ValueError("Yeniden başlatma sınırı 0–3.")
    supervisor.validate(symbol,minutes,paper,automatic)
    emit=emit or (lambda d:print(json.dumps(d,ensure_ascii=True,allow_nan=False),flush=True))
    started=monotonic();deadline=started+minutes*60+120
    attempts=0;reason="not_started";recovered=False
    def report(status,**extra):
        emit({"version":VERSION,"symbol":symbol,"status":status,"real_orders":False,**extra})
    with supervisor.lease(kind="watchdog"):
        while monotonic()<deadline:
            remaining=minutes if attempts==0 else min(minutes,max(1,int((deadline-monotonic())//60)))
            report("child_start",attempt=attempts+1,automatic_mode=automatic and not recovered,
                   recovery_entry_brake=recovered)
            try:reason=runner(symbol,remaining,paper,automatic,recovered,deadline,emit)
            except OSError:reason="child_start_or_stop_error"
            report("child_end",reason=reason)
            if reason in ("completed","interrupted","session_deadline"):break
            # A stop error could leave a child alive; never launch a second one.
            if reason=="child_start_or_stop_error":break
            if attempts>=restarts:reason="restart_limit_reached";break
            delay=BACKOFF[attempts]
            if monotonic()+delay+60>=deadline:reason="session_deadline";break
            attempts+=1;recovered=True
            report("recovery_backoff",seconds=delay,automatic_mode=False)
            sleep(delay)
    return {"version":VERSION,"symbol":symbol,"status":reason,"restarts":attempts,
            "automatic_rearmed":False,"recovery_entry_brake":recovered,"paper_enabled":paper,
            "positions_may_remain_open":paper,"real_orders":False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol",required=True,choices=("BTCUSDT","ETHUSDT"))
    p.add_argument("--minutes",type=int,default=1440);p.add_argument("--restarts",type=int,default=MAX_RESTARTS)
    p.add_argument("--paper",action="store_true");p.add_argument("--automatic",action="store_true")
    a=p.parse_args()
    try:
        d=run(a.symbol,a.minutes,paper=a.paper,automatic=a.automatic,restarts=a.restarts)
        print(json.dumps(d,ensure_ascii=True))
        return 0 if d["status"]=="completed" else 130 if d["status"]=="interrupted" else 1
    except KeyboardInterrupt:return 130
    except supervisor.ERRORS as exc:
        print(json.dumps({"status":"rejected","type":type(exc).__name__,"real_orders":False}));return 1
if __name__=="__main__":raise SystemExit(main())
