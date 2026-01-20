"""
Cache monitoring and metrics for the DTO-based caching layer.

Tracks cache hits/misses, request counts, and error occurrences.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.util.log import logger


@dataclass
class CacheMetrics:
    """Metrics for cache performance monitoring."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    rehydration_failures: int = 0
    object_deleted_errors: int = 0
    last_cleared: Optional[datetime] = None

    @property
    def total_accesses(self) -> int:
        """Total cache accesses (hits + misses)."""
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        """Cache hit rate as a percentage."""
        if self.total_accesses == 0:
            return 0.0
        return (self.hits / self.total_accesses) * 100

    def record_hit(self) -> None:
        """Record a cache hit."""
        self.hits += 1

    def record_miss(self) -> None:
        """Record a cache miss."""
        self.misses += 1

    def record_eviction(self) -> None:
        """Record a cache eviction."""
        self.evictions += 1

    def record_rehydration_failure(self) -> None:
        """Record a failed rehydration attempt."""
        self.rehydration_failures += 1

    def record_object_deleted_error(self) -> None:
        """Record an ObjectDeletedError occurrence."""
        self.object_deleted_errors += 1

    def log_summary(self) -> None:
        """Log current metrics summary."""
        logger.info(
            "Cache metrics summary",
            total_accesses=self.total_accesses,
            hits=self.hits,
            misses=self.misses,
            hit_rate=f"{self.hit_rate:.1f}%",
            evictions=self.evictions,
            rehydration_failures=self.rehydration_failures,
            object_deleted_errors=self.object_deleted_errors,
        )

    def reset(self) -> None:
        """Reset all metrics to zero."""
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.rehydration_failures = 0
        self.object_deleted_errors = 0
        self.last_cleared = datetime.now()


# Global metrics instance
cache_metrics = CacheMetrics()
