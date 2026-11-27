"""Explicit single-operator host integration; disabled by default."""
from fastapi import APIRouter, Depends, Request
from tools.notification_api import build_router
from tools.notification_preferences_api import build_preferences_router
from tools.notification_push_api import build_push_router
from tools.notification_health_api import build_health_router

def mount_notification_panel(app, *, store, preferences, push_store, queue, health_path,
                             require_user, require_csrf, enabled=False):
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
    combined = APIRouter()
    combined.include_router(guarded)
    combined.include_router(build_preferences_router(preferences, require_user, require_csrf))
    combined.include_router(build_push_router(push_store, require_user, require_csrf))
    combined.include_router(build_health_router(health_path, queue, push_store, require_user))
    existing = {(r.path,m) for r in app.routes for m in (getattr(r,"methods",None) or ())}
    if any((r.path,m) in existing for r in combined.routes for m in r.methods):
        raise RuntimeError("Notification route collision")
    app.include_router(combined)
    app.state.notification_panel_mounted = True
    return True
