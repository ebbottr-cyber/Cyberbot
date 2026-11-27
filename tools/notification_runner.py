"""Windows foreground worker suitable for an explicitly configured task."""
import argparse
import signal
import threading
from pathlib import Path
from contextlib import contextmanager

@contextmanager
def single_instance(path):
    import msvcrt
    with open(path, "a+b") as lock:
        lock.seek(0, 2)
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError("Notification worker already running") from exc
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--enable", action="store_true")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--interval", type=int, default=300)
    args = parser.parse_args()
    if not args.enable:
        print("Disabled; explicit --enable required")
        return
    from tools.notification_center import NotificationStore
    from tools.notification_news_store import NewsStore
    from tools.notification_preferences import Preferences
    from tools.notification_push_server import PushStore
    from tools.notification_push_queue import PushQueue
    from tools.notification_service import run_cycle
    from tools.notification_scheduler import run_periodic
    from tools.notification_vapid_sender import build_sender
    state = Path.home() / ".cyberbot-private"
    state.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    with single_instance(state / "notification-worker.lock"):
        store = NotificationStore(state / "notifications.sqlite3")
        news = NewsStore(state / "research-news.sqlite3")
        prefs = Preferences(state / "preferences.sqlite3")
        subscriptions = PushStore(state / "subscriptions.sqlite3")
        queue = PushQueue(state / "push-queue.sqlite3")
        sender = build_sender(enabled=True) if args.push else None
        def cycle():
            return run_cycle(store, subscriptions, queue, preferences=prefs,
                             enabled=True, push_enabled=args.push, sender=sender, news_store=news)
        run_periodic(cycle, state / "notification-health.json", stop,
                     enabled=True, interval=args.interval)

if __name__ == "__main__":
    main()
