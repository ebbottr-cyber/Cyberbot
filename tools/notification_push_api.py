"""Single-operator subscription API; mount with existing auth and CSRF protection."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from tools.notification_push_server import validate

class Keys(BaseModel):
    p256dh: str = Field(max_length=128)
    auth: str = Field(max_length=128)

class Subscription(BaseModel):
    endpoint: str = Field(max_length=4096)
    keys: Keys

def build_push_router(store, require_user, require_csrf):
    if not callable(require_user) or not callable(require_csrf):
        raise ValueError("Authentication and CSRF dependencies required")
    router = APIRouter(prefix="/api/notifications/push",
                       dependencies=[Depends(require_user), Depends(require_csrf)])

    @router.post("/subscriptions")
    def subscribe(subscription: Subscription):
        try:
            data = subscription.model_dump() if hasattr(subscription, "model_dump") else subscription.dict()
            store.save(validate(data))
        except (ValueError, TypeError, KeyError):
            raise HTTPException(400, "Invalid subscription")
        return {"registered": True}

    @router.delete("/subscriptions")
    def unsubscribe(subscription: Subscription):
        try:
            data = subscription.model_dump() if hasattr(subscription, "model_dump") else subscription.dict()
            store.remove(validate(data)["endpoint"])
        except (ValueError, TypeError, KeyError):
            raise HTTPException(400, "Invalid subscription")
        return {"removed": True}

    return router
