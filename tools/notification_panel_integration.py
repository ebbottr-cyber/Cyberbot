"""Explicit single-operator host integration; disabled by default."""
from fastapi import APIRouter, Depends, Request
from tools.notification_news_api import build_news_router
from tools.notification_api import build_router
from tools.notification_preferences_api import build_preferences_router
from tools.notification_push_api import build_push_router
from tools.notification_health_api import build_health_router

def mount_notification_panel(app, *, store, preferences, push_store, queue, health_path,
                             require_user, require_csrf, enabled=False, news_store=None):
    if not enabled:
        return False
    if not callable(require_user) or not callable(require_csrf):
        raise ValueError("Authentication and CSRF required")
    if getattr(app.state, "notification_panel_mounted", False):
        raise RuntimeError("Notification panel already mounted")
    # Apply CSRF to the inbox mutation without requiring tokens for reads.
    inbox = build_router(store, require_user)
    guarded = APIRouter()
    for route in inbox.routes:
        if "POST" in route.methods:
            guarded.add_api_route(route.path, route.endpoint, methods=["POST"],
                                  dependencies=[Depends(require_user), Depends(require_csrf)])
        else:
            guarded.routes.append(route)
    routers = [guarded, build_preferences_router(preferences, require_user, require_csrf),
               build_push_router(push_store, require_user, require_csrf),
               build_health_router(health_path, queue, push_store, require_user)]
    if news_store is not None:
        routers.append(build_news_router(news_store, require_user))
    # FastAPI may retain included routers as lazy wrappers. Inspect the
    # public OpenAPI representation for nested host routes, plus direct routes.
    from fastapi.openapi.utils import get_openapi
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    verbs = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
    existing = {(path, method.upper()) for path, operations in schema.get("paths", {}).items()
                for method in operations if method in verbs}
    existing.update((r.path, m) for r in app.routes for m in (getattr(r, "methods", None) or ()))
    for router in routers:
        for route in router.routes:
            methods = getattr(route, "methods", None)
            if methods is None or not hasattr(route, "path"):
                raise RuntimeError("Unsupported notification route")
            for method in methods:
                key = (route.path, method)
                if key in existing:
                    raise RuntimeError("Notification route collision")
                existing.add(key)
    for router in routers:
        app.include_router(router)
    app.openapi_schema = None
    app.state.notification_panel_mounted = True
    return True
