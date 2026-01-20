# Caching Refactor: DTO-Based Architecture

## Overview

This document describes the caching architecture refactor that moves the AudioBookRequest application from storing ORM objects in cache to storing lightweight Data Transfer Objects (DTOs). This eliminates `ObjectDeletedError` exceptions and provides a foundation for future optimizations.

## Architecture

### Previous Architecture (Problems)

```python
# Old: Caching ORM objects directly
search_cache: dict[CacheQuery, CacheResult[list[Audiobook]]] = {}

# Problem: ORM objects can be deleted from DB while cached
cache_result = search_cache.get(cache_key)
for book in cache_result.value:
    # Exception if book was deleted from DB!
    try:
        session.add(book)
        session.refresh(book)
    except ObjectDeletedError:
        # Cache is now stale/invalid
        del search_cache[cache_key]
```

### New Architecture (Solution)

```python
# New: Cache DTOs instead of ORM objects
search_cache: dict[CacheQuery, CacheResult[list[SearchResultDTO]]] = {}

# Solution: Rehydrate fresh ORM objects from DB using cached ASINs
cache_result = search_cache.get(cache_key)
if cache_result:
    cached_dtos = cache_result.value
    # Extract ASINs and fetch fresh ORM objects
    asins = {dto.asin for dto in cached_dtos if dto.asin}
    fresh_books = get_existing_books(session, asins)
    # No ObjectDeletedError - books are fresh from DB
```

## Components

### 1. Data Transfer Objects (DTOs)

**File**: `app/internal/dtos.py`

Lightweight data containers that decouple search results from ORM:

- **SearchResultDTO**: Core search result format
  - Fields: asin, title, authors, narrators, cover_image, runtime_length_min, ISBN fields, source
  - Computed properties: `runtime_length_hrs`, `request_count`, `user_has_requested`
  - Factory methods: `from_audiobook_orm()`, `from_audible_api()`

- **AudiobookWishlistDTO**: Wishlist-specific format
  - Extends SearchResultDTO with wishlist metadata
  - Includes request counts and usernames

### 2. Repository Layer

**File**: `app/internal/repositories.py`

Data access abstraction with batch query capabilities:

- **AudiobookRepository**
  - `get_by_asin(asin)`: Single lookup
  - `get_by_id(id)`: Single lookup
  - `get_many_by_asins(asins)`: Batch fetch with dict return
  - `get_many_by_ids(ids)`: Batch fetch preserving order

- **AudiobookRequestRepository**
  - `count_by_audiobook_id(id)`: Single count
  - `count_requests_by_audiobook_ids(ids)`: Batch count (avoids N+1)
  - `get_all_for_audiobook(id)`: All requests for a book
  - `get_all_for_user(username)`: All requests by user
  - `has_user_requested_audiobook(id, username)`: Existence check

### 3. Cache Layer

**File**: `app/internal/book_search.py`

The core search caching with DTO storage:

- **search_cache**: Now stores `list[SearchResultDTO]`
- **Cache Loading**: Rehydrates DTOs to fresh ORM objects
- **Cache Invalidation**:
  - `invalidate_book_cache(asin)`: Remove entries for specific book
  - `invalidate_all_search_cache()`: Clear all caches

### 4. Monitoring & Metrics

**File**: `app/internal/cache_monitoring.py`

Performance tracking:

- **CacheMetrics** class tracks:
  - `hits`: Cache hits
  - `misses`: Cache misses
  - `hit_rate`: Percentage hit rate
  - `evictions`: Entries evicted by TTL
  - `rehydration_failures`: Failed rehydrations
  - `object_deleted_errors`: ObjectDeletedError count (should be 0)

- **Global instance**: `cache_metrics` - automatically incremented during cache operations

### 5. Health Endpoints

**File**: `app/routers/api/health.py`

New monitoring endpoints:

- `GET /api/health/cache` - Cache metrics and health (admin only)
  - Returns: cache size, entry count, hit rate, error counts

### 6. Configuration

**File**: `app/internal/env_settings.py`

New setting:

- `ABR_APP__ENABLE_DTO_CACHE` (default: `true`)
  - Feature flag to disable DTO cache if needed
  - Allows gradual rollout and easy fallback

## Integration Points

### Search Pipeline

1. **Audible API Search** → `list_audible_books()`
   - Searches Audible API
   - Checks local DB for existing books
   - Fetches missing books from Audible
   - Converts to DTOs before caching
   - Returns fresh ORM objects

2. **Hybrid Search** → `hybrid_search()`
   - Combines Audible + Google Books results
   - Returns fresh ORM objects
   - Cached independently via `list_audible_books()`

3. **API Endpoint** → `/api/search`
   - Calls search functions (returns ORM objects)
   - Uses `AudiobookRequestRepository` for batch loading
   - Returns serialized results

### Wishlist Operations

- Uses existing `get_wishlist_results()` with `selectinload`
- Efficient batch loading of requests per book
- No changes required (already optimized)

## Cache Flow

### Cache Hit (Rehydration)

```
1. Check if CacheQuery key exists
2. If exists and not expired:
   a. Record hit in metrics
   b. Extract ASINs from cached DTOs
   c. Query fresh ORM objects by ASIN
   d. Return fresh books (no deletion risk)
3. If expired or missing, proceed to fetch
```

### Cache Miss (Storage)

```
1. Fetch search results from Audible API
2. Store in DB
3. Convert ORM objects to DTOs
4. Store DTOs in cache with timestamp
5. Record miss + cleanup old entries
6. Return ORM objects
```

## Monitoring & Debugging

### Cache Metrics

```bash
# Check cache health (admin only)
curl -H "Authorization: Bearer YOUR_API_KEY" \
  http://localhost:9000/api/health/cache

# Response:
{
  "cache_size": 42,
  "total_entries": 156,
  "hits": 1245,
  "misses": 312,
  "hit_rate": 79.9,
  "evictions": 8,
  "rehydration_failures": 0,
  "object_deleted_errors": 0
}
```

### Logging

Structured logs track cache operations:

```
# Cache hit
"Using cached search result from DTO cache", query=..., result_count=...

# Cache miss (new search)
"Multi-query search complete", unique_asins_found=..., total_results=...

# Errors
"Cached search result contained invalid book, refetching", error=...
"ObjectDeletedError" - Should never happen with DTO cache!
```

### Metrics Summary

```python
from app.internal.cache_monitoring import cache_metrics

# View metrics
cache_metrics.log_summary()
# Output: Cache metrics summary, hits=..., misses=..., hit_rate=...%

# Reset metrics (useful for testing/benchmarking)
cache_metrics.reset()
```

## Performance Characteristics

### Before (ORM Caching)

```
Cache Hit: Session rehydration + relationship access (N+1 risk)
Cache Miss: Full search + fetch + ORM storage
Risk: ObjectDeletedError when books deleted from DB
```

### After (DTO Caching)

```
Cache Hit: Single batch query for fresh ORM objects (O(1) query)
Cache Miss: Full search + fetch + DTO conversion
Benefit: No ObjectDeletedError, fresh data, batch queries
```

## Migration Guide

### For Operators

1. **Enable the feature flag** (or verify it's enabled):
   ```bash
   ABR_APP__ENABLE_DTO_CACHE=true
   ```

2. **Monitor cache health**:
   ```bash
   # Check cache metrics endpoint
   curl http://localhost:9000/api/health/cache
   
   # Expected: object_deleted_errors = 0
   ```

3. **Check logs** for any issues:
   ```bash
   grep "object_deleted_error\|rehydration_failure" logs/
   ```

4. **If issues arise**, disable with:
   ```bash
   ABR_APP__ENABLE_DTO_CACHE=false
   ```

### For Developers

1. **Use DTOs for cache storage**:
   ```python
   # Good
   dtos = [SearchResultDTO.from_audiobook_orm(book) for book in books]
   search_cache[key] = CacheResult(value=dtos, timestamp=time.time())
   
   # Bad (old way)
   search_cache[key] = CacheResult(value=books, timestamp=time.time())
   ```

2. **Use repositories for batch queries**:
   ```python
   # Good
   request_repo = AudiobookRequestRepository(session)
   counts = request_repo.count_requests_by_audiobook_ids(book_ids)
   
   # Bad (N+1)
   for book in books:
       count = len(book.requests)  # Loads relationship for each book
   ```

3. **Invalidate cache when needed**:
   ```python
   # After creating/deleting requests
   from app.internal.book_search import invalidate_book_cache
   
   invalidate_book_cache(asin)
   ```

## Testing Checklist

### Functional Tests

- [ ] Search returns correct results
- [ ] Cached searches return same results
- [ ] Cache invalidation works (delete request, search again)
- [ ] Hybrid search (Audible + Google Books) works
- [ ] Pagination works correctly
- [ ] Wishlist loads quickly (batch loading)

### Performance Tests

- [ ] First search: ~200-500ms (API calls)
- [ ] Cached search: ~10-50ms (DB batch query)
- [ ] Hit rate: >70% with typical usage
- [ ] Memory: Cache stays bounded

### Error Handling

- [ ] No `ObjectDeletedError` in logs
- [ ] Rehydration failures: 0
- [ ] Graceful fallback on error
- [ ] Proper logging of failures

### Metrics

- [ ] Cache health endpoint works
- [ ] Metrics track correctly
- [ ] Hit rate reasonable (~70-80%)
- [ ] No slow queries (check DB logs)

## Troubleshooting

### Cache Hit Rate Too Low

**Symptom**: Cache hit rate <50%

**Causes**:
- Users searching for unique queries each time
- Cache TTL too short
- Cache cleared frequently

**Solution**:
- Normal in development/testing
- Increase REFETCH_TTL if needed
- Check cache invalidation logic

### Memory Usage High

**Symptom**: Cache grows unbounded

**Causes**:
- Cleanup not running
- No TTL expiration

**Solution**:
- Cleanup runs on startup via `clear_old_book_caches()`
- Consider LRU eviction for bounded cache

### Rehydration Failures

**Symptom**: Cache hit but books not found

**Causes**:
- Books deleted from DB during cache validity
- Session timeout

**Solution**:
- Normal if books were requested and downloaded
- Cache will be refreshed on next miss
- Check `clear_old_book_caches()` is running

### ObjectDeletedError Still Occurring

**Symptom**: `ObjectDeletedError` in logs

**Causes**:
- ORM cache not actually disabled
- Old code path still active

**Solution**:
- Check that `enable_dto_cache=true`
- Verify `search_cache` stores DTOs
- Check logs for which endpoint

## Future Optimizations

1. **Request Count Batching**: Batch load request counts to avoid N+1
2. **Wishlist Optimization**: Similar DTOs for wishlist caching
3. **LRU Eviction**: Bounded cache with LRU replacement
4. **Metrics Export**: Prometheus metrics for monitoring
5. **Cache Warming**: Pre-populate cache on startup
6. **Negative Caching**: Cache "not found" results

## References

- DTOs: `app/internal/dtos.py`
- Repositories: `app/internal/repositories.py`
- Cache Logic: `app/internal/book_search.py`
- Monitoring: `app/internal/cache_monitoring.py`
- Health Endpoints: `app/routers/api/health.py`
- Settings: `app/internal/env_settings.py`

## Rollback

If issues occur:

1. Set `ABR_APP__ENABLE_DTO_CACHE=false`
2. Clear cache: `invalidate_all_search_cache()`
3. Restart application
4. Monitor logs for any errors

No database schema changes, so safe to roll back or re-enable.
