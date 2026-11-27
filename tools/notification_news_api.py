"""Read-only structured news API; explicit host mounting required."""
from fastapi import APIRouter, Depends, HTTPException, Query

def build_news_router(news_store, require_user):
    if not callable(require_user):
        raise ValueError("Authentication required")
    router = APIRouter(prefix="/api/research-news", dependencies=[Depends(require_user)])

    @router.get("")
    def list_news(market: list[str] = Query(default=[]),
                  symbol: list[str] = Query(default=[]),
                  topic: list[str] = Query(default=[]),
                  minimum: str = "low",
                  include_global: bool = True,
                  limit: int = Query(100, ge=1, le=500)):
        if any(len(values)>100 or any(not v.strip() or len(v)>100 for v in values)
               for values in (market,symbol,topic)):
            raise HTTPException(422,"Geçersiz haber filtresi")
        try:
            items = news_store.list(limit=limit, markets=market, symbols=symbol,
                                    topics=topic, minimum=minimum, include_global=include_global)
        except ValueError:
            raise HTTPException(422,"Geçersiz haber filtresi")
        return {"items":items,"count":len(items),"research_only":True,"orders_enabled":False}
    return router
