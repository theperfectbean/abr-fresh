"""Cache metrics and health check endpoints."""

from typing import Annotated

from fastapi import APIRouter, Security
from pydantic import BaseModel

from app.internal.auth.authentication import APIKeyAuth, DetailedUser
from app.internal.book_search import search_cache
from app.internal.cache_monitoring import cache_metrics

router = APIRouter(prefix="/health", tags=["Health"])


class CacheHealthResponse(BaseModel):
    """Cache health and metrics status."""

    cache_size: int
    total_entries: int
    hits: int
    misses: int
    hit_rate: float
    evictions: int
    rehydration_failures: int
    object_deleted_errors: int


@router.get(
    "/cache",
    response_model=CacheHealthResponse,
    dependencies=[Security(APIKeyAuth(), scopes=["admin"])],
)
async def cache_health(
    _: Annotated[DetailedUser, Security(APIKeyAuth())],
):
    """
    Get cache health metrics (admin only).

    Returns current cache state and performance metrics.
    """
    return CacheHealthResponse(
        cache_size=len(search_cache),
        total_entries=sum(len(entry.value) for entry in search_cache.values()),
        hits=cache_metrics.hits,
        misses=cache_metrics.misses,
        hit_rate=cache_metrics.hit_rate,
        evictions=cache_metrics.evictions,
        rehydration_failures=cache_metrics.rehydration_failures,
        object_deleted_errors=cache_metrics.object_deleted_errors,
    )
