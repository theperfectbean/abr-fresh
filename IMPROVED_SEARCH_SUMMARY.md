# Improved Audible Search - Fresh Start

**Location:** `/home/gary/abr-fresh` (cloned from `markbeep/AudioBookRequest`)

## Problem
Original ABR Audible search is weak - queries like "bart ehrman" don't return all available books.
Example: "ehrman heaven" finds books that "bart ehrman" misses.

## Solution
**Added multi-query search expansion** to `app/internal/book_search.py`

### What Changed

#### 1. New Function: `_expand_search_queries(query: str) -> list[str]`
Generates intelligent query variants:
- `"bart ehrman"` → `["bart ehrman", "ehrman", "bart"]`
- `"heaven and hell"` → `["heaven and hell", "heaven hell", "hell"]`
- Tries: original + last word + first word + meaningful words (removes articles)

#### 2. Enhanced `list_audible_books()` Function
- **Before:** Single query to Audible API
- **After:** 
  1. Expands query into 3-4 variants
  2. Tries each variant sequentially
  3. Deduplicates results (unique ASINs only)
  4. Returns combined results in order of discovery
  5. Logs each variant's contribution

### Example Flow

**User searches:** `"bart ehrman"`
1. Expand to: `["bart ehrman", "ehrman", "bart"]`
2. Query 1: "bart ehrman" → [Book1, Book2, Book3, Book5]
3. Query 2: "ehrman" → [Book1, Book2, Book3, Book4, Book5, Book6] ← **NEW!**
4. Query 3: "bart" → [Book1, Book2, Book3, Book5]
5. Combine (deduplicated): [Book1, Book2, Book3, Book5, **Book4**, **Book6**] ← Found missing books!

### Why This Works
- Audible search can be brittle with full names
- Breaking into components catches partial matches
- Removing articles improves title-based queries
- No Prowlarr needed, no virtual ASINs, no complex ranking
- **Simple, maintainable, solves the actual problem**

### Performance
- Original query still cached (no performance regression)
- Only attempts variants if cache miss
- Results deduplicated (no duplicates in results)
- Logging tracks expansion effectiveness

### Code Stats
- **Lines added:** ~160
- **Files modified:** 1 (`app/internal/book_search.py`)
- **Complexity:** Low (simple list operations, no new dependencies)
- **Breaking changes:** None (backward compatible)

---

## How to Test

```bash
cd /home/gary/abr-fresh

# Install dependencies
uv sync

# Run migrations
just migrate

# Start app
just dev

# Test search:
# Search: "bart ehrman" (should now find all his books)
# Search: "heaven and hell" (should find title variants)
# Search: "ehrman" (should find all Ehrman books)
```

## Next Steps

1. Deploy and test with real queries
2. Monitor logs: look for "Search query expansion" entries to see variants
3. If variants help, consider adding:
   - Caching of expanded queries (optional optimization)
   - Configuration to enable/disable expansion (via env var)
   - A/B test metrics (before/after result count)

## Why NOT Prowlarr?
- Prowlarr solves different problem (torrents)
- This problem is fixable at Audible layer
- Simpler, fewer dependencies, faster
- Maintains original ABR philosophy

## Why NOT complex ranking?
- Audible already ranks by relevance
- Our variants just increase recall
- Combining results by discovery order = good enough
- Keeps code simple & maintainable
