# Reduce ASIN Dependency - Implementation Plan

**Date:** 2026-01-19  
**Goal:** Make the system less dependent on Audible ASINs, add Google Books as a search source

---

## Current Architecture Problems

### 1. ASIN as Primary Key
```python
class Audiobook(BaseSQLModel, table=True):
    asin: str = Field(primary_key=True)  # ← Single point of failure
```

**Problem:** If a book doesn't have an ASIN (or Audible search fails), we can't add it.

### 2. Audible-Only Search
```python
async def list_audible_books(query: str):
    # Only searches Audible API
```

**Problem:** Missing books that Audible search doesn't return (like "bart ehrman" issue).

### 3. Prowlarr Doesn't Use ASIN
```python
async def query_prowlarr(book: Audiobook):
    query = book.title  # ← Only uses title!
```

**Insight:** ASINs aren't needed for downloading, just for identification.

---

## Proposed Architecture

### Phase 1: Add Alternative Identifiers (Non-Breaking) ✅

**Add optional fields to Audiobook model:**
```python
class Audiobook(BaseSQLModel, table=True):
    asin: str = Field(primary_key=True)  # Keep for now
    isbn_10: str | None = None           # ← NEW
    isbn_13: str | None = None           # ← NEW
    google_books_id: str | None = None   # ← NEW
    source: str = "audible"              # ← NEW (audible/google/manual)
```

**Benefits:**
- Non-breaking change
- Allows tracking books from multiple sources
- Can cross-reference between systems

### Phase 2: Add Google Books Search Integration ✅

**New function in `book_search.py`:**
```python
async def search_google_books(
    query: str,
    max_results: int = 30
) -> list[dict]:
    """Search Google Books API for audiobooks"""
    # https://www.googleapis.com/books/v1/volumes?q={query}
    # Filter for books with audiobook availability
```

**Hybrid search strategy:**
```python
async def hybrid_search(query: str) -> list[Audiobook]:
    results = []
    
    # 1. Audible search (current)
    audible_books = await list_audible_books(query)
    results.extend(audible_books)
    
    # 2. Google Books fallback (if < 10 results)
    if len(results) < 10:
        google_books = await search_google_books(query)
        
        for gb_book in google_books:
            # Try ISBN as potential ASIN
            for isbn in gb_book.get('isbns', []):
                asin = isbn.replace('-', '')
                
                # Check if this ISBN exists on Audible
                audible_book = await try_get_audible_book(asin)
                if audible_book:
                    audible_book.isbn_10 = isbn
                    audible_book.source = "google_books_hybrid"
                    results.append(audible_book)
                    break
            else:
                # No ASIN found, create book from Google Books data
                book = create_book_from_google_data(gb_book)
                book.source = "google_books"
                results.append(book)
    
    return deduplicate(results)
```

### Phase 3: Support Non-ASIN Books in Database ⚠️

**Problem:** Can't insert books without ASINs (primary key constraint)

**Solution A - Use ISBN as fallback ASIN:**
```python
# When adding Google Books results
if not asin:
    asin = isbn_10 or isbn_13 or f"GB{google_books_id}"
```

**Solution B - Change primary key to generated ID:**
```python
class Audiobook(BaseSQLModel, table=True):
    id: int = Field(primary_key=True)    # ← NEW
    asin: str | None = None              # ← Optional
    isbn_10: str | None = None
    isbn_13: str | None = None
    # Unique constraint on any identifier
```
⚠️ **This requires database migration!**

### Phase 4: Update Prowlarr Query (Enhancement)

**Current:**
```python
query = book.title
```

**Enhanced:**
```python
# Build better search query
query_parts = [book.title]
if book.authors:
    query_parts.append(book.authors[0])
if book.asin and is_isbn_format(book.asin):
    query_parts.append(book.asin)  # ISBNs often in release names

query = " ".join(query_parts)
```

**Example:**
- Old: `"Heaven and Hell"`
- New: `"Heaven and Hell Bart Ehrman 1797101021"`

This helps Prowlarr find better matches!

---

## Implementation Order

### Stage 1: Non-Breaking Additions (START HERE)
1. ✅ Add ISBN/Google fields to Audiobook model
2. ✅ Create database migration
3. ✅ Add Google Books API client
4. ✅ Implement hybrid search function
5. ✅ Update search router to use hybrid search
6. ✅ Test with "bart ehrman" query

### Stage 2: Improvements
7. ⬜ Enhance Prowlarr query with author + ISBN
8. ⬜ Add UI indicator for book source (Audible/Google)
9. ⬜ Add fallback chain: Audible → Google → Manual entry

### Stage 3: Major Refactor (OPTIONAL)
10. ⬜ Replace ASIN primary key with generated ID
11. ⬜ Support multiple identifier types per book
12. ⬜ Add identifier resolution service

---

## Stage 1 Implementation Details

### 1. Database Migration

**File:** `alembic/versions/XXXX_add_isbn_fields.py`
```python
def upgrade():
    op.add_column('audiobook', sa.Column('isbn_10', sa.String(), nullable=True))
    op.add_column('audiobook', sa.Column('isbn_13', sa.String(), nullable=True))
    op.add_column('audiobook', sa.Column('google_books_id', sa.String(), nullable=True))
    op.add_column('audiobook', sa.Column('source', sa.String(), nullable=False, server_default='audible'))
    
    # Create indexes for ISBN lookups
    op.create_index('ix_audiobook_isbn_10', 'audiobook', ['isbn_10'])
    op.create_index('ix_audiobook_isbn_13', 'audiobook', ['isbn_13'])
```

### 2. Update Audiobook Model

**File:** `app/internal/models.py`
```python
class Audiobook(BaseSQLModel, table=True):
    asin: str = Field(primary_key=True)
    title: str
    subtitle: str | None
    authors: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    narrators: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    cover_image: str | None
    release_date: datetime
    runtime_length_min: int
    
    # NEW: Alternative identifiers
    isbn_10: str | None = Field(default=None, index=True)
    isbn_13: str | None = Field(default=None, index=True)
    google_books_id: str | None = Field(default=None)
    source: str = Field(default="audible")  # audible | google_books | hybrid | manual
    
    updated_at: datetime = Field(...)
    downloaded: bool = False
```

### 3. Google Books API Client

**File:** `app/internal/google_books.py` (NEW)
```python
from aiohttp import ClientSession
from typing import List, Dict, Any

GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1/volumes"

async def search_google_books(
    session: ClientSession,
    query: str,
    max_results: int = 30
) -> List[Dict[str, Any]]:
    """Search Google Books API"""
    params = {
        "q": query,
        "maxResults": max_results,
        "printType": "books",
    }
    
    async with session.get(GOOGLE_BOOKS_API, params=params) as resp:
        if not resp.ok:
            return []
        data = await resp.json()
        return data.get("items", [])

def extract_isbns(volume_info: Dict) -> tuple[str | None, str | None]:
    """Extract ISBN-10 and ISBN-13 from Google Books volume"""
    isbn_10 = None
    isbn_13 = None
    
    for identifier in volume_info.get("industryIdentifiers", []):
        if identifier["type"] == "ISBN_10":
            isbn_10 = identifier["identifier"]
        elif identifier["type"] == "ISBN_13":
            isbn_13 = identifier["identifier"]
    
    return isbn_10, isbn_13
```

### 4. Hybrid Search Implementation

**File:** `app/internal/book_search.py`

Add after existing `list_audible_books()`:
```python
async def hybrid_search(
    session: Session,
    client_session: ClientSession,
    query: str,
    region: str = "us",
    num_results: int = 30,
) -> list[Audiobook]:
    """
    Hybrid search using both Audible and Google Books.
    
    Strategy:
    1. Search Audible API first (audiobook-specific)
    2. If < 10 results, query Google Books
    3. For each Google Books result, try ISBN as ASIN
    4. If ASIN exists, fetch from Audible with ISBN enrichment
    5. Return combined deduplicated results
    """
    from app.internal.google_books import search_google_books, extract_isbns
    
    # Step 1: Audible search (existing)
    audible_results = await list_audible_books(
        session, client_session, query, region, num_results
    )
    
    # If we have enough results, return
    if len(audible_results) >= 10:
        return audible_results
    
    # Step 2: Google Books fallback
    logger.info("Audible returned few results, trying Google Books", count=len(audible_results))
    
    google_books = await search_google_books(client_session, query, max_results=20)
    
    found_via_google = []
    for item in google_books:
        volume_info = item.get("volumeInfo", {})
        isbn_10, isbn_13 = extract_isbns(volume_info)
        
        if not isbn_10 and not isbn_13:
            continue
        
        # Try ISBN-10 as ASIN first (10-digit format common for older books)
        potential_asin = isbn_10 or isbn_13
        if potential_asin:
            potential_asin = potential_asin.replace("-", "")
            
            # Try to fetch from Audible using this ISBN as ASIN
            try:
                book = await get_book_by_asin(client_session, potential_asin, region)
                if book:
                    # Enrich with ISBN data
                    book.isbn_10 = isbn_10
                    book.isbn_13 = isbn_13
                    book.google_books_id = item["id"]
                    book.source = "google_books_hybrid"
                    found_via_google.append(book)
                    logger.info(
                        "Found book via Google Books ISBN",
                        title=book.title,
                        isbn=potential_asin
                    )
            except Exception as e:
                logger.debug("ISBN not found on Audible", isbn=potential_asin, error=str(e))
    
    # Combine results
    all_results = audible_results + found_via_google
    
    # Deduplicate by ASIN
    seen_asins = set()
    unique_results = []
    for book in all_results:
        if book.asin not in seen_asins:
            seen_asins.add(book.asin)
            unique_results.append(book)
    
    return unique_results[:num_results]
```

### 5. Update Router

**File:** `app/routers/search.py`

Change the search endpoint:
```python
@router.get("/audiobooks/search")
async def search_audiobooks(
    query: str,
    region: str = "us",
    num_results: int = 30,
    use_hybrid: bool = True,  # ← NEW parameter
    session: Session = Depends(get_session),
    client_session: ClientSession = Depends(get_client_session),
) -> list[Audiobook]:
    if use_hybrid:
        return await hybrid_search(
            session, client_session, query, region, num_results
        )
    else:
        return await list_audible_books(
            session, client_session, query, region, num_results
        )
```

---

## Testing Plan

### Test Case 1: The Original Bug
```bash
# Should now find "Heaven and Hell: A History of the Afterlife"
curl "http://localhost:8000/audiobooks/search?query=bart+ehrman&use_hybrid=true"
```

**Expected:** Book with ISBN 1797101021 appears in results

### Test Case 2: Audible-Only Books
```bash
curl "http://localhost:8000/audiobooks/search?query=harry+potter"
```

**Expected:** Works normally (all from Audible)

### Test Case 3: Hybrid Results
```bash
curl "http://localhost:8000/audiobooks/search?query=obscure+author"
```

**Expected:** Shows both Audible + Google Books results

---

## Risks & Mitigations

### Risk 1: Google Books Rate Limiting
**Mitigation:** 
- Cache Google Books results (7 days like Audible)
- Only query if Audible returns < 10 results
- Use API key if rate limits hit

### Risk 2: ISBNs That Aren't ASINs
**Mitigation:**
- Try fetch, gracefully handle 404
- Don't add to results if not found

### Risk 3: Database Migration Failure
**Mitigation:**
- Test migration on copy of production DB first
- Nullable columns = non-breaking
- Can rollback easily

---

## Success Metrics

1. ✅ "bart ehrman" query returns "Heaven and Hell" book
2. ✅ No regression in existing Audible search
3. ✅ 10-20% more results for queries with < 10 Audible matches
4. ✅ Database migration completes without errors

---

## Future Enhancements

- **OpenLibrary integration** (similar to Google Books)
- **Manual book entry** (for books not in any API)
- **ISBN resolver service** (aggregate multiple sources)
- **Alternative audiobook platforms** (Libro.fm, Scribd, etc.)
- **Generated IDs instead of ASIN primary key** (major refactor)

---

## Ready to Implement?

**Start with Stage 1, Steps 1-6** - this will solve your immediate problem while keeping the changes minimal and non-breaking.
