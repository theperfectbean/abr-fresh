# Quick Start: Testing the Search Redesign

## Pre-Deployment Checklist

### 1. Code Verification
```bash
# Check Python syntax
python3 -m py_compile app/internal/sources/*.py app/routers/browse.py

# Check imports work
python3 -c "from app.internal.sources import unified_search, search_author_books; print('✓ Imports OK')"

# Verify database models
python3 -c "from app.internal.models import Audiobook, AudiobookRequest; print('✓ Models OK')"
```

### 2. Apply Database Migrations
```bash
# First, BACKUP YOUR DATABASE
cp app.db app.db.backup

# Run migrations
uv run alembic upgrade heads

# Verify migration success
echo "Check that audiobook and audiobookrequest tables were updated"
```

### 3. Verify Database Changes
```bash
# Open SQLite shell
sqlite3 app.db

# Verify Audiobook table has UUID column
.schema audiobook
# Should show: id TEXT PRIMARY KEY

# Verify ASIN is now nullable and unique
# Should show: asin TEXT UNIQUE

# Verify AudiobookRequest uses audiobook_id
.schema audiobookrequest
# Should show: audiobook_id TEXT (FK to audiobook.id)

# Check data integrity
SELECT COUNT(*) FROM audiobook WHERE id IS NULL;  -- Should be 0
SELECT COUNT(*) FROM audiobookrequest;  -- Should match previous count
.quit
```

---

## Post-Deployment Testing

### Test 1: Author Browse Endpoint

**Goal**: Verify multi-source search works for "Bart Ehrman"

```bash
# Start dev server
just dev

# In another terminal:
curl -s "http://localhost:9000/api/browse/author?author_name=bart%20ehrman&max_results=20" | jq '.[] | {title: .book.title, asin: .book.asin, source: .book.source}' | head -40
```

**Expected Output**:
- Should return 20+ books
- Should include: "Heaven and Hell: A History of the Afterlife"
- Should have mix of sources (audible, google_books, openlibrary)

### Test 2: Author Count Endpoint

```bash
curl -s "http://localhost:9000/api/browse/author/bart%20ehrman/count" | jq
```

**Expected Output**:
```json
{
  "author_name": "bart ehrman",
  "total_books": 50+,
  "available_on_audible": 30+,
  "not_available_on_audible": 20+
}
```

### Test 3: Check ISBN Enrichment

```bash
# Search for a book that should have ISBN data
curl -s "http://localhost:9000/api/browse/author?author_name=bart%20ehrman&page=0" | jq '.[] | select(.book.title | contains("Heaven")) | {title: .book.title, isbn_13: .book.isbn_13, isbn_10: .book.isbn_10, asin: .book.asin}'
```

**Expected Output**: Book should have ISBN and possibly ASIN

### Test 4: Pagination

```bash
# Page 0 (results 0-30)
curl -s "http://localhost:9000/api/browse/author?author_name=bart%20ehrman&page=0" | jq 'length'

# Page 1 (results 30-60)
curl -s "http://localhost:9000/api/browse/author?author_name=bart%20ehrman&page=1" | jq 'length'
```

**Expected Output**: Each page returns up to 30 results

### Test 5: Book Metadata Completeness

```bash
# Get first book and check fields
curl -s "http://localhost:9000/api/browse/author?author_name=bart%20ehrman&max_results=1" | jq '.[0].book | {title, authors, isbn_13, isbn_10, asin, cover_image: (.cover_image | if . then "✓" else null end), source}'
```

**Expected Output**: Most fields should be populated

---

## Troubleshooting

### Migration Errors

**Error**: `Target database is not up to date`
```bash
# Solution: Run upgrade
uv run alembic upgrade heads
```

**Error**: `audiobook_id does not exist`
```bash
# Cause: Migrations not applied yet
# Solution: Run migrations and restart server
```

### Import Errors

**Error**: `No module named 'app.internal.sources'`
```bash
# Cause: Missing __init__.py
# Solution: Verify app/internal/sources/__init__.py exists
ls -la app/internal/sources/__init__.py
```

**Error**: `AttributeError: AudiobookRequest has no field 'asin'`
```bash
# Cause: Trying to use old ASIN-based code before migration
# Solution: Complete all database migrations first
```

### API Errors

**Error**: `422 Unprocessable Entity`
```bash
# Cause: Missing required parameters
# Solution: Check query parameters are URL-encoded
# Example: "bart ehrman" should be "bart%20ehrman"
```

**Error**: `500 Internal Server Error`
```bash
# Check logs for details
# Likely cause: API rate limiting or network error
# Solution: Check Google Books and OpenLibrary API availability
```

---

## What Should Work After Deployment

### ✅ Existing Functionality (Preserved)
- Existing audiobook searches still work
- ASIN-based request creation still works
- Download flow still works
- Wishlist display still works

### ✅ New Functionality (Added)
- Author browse endpoint (`/api/browse/author`)
- Multi-source search (Audible + Google Books + OpenLibrary)
- ISBN-based book matching
- Better metadata for non-Audible books

### ✅ Edge Cases Resolved
- "Heaven and Hell" now appears in search results
- Books without ASIN are searchable
- Comprehensive author bibliography available

---

## Performance Notes

### First Search (Cold Cache)
- Expected time: 2-5 seconds
- Reason: Fetching from 3 external APIs in parallel

### Subsequent Searches (Same Query)
- Expected time: <500ms
- Reason: Results cached in memory (per request)

### Large Result Sets
- 100 books with metadata: ~3-5 MB JSON
- Pagination recommended for UI (30 per page)

---

## Rollback Instructions

If you need to rollback:

```bash
# Backup current database
cp app.db app.db.after-migration

# Downgrade migrations
uv run alembic downgrade -1

# Or restore from backup
cp app.db.backup app.db
```

---

## Next Steps After Verification

1. **Update UI Templates** (if needed)
   - Create HTML template for author browse
   - Add author search to search page

2. **Complete Phase 2** (optional)
   - Transition API routes from ASIN to UUID
   - Update search endpoint to use UUID

3. **Add Smart Lookup** (optional)
   - Create endpoint for ISBN/ASIN direct lookup
   - Enrich existing books with missing ISBNs

4. **Performance Optimization** (optional)
   - Add Redis caching for author searches
   - Implement result pagination in API
   - Add rate limiting for external APIs

---

## Support & Debugging

### Check All Imports
```bash
python3 << 'EOF'
try:
    from app.internal.sources import unified_search, search_author_books
    from app.routers.browse import router
    from app.util.audiobook_lookup import resolve_audiobook_identifier
    print("✓ All imports successful")
except Exception as e:
    print(f"✗ Import error: {e}")
EOF
```

### Test ISBN Conversion
```bash
python3 << 'EOF'
from app.internal.sources.isbn_utils import isbn10_to_isbn13
result = isbn10_to_isbn13("1797101021")
print(f"ISBN-10 1797101021 → ISBN-13 {result}")
EOF
```

### Check Database Connection
```bash
python3 << 'EOF'
from app.util.db import get_session
from sqlmodel import select
from app.internal.models import Audiobook
try:
    session = next(get_session())
    count = len(session.exec(select(Audiobook)).all())
    print(f"✓ Database OK: {count} audiobooks found")
except Exception as e:
    print(f"✗ Database error: {e}")
EOF
```

---

## Success Criteria

✅ **You've successfully deployed if:**

1. Database migrations run without errors
2. `curl http://localhost:9000/api/browse/author?author_name=bart%20ehrman` returns 50+ books
3. "Heaven and Hell: A History of the Afterlife" appears in results
4. Books have ISBN and source information
5. Existing search functionality still works
6. No import or syntax errors in logs

**Congratulations! The search redesign is deployed and working.** 🎉
