# Can We Be Even LESS Reliant on ASINs?

**Date:** 2026-01-19  
**Current Status:** ASIN is primary key, but only used for identification

---

## Current ASIN Usage Analysis

### Where ASINs ARE Used:
1. **Database primary key** - `audiobook.asin` 
2. **Foreign key references** - `audiobookrequest.asin`
3. **Book identification** - Deduplication, uniqueness
4. **Notifications** - Referencing which book was downloaded

### Where ASINs Are NOT Used:
1. ❌ **Prowlarr search** - Uses `title` only
2. ❌ **Download matching** - Uses `title + author`
3. ❌ **Torrent identification** - Uses file analysis

**Key insight:** ASINs are ONLY for identification, not functionality!

---

## What Would "Less ASIN Reliant" Look Like?

### Option 1: Generated Primary Keys (Recommended)

**Replace ASIN as primary key with auto-generated ID:**

```python
class Audiobook(BaseSQLModel, table=True):
    id: int = Field(primary_key=True)  # ← NEW
    
    # All identifiers become optional
    asin: str | None = Field(default=None, index=True, unique=True)
    isbn_10: str | None = Field(default=None, index=True)
    isbn_13: str | None = Field(default=None, index=True)
    google_books_id: str | None = Field(default=None, index=True)
    
    # Core fields (always required)
    title: str
    authors: list[str]
    # ...
```

**Benefits:**
- ✅ Can add books from ANY source (Google Books, OpenLibrary, manual entry)
- ✅ Don't need ASIN to create a book
- ✅ Multiple identifiers for cross-referencing
- ✅ Support books that don't exist on Audible

**Challenges:**
- ⚠️ Major database migration (change primary key)
- ⚠️ Update all foreign keys
- ⚠️ Need new deduplication logic

---

### Option 2: Composite Natural Key

**Use title + author as primary identifier:**

```python
class Audiobook(BaseSQLModel, table=True):
    # Composite primary key
    title: str = Field(primary_key=True)
    author: str = Field(primary_key=True)  # First author
    
    # Identifiers become metadata
    asin: str | None
    isbn_10: str | None
    # ...
```

**Benefits:**
- ✅ Works for any book from any source
- ✅ Human-readable primary key

**Challenges:**
- ❌ Duplicates if title/author vary slightly
- ❌ What if author name changes (Bart D. Ehrman vs Bart Ehrman)?
- ❌ Multi-author books?

---

### Option 3: Universal Book Identifier

**Use ISBN-13 as primary key (most universal):**

```python
class Audiobook(BaseSQLModel, table=True):
    isbn_13: str = Field(primary_key=True)  # ← Most books have this
    
    # Fallback identifiers
    asin: str | None = None
    isbn_10: str | None = None
    synthetic_id: str | None = None  # For books without ISBN
    # ...
```

**Benefits:**
- ✅ ISBN-13 is more universal than ASIN
- ✅ Works across platforms (Audible, Google Books, OpenLibrary)
- ✅ Industry standard

**Challenges:**
- ❌ Some audiobooks don't have ISBNs
- ❌ Old books only have ISBN-10
- ❌ Still need fallback for non-ISBN books

---

## Recommended Approach: Generated IDs + Identifier Resolution

### Step 1: Change Primary Key to ID

```python
class Audiobook(BaseSQLModel, table=True):
    id: int = Field(primary_key=True)
    
    # ALL identifiers become optional
    asin: str | None = Field(default=None, index=True)
    isbn_10: str | None = Field(default=None, index=True)
    isbn_13: str | None = Field(default=None, index=True)
    google_books_id: str | None = Field(default=None, index=True)
    openlibrary_id: str | None = Field(default=None, index=True)
    
    # Require at least ONE identifier
    title: str  # Always required
    authors: list[str]  # Always required
    
    # Add constraint: at least one identifier must be present
    def __post_init__(self):
        if not any([self.asin, self.isbn_10, self.isbn_13, 
                   self.google_books_id, self.openlibrary_id]):
            raise ValueError("At least one identifier required")
```

### Step 2: Identifier Resolution Service

```python
class BookIdentifier:
    """Resolves books across multiple identifier types"""
    
    async def find_book(
        self,
        asin: str | None = None,
        isbn_10: str | None = None,
        isbn_13: str | None = None,
        title: str | None = None,
        author: str | None = None,
    ) -> Audiobook | None:
        """Find book by any available identifier"""
        
        # Try exact matches first
        if asin:
            book = session.query(Audiobook).filter_by(asin=asin).first()
            if book:
                return book
        
        if isbn_10:
            book = session.query(Audiobook).filter_by(isbn_10=isbn_10).first()
            if book:
                return book
        
        # Try fuzzy match on title + author
        if title and author:
            books = session.query(Audiobook).filter(
                Audiobook.title.ilike(f"%{title}%"),
                Audiobook.authors.contains(author)
            ).all()
            
            if len(books) == 1:
                return books[0]
        
        return None
    
    async def merge_books(self, book1: Audiobook, book2: Audiobook) -> Audiobook:
        """Merge duplicate books, combining identifiers"""
        # Keep book with more metadata
        primary = book1 if len(book1.dict()) > len(book2.dict()) else book2
        secondary = book2 if primary == book1 else book1
        
        # Merge identifiers
        primary.asin = primary.asin or secondary.asin
        primary.isbn_10 = primary.isbn_10 or secondary.isbn_10
        primary.isbn_13 = primary.isbn_13 or secondary.isbn_13
        
        # Update foreign keys to point to primary
        session.query(AudiobookRequest).filter_by(
            audiobook_id=secondary.id
        ).update({"audiobook_id": primary.id})
        
        # Delete secondary
        session.delete(secondary)
        session.commit()
        
        return primary
```

### Step 3: Multi-Source Search

```python
async def universal_search(
    query: str,
    sources: list[str] = ["audible", "google_books", "openlibrary"]
) -> list[Audiobook]:
    """Search across multiple sources and deduplicate"""
    
    all_books = []
    
    if "audible" in sources:
        audible_books = await search_audible(query)
        all_books.extend(audible_books)
    
    if "google_books" in sources:
        google_books = await search_google_books(query)
        for gb in google_books:
            book = await create_or_find_book_from_google(gb)
            all_books.append(book)
    
    if "openlibrary" in sources:
        ol_books = await search_openlibrary(query)
        for ol in ol_books:
            book = await create_or_find_book_from_openlibrary(ol)
            all_books.append(book)
    
    # Deduplicate by identifier matching
    unique_books = deduplicate_by_identifiers(all_books)
    
    return unique_books


def deduplicate_by_identifiers(books: list[Audiobook]) -> list[Audiobook]:
    """Smart deduplication using identifier matching"""
    seen = {}
    unique = []
    
    for book in books:
        # Generate signature from all identifiers
        signature = (
            book.asin,
            book.isbn_10,
            book.isbn_13,
            book.google_books_id,
        )
        
        # Check if we've seen any of these identifiers
        found = False
        for identifier in signature:
            if identifier and identifier in seen:
                found = True
                break
        
        if not found:
            unique.append(book)
            # Record all identifiers
            for identifier in signature:
                if identifier:
                    seen[identifier] = book
    
    return unique
```

---

## Implementation Plan

### Phase 1: Non-Breaking (Do This First)

**Already done:**
- ✅ Added ISBN/Google Books ID tracking
- ✅ Hybrid search with multiple sources

**Next steps:**
1. Add OpenLibrary integration (similar to Google Books)
2. Add manual book entry UI (for books not in any API)
3. Add identifier resolution service

### Phase 2: Breaking Changes (Major Refactor)

**Change primary key to generated ID:**

```sql
-- Migration pseudocode
ALTER TABLE audiobook ADD COLUMN id INTEGER PRIMARY KEY AUTOINCREMENT;
ALTER TABLE audiobook ADD UNIQUE INDEX ON asin;
ALTER TABLE audiobookrequest RENAME COLUMN asin TO audiobook_id;
ALTER TABLE audiobookrequest ADD FOREIGN KEY audiobook_id REFERENCES audiobook(id);
```

**Update all queries:**
```python
# Before
book = session.query(Audiobook).filter_by(asin=asin).first()

# After
book = session.query(Audiobook).filter_by(id=book_id).first()
# OR
book = session.query(Audiobook).filter_by(asin=asin).first()  # Still works!
```

---

## What This Enables

### 1. Manual Book Entry
```python
# User can add ANY audiobook, even if not on Audible
book = Audiobook(
    title="Some Obscure Audiobook",
    authors=["Unknown Author"],
    narrators=["Unknown Narrator"],
    runtime_length_min=300,
    # No ASIN needed!
)
```

### 2. Multi-Platform Support
```python
# Book from Libro.fm (DRM-free audiobooks)
libro_book = Audiobook(
    title="Freedom Book",
    authors=["Author"],
    isbn_13="9781234567890",  # Has ISBN but no ASIN
    source="libro_fm",
)

# Book from Scribd
scribd_book = Audiobook(
    title="Another Book",
    authors=["Author"],
    scribd_id="SCRIB123",  # Custom identifier
    source="scribd",
)
```

### 3. Better Deduplication
```python
# Same book from different sources gets merged
audible_book = Audiobook(asin="B1234", title="Book")
google_book = Audiobook(isbn_10="1234567890", title="Book")

# System recognizes they're the same via title matching
# Merges into one record with both identifiers
merged = Audiobook(
    asin="B1234",
    isbn_10="1234567890",
    title="Book",
    source="multiple",
)
```

---

## Challenges & Solutions

### Challenge 1: Prowlarr Requires Title
**Solution:** Title is always required, so this still works.

### Challenge 2: How to Handle Duplicates?
**Solution:** Identifier resolution service + fuzzy title matching.

### Challenge 3: Migration Complexity
**Solution:** Phased approach:
1. Add ID column (non-breaking)
2. Populate IDs for all existing records
3. Change foreign keys to use ID
4. Make ASIN optional

### Challenge 4: UI/API Changes
**Solution:** Support both:
```python
# Old API (still works)
GET /audiobooks/B1234  # ASIN

# New API
GET /audiobooks/12345  # ID
GET /audiobooks?asin=B1234  # Query by ASIN
GET /audiobooks?isbn=1234567890  # Query by ISBN
```

---

## Effort Estimate

| Phase | Effort | Risk | Value |
|-------|--------|------|-------|
| Add OpenLibrary | 2 hours | Low | Medium |
| Manual entry UI | 4 hours | Low | Medium |
| Identifier resolution | 8 hours | Medium | High |
| Change primary key | 16 hours | High | High |
| Multi-platform support | 40 hours | High | Very High |

---

## Recommendation

### Short Term (This Week)
1. **Add OpenLibrary integration** (similar to Google Books)
2. **Add manual book entry form** (for books not in APIs)
3. Keep ASIN as primary key (for now)

### Medium Term (This Month)
1. **Implement identifier resolution service**
2. **Add fuzzy matching for deduplication**
3. **Test with production data**

### Long Term (This Quarter)
1. **Migrate to generated IDs** (major refactor)
2. **Add multi-platform support** (Libro.fm, Scribd, etc.)
3. **Build identifier mapping database**

---

## Example: Fully ASIN-Independent System

```python
# User searches for "bart ehrman heaven hell"
results = await universal_search("bart ehrman heaven hell")

# Results from multiple sources:
[
    Audiobook(
        id=1,
        asin="1797101021",  # From Audible
        title="Heaven and Hell: A History of the Afterlife",
        source="audible"
    ),
    Audiobook(
        id=2,
        isbn_13="9781786077219",  # From Google Books
        title="Heaven and Hell: A History of the Afterlife",
        source="google_books"
    ),
    Audiobook(
        id=3,
        openlibrary_id="OL123456M",  # From OpenLibrary
        title="Heaven and Hell",
        source="openlibrary"
    ),
]

# System merges duplicates
merged = merge_duplicates(results)

# Final result: ONE book with ALL identifiers
result = Audiobook(
    id=1,
    asin="1797101021",
    isbn_13="9781786077219",
    openlibrary_id="OL123456M",
    title="Heaven and Hell: A History of the Afterlife",
    source="multiple",
)

# User requests it
# Prowlarr searches by title: "Heaven and Hell Bart Ehrman"
# Downloads work regardless of which identifier we have
```

---

## Bottom Line

**Yes, you can be MUCH less reliant on ASINs** by:

1. ✅ **Short term:** Add more data sources (OpenLibrary, manual entry)
2. ✅ **Medium term:** Build identifier resolution service
3. ✅ **Long term:** Replace ASIN primary key with generated IDs

**The effort is significant** (40-80 hours total), but would make the system:
- Platform-agnostic
- More robust against API changes
- Able to handle ANY audiobook from ANY source

Want me to start with OpenLibrary integration?
