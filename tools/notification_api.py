"""Mount explicitly in the existing authenticated panel; disabled by default."""
from fastapi import APIRouter, Depends, HTTPException, Query
from tools.notification_center import CATEGORIES

def build_router(store, require_user):
    if not callable(require_user):
        raise ValueError("Authentication dependency required")
    router = APIRouter(prefix="/api/notifications", dependencies=[Depends(require_user)])

    @router.get("")
    def list_notifications(category: str | None = None, unread: bool = False,
                           limit: int = Query(100, ge=1, le=500)):
        if category is not None and category not in CATEGORIES:
            raise HTTPException(400, "Invalid category")
        return {"items": store.list(category=category, unread=unread, limit=limit)}

    @router.post("/{notification_id}/read")
    def mark_read(notification_id: int):
        if notification_id < 1:
            raise HTTPException(400, "Invalid notification ID")
        return {"changed": store.mark_read(notification_id)}

    return router
