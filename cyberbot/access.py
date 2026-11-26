"""Fail-closed access guard for loopback or explicitly configured Tailscale Serve.
The trusted proxy must connect to loopback; do not enable Uvicorn proxy headers.
Tailscale Serve strips incoming identity headers and inserts authenticated identity.
"""
import os
import re
from hmac import compare_digest

def authorize(request):
    client=request.client.host if request.client else ""
    if client not in ("127.0.0.1","::1"):
        return "Yalnız yerel sunucu veya güvenilir yerel proxy erişimi."
    host=request.headers.get("host","")
    remote=os.getenv("CYBERBOT_TAILSCALE_ENABLED")=="1"
    write=request.method not in ("GET","HEAD")
    if remote:
        allowed_host=os.getenv("CYBERBOT_TAILSCALE_HOST","").lower()
        allowed_login=os.getenv("CYBERBOT_TAILSCALE_LOGIN","")
        if not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+\.ts\.net",allowed_host) or not allowed_login:
            return "Tailscale erişimi yapılandırılmadı."
        port=os.getenv("CYBERBOT_TAILSCALE_PORT","8443")
        if port not in ("443","8443"):
            return "Tailscale portu geçersiz."
        authority=allowed_host if port=="443" else allowed_host+":"+port
        if host.lower() not in ((allowed_host,allowed_host+":443") if port=="443" else (authority,)):
            return "Tailscale alan adı reddedildi."
        identity=request.headers.getlist("tailscale-user-login")
        if len(identity)!=1 or not compare_digest(identity[0].encode(),allowed_login.encode()):
            return "Tailscale kullanıcı kimliği yetkisiz."
        if write:
            if os.getenv("CYBERBOT_TAILSCALE_WRITE")!="1":
                return "Mobil erişim salt okunur."
            if request.headers.get("origin")!="https://"+authority:
                return "Güvenli kaynak doğrulaması başarısız."
    else:
        if not re.fullmatch(r"(localhost|127\.0\.0\.1)(:[0-9]{1,5})?",host):
            return "Yalnız yerel erişim."
        if write:
            origin=request.headers.get("origin")
            if origin and origin!="http://"+host:
                return "Kaynak reddedildi."
    if write and request.headers.get("x-cyberbot-paper")!="1":
        return "Sanal işlem başlığı gerekli."
    return None
