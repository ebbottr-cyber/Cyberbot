"""Encrypted Web Push transport; requires pywebpush and server-held VAPID key."""
import os
from urllib.parse import urlsplit
from tools.notification_push_server import validate

def build_sender(*, enabled=False):
    if not enabled:
        raise RuntimeError("Web Push disabled")
    from pywebpush import WebPusher, WebPushException
    from py_vapid import Vapid
    import requests
    key = os.environ.get("CYBERBOT_VAPID_PRIVATE_KEY_FILE")
    subject = os.environ.get("CYBERBOT_VAPID_SUBJECT", "")
    if not key or not subject.startswith("mailto:") or "@" not in subject:
        raise ValueError("VAPID key file and contact required")
    vapid = Vapid.from_file(key)

    class NoRedirectSession(requests.Session):
        def request(self, method, url, **kwargs):
            kwargs["allow_redirects"] = False
            kwargs["timeout"] = 15
            kwargs["verify"] = True
            return super().request(method, url, **kwargs)

    def sender(subscription, payload):
        sub = validate(subscription)
        url = urlsplit(sub["endpoint"])
        claims = {"aud": f"{url.scheme}://{url.netloc}", "sub": subject}
        headers = vapid.sign(claims)
        with NoRedirectSession() as session:
            session.trust_env = False
            try:
                response = WebPusher(sub, requests_session=session).send(
                    data=payload, headers=headers, ttl=300, timeout=15,
                    content_encoding="aes128gcm")
                return response.status_code
            except WebPushException as exc:
                if exc.response is not None:
                    return exc.response.status_code
                raise
    return sender
