import os
from functools import lru_cache
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel
from .engine import Ledger, PaperError
from .lab import experiment
from .market import INDEX
from .access import authorize
from .db_paths import checked,PathCollision

app=FastAPI(title="Cyberbot Obsidian",docs_url=None,redoc_url=None,openapi_url=None)

@lru_cache
def _ledger(path):
    return Ledger(path)
def ledger():
    return _ledger(checked()["paper"])
ledger.cache_clear=_ledger.cache_clear

@app.middleware("http")
async def local_guard(request:Request, call_next):
    denial=authorize(request)
    if denial:
        return JSONResponse({"detail":denial},status_code=403,headers={"Cache-Control":"no-store"})
    response=await call_next(request)
    response.headers["Cache-Control"]="no-store"
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["X-Frame-Options"]="DENY"
    response.headers["Content-Security-Policy"]="default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; manifest-src 'self'; img-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    return response

@app.exception_handler(PathCollision)
async def collision(request:Request,exc:PathCollision):
    return JSONResponse({"detail":str(exc)},status_code=409)

@app.exception_handler(PaperError)
async def paper_error(request:Request,exc:PaperError):
    return JSONResponse({"detail":str(exc)},status_code=409)

class Buy(BaseModel):
    symbol:str

@app.get("/",response_class=HTMLResponse)
def home():
    html = (Path(__file__).parent/"web"/"index.html").read_text(encoding="utf-8")
    if getattr(app.state, "notification_panel_mounted", False):
        html = html.replace("</head>", '<link rel="stylesheet" href="/ui/notifications/center.css"></head>', 1)
        html = html.replace("</header>", '<div id="notificationBell" class="cyberbot-notifications"></div><a href="/notification-settings">Bildirim ayarları</a></header>', 1)
        html = html.replace("</body>", '<script type="module" src="/ui/notifications/host.js"></script></body>', 1)
    return html

@app.get("/api/status")
def status():
    return ledger().snapshot()

@app.post("/api/paper/buy")
def buy(body:Buy):
    ledger().buy(body.symbol)
    return ledger().snapshot()

@app.post("/api/paper/sell/{trade_id}")
def sell(trade_id:int):
    ledger().sell(trade_id)
    return ledger().snapshot()

@app.post("/api/paper/advance")
def advance():
    ledger().advance()
    return ledger().snapshot()

@app.get("/api/lab/{symbol}")
def lab(symbol:str):
    if symbol not in INDEX:
        raise HTTPException(404,"Bilinmeyen sembol.")
    return experiment(symbol)

from .data_api import router as data_router
app.include_router(data_router)

from .trader_api import router as trader_router
app.include_router(trader_router)

from .analysis_api import router as analysis_router
app.include_router(analysis_router)

from .strategy_api import router as strategy_router
app.include_router(strategy_router)

from .learning_api import router as learning_router
app.include_router(learning_router)

from .models_api import router as models_router
app.include_router(models_router)

from .pwa import router as pwa_router
app.include_router(pwa_router)

from .operations_api import router as operations_router
app.include_router(operations_router)

from .stress_api import router as stress_router
app.include_router(stress_router)

from .capital_api import router as capital_router
app.include_router(capital_router)

from .futures_api import router as futures_router
app.include_router(futures_router)

from .development_api import router as development_router
app.include_router(development_router)

from .knowledge_api import router as knowledge_router
app.include_router(knowledge_router)

# Optional single-operator notification API; existing access guard remains authoritative.
if os.getenv("CYBERBOT_NOTIFICATION_PANEL_ENABLED") == "1":
    from tools.notification_center import NotificationStore
    from tools.notification_preferences import Preferences
    from tools.notification_push_server import PushStore
    from tools.notification_push_queue import PushQueue
    from tools.notification_news_store import NewsStore
    from tools.notification_panel_integration import mount_notification_panel

    def notification_user(request: Request):
        denial = authorize(request)
        if denial:
            raise HTTPException(403, denial)

    def notification_csrf(request: Request):
        notification_user(request)
        host = request.headers.get("host", "")
        scheme = "https" if os.getenv("CYBERBOT_TAILSCALE_ENABLED") == "1" else "http"
        if request.headers.get("origin") != scheme + "://" + host:
            raise HTTPException(403, "Bildirim kaynağı doğrulanamadı.")

    @app.get("/notification-settings", response_class=HTMLResponse)
    def notification_settings_page():
        return """<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Obsidian | Bildirim ayarları</title><link rel="stylesheet" href="/ui/obsidian.css">
<link rel="stylesheet" href="/ui/panel-mobile.css"></head><body><main>
<a href="/">Ana panel</a><section id="notificationSettings">Ayarlar yükleniyor…</section>
<script type="module" src="/ui/notifications/settings-host.js"></script></main></body></html>"""

    @app.get("/api/notifications/device-config")
    def notification_device_config(request: Request):
        notification_user(request)
        import re
        key = os.getenv("CYBERBOT_VAPID_PUBLIC_KEY", "")
        writable = os.getenv("CYBERBOT_TAILSCALE_ENABLED") != "1" or os.getenv("CYBERBOT_TAILSCALE_WRITE") == "1"
        return {"public_key": key if re.fullmatch(r"[A-Za-z0-9_-]{87}", key) and writable else "",
                "writable": writable}

    @app.get("/ui/notifications/{asset}")
    def notification_asset(asset: str):
        assets = {"center.js": ("notification_center_ui.js", "application/javascript"),
                  "center.css": ("notification_center_ui.css", "text/css"),
                  "settings.js": ("notification_settings_ui.js", "application/javascript"),
                  "notification_push_client.js": ("notification_push_client.js", "application/javascript")}
        if asset == "settings-host.js":
            return Response("""import {mountNotificationSettings} from './settings.js';
const root = document.getElementById('notificationSettings');
const request = (url, options = {}) => fetch(url, {...options, credentials:'same-origin',
  headers:{...options.headers, 'X-Cyberbot-Paper':'1'}});
try {
  const response = await request('/api/notifications/device-config');
  if (!response.ok) throw new Error();
  const config = await response.json();
  await mountNotificationSettings(root, request, config.public_key);
  if (!config.writable) {
    for (const control of root.querySelectorAll('input,button,select')) control.disabled = true;
    const note = document.createElement('p'); note.textContent = 'Mobil erişim salt okunur.';
    root.prepend(note);
  }
} catch { root.textContent = 'Bildirim ayarları yüklenemedi.'; }
""", media_type="application/javascript")
        if asset == "host.js":
            return Response("""import {mountNotificationCenter} from './center.js';
const root = document.getElementById('notificationBell');
if (root) {
  const request = (url, options = {}) => fetch(url, {...options, credentials:'same-origin',
    headers:{...options.headers, 'X-Cyberbot-Paper':'1'}});
  const center = mountNotificationCenter(root, request);
  const timer = setInterval(() => { if (!document.hidden) center.refresh(); }, 30000);
  window.addEventListener('pagehide', event => { if (!event.persisted) { clearInterval(timer); center.destroy(); } });
}
""", media_type="application/javascript")
        if asset not in assets:
            raise HTTPException(404)
        filename, media = assets[asset]
        return Response((Path(__file__).resolve().parent.parent / "tools" / filename).read_text(encoding="utf-8"), media_type=media)

    notification_state = Path.home() / ".cyberbot-private"
    notification_state.mkdir(parents=True, exist_ok=True)
    mount_notification_panel(
        app, store=NotificationStore(notification_state / "notifications.sqlite3"),
        preferences=Preferences(notification_state / "preferences.sqlite3"),
        push_store=PushStore(notification_state / "subscriptions.sqlite3"),
        queue=PushQueue(notification_state / "push-queue.sqlite3"),
        news_store=NewsStore(notification_state / "research-news.sqlite3"),
        health_path=notification_state / "notification-health.json",
        require_user=notification_user, require_csrf=notification_csrf, enabled=True,
    )
