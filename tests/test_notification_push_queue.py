import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
import base64
import sqlite3
from contextlib import closing
from tools.notification_push_server import PushStore
from tools.notification_push_queue import PushQueue

class NotificationTests(unittest.TestCase):
    def test_offline_queue(self):
        with TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            path = tmp_path / "push.sqlite"
            store, queue = PushStore(path), PushQueue(path)
            encode = lambda x: base64.urlsafe_b64encode(x).decode().rstrip("=")
            store.save({"endpoint":"https://web.push.apple.com/test", "keys":{"p256dh":encode(bytes([4])+bytes(64)), "auth":encode(bytes(16))}})
            calls = []
            def sender(sub, payload):
                calls.append(payload)
                return 503 if len(calls)==1 else 201
            queue.enqueue(1, store.subscriptions())
            queue.enqueue(1, store.subscriptions())
            assert queue.drain(store,sender) == {"status":"disabled"}
            assert queue.drain(store,sender,enabled=True,eligible=lambda _:False) == {}
            assert not calls
            assert queue.drain(store,sender,enabled=True) == {"pending":1}
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("UPDATE push_queue SET due=0")
            assert queue.drain(store,sender,enabled=True) == {"accepted":1}
            assert queue.drain(store,sender,enabled=True) == {}
            assert len(calls)==2
