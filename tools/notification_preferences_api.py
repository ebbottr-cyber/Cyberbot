"""Explicitly mounted single-operator preferences API."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StrictBool

class Settings(BaseModel):
    quiet_start: str
    quiet_end: str
    muted: list[str]
    push_enabled: StrictBool

def build_preferences_router(preferences, require_user, require_csrf):
    router = APIRouter(prefix="/api/notifications/preferences", dependencies=[Depends(require_user)])

    @router.get("")
    def get_preferences():
        return preferences.load()

    @router.put("", dependencies=[Depends(require_csrf)])
    def update_preferences(settings: Settings):
        try:
            preferences.save(settings.model_dump() if hasattr(settings, "model_dump") else settings.dict())
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="Geçersiz bildirim ayarları")
        return preferences.load()

    return router
