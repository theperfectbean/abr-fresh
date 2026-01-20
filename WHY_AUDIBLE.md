# Why Audible? Could We Use Google Books/OpenLibrary Instead?

**Date:** 2026-01-19

---

## TL;DR

**No, Google Books and OpenLibrary are NOT viable alternatives** because this app is not just a search tool—it's an **audiobook request and download system**.

---

## What This App Actually Does

Based on the codebase, here's the complete workflow:

```
1. User searches Audible → finds audiobook
2. User requests audiobook → creates AudiobookRequest
3. System queries Prowlarr → finds torrents/usenet
4. System downloads audiobook → marks as downloaded
5. Audiobook added to Plex/Audiobookshelf/Jellyfin
```

This is **like Overseerr/Ombi but for audiobooks**.

---

## Why Audible Specifically

### 1. **ASIN = Universal Audiobook Identifier**

```python
class Audiobook(BaseSQLModel, table=True):
    asin: str = Field(primary_key=True)  # ← The key!
    title: str
    authors: list[str]
    # ...
```

The ASIN is used to:
- **Search Prowlarr** for torrents: `"Bart Ehrman 1797101021"`
- **Match releases** across different torrent sites
- **Identify** the exact audiobook edition

Google Books uses **ISBNs** (for print books), not ASINs.
OpenLibrary uses **OLIDs** (their own IDs), not ASINs.

### 2. **Audiobook-Specific Metadata**

```python
class Audiobook:
    narrators: list[str]        # ← Audiobooks have narrators
    runtime_length_min: int     # ← Runtime in minutes
    cover_image: str            # ← Audiobook covers
```

This metadata is critical for:
- Finding the right torrent (narrator + runtime help identify releases)
- Quality ranking (bitrate analysis)
- Display in media servers

**Google Books:** Has print book data, some audiobook listings but limited metadata  
**OpenLibrary:** Primarily print books, minimal audiobook support

### 3. **Prowlarr Integration**

The system uses Prowlarr to search **audiobook-specific torrent sites**:

```python
# From prowlarr.py
async def query_prowlarr(
    book: Audiobook,
    indexer_ids: list[int],
) -> list[ProwlarrSource]:
    # Searches torrents using ASIN + title + author
    search_query = f"{book.title} {book.authors[0]} {book.asin}"
```

Torrent indexers for audiobooks typically:
- Include ASIN in release names
- Use Audible metadata for organization
- Example: `"Heaven and Hell [1797101021] - Bart Ehrman (2020) [MP3 64kbps]"`

---

## What About Google Books / OpenLibrary?

### Google Books API

**What it provides:**
```json
{
  "volumeInfo": {
    "title": "Heaven and Hell",
    "authors": ["Bart D. Ehrman"],
    "industryIdentifiers": [
      {"type": "ISBN_10", "identifier": "1982130318"}
    ]
  }
}
```

**Problems:**
1. ❌ ISBNs are for **print/ebook**, not audiobooks
2. ❌ No narrator information
3. ❌ No runtime data
4. ❌ Audiobook coverage is incomplete
5. ❌ No way to find torrents (ISBN != ASIN)

### OpenLibrary API

**What it provides:**
```json
{
  "key": "/works/OL17935742W",
  "title": "Heaven and Hell",
  "authors": [{"key": "/authors/OL220897A"}],
  "isbn_10": ["1982130318"]
}
```

**Problems:**
1. ❌ Focus on print books
2. ❌ OLIDs are not recognized by torrent sites
3. ❌ Very limited audiobook data
4. ❌ No ASIN mapping
5. ❌ Cannot search Prowlarr with OLIDs

---

## Could We Add Google Books/OpenLibrary as Supplements?

### Possible: Use for ASIN Discovery

**Workflow:**
1. User searches "Bart Ehrman"
2. Query Google Books for books by that author
3. Extract ISBNs from results
4. **Try ISBNs as potential ASINs** (some match!)
5. Check if those ASINs exist on Audible
6. Add to search results

**Example:**
```python
# Google Books returns ISBN: 1797101021
# Try it as an ASIN on Audible
book = await get_book_by_asin(session, "1797101021", region="us")
if book:
    # Success! This ISBN is also an ASIN
    results.append(book)
```

**This could help find books like yours!**

---

## Realistic Hybrid Solution

```python
async def hybrid_search(query: str) -> list[Audiobook]:
    results = []
    
    # 1. Primary: Audible API (fast, audiobook-specific)
    audible_results = await search_audible_api(query)
    results.extend(audible_results)
    
    # 2. Fallback: Google Books ISBN → ASIN
    if len(results) < 10:
        google_books = await search_google_books(query)
        
        for book in google_books:
            # Try each ISBN as a potential ASIN
            for isbn in book.isbns:
                asin = isbn.replace("-", "")  # Clean ISBN
                
                # Check if this ISBN exists as an Audible ASIN
                audiobook = await get_book_by_asin(session, asin, region)
                if audiobook:
                    results.append(audiobook)
    
    # 3. Last resort: Local database
    local_results = search_local_database(query)
    results.extend(local_results)
    
    return deduplicate(results)
```

**Pros:**
- ✅ Legal (using public APIs)
- ✅ May find books Audible search misses
- ✅ Still uses ASINs for downstream (Prowlarr)

**Cons:**
- ❌ Not all audiobook ISBNs match ASINs
- ❌ Extra API calls (slower)
- ❌ Google Books API has rate limits

---

## Why The Current Solution Makes Sense

The codebase is designed around **Audible as the source of truth** because:

1. **ASINs are the standard** for audiobook piracy/sharing
2. **Prowlarr integration requires ASINs** to find torrents
3. **Audible has the best audiobook metadata**
4. **The app is called "AudioBookRequest"** not "BookRequest"

---

## My Recommendation

### Short Term (What We Did)
✅ Keep Audible as primary source  
✅ Add direct ASIN search (helps with your specific case)  
✅ Improve ranking (better results)  

### Medium Term (What We Could Add)
Consider **Google Books as a supplement**:
```python
# If Audible search fails to find enough results
if len(audible_results) < 10:
    # Try Google Books ISBNs as potential ASINs
    google_results = await google_books_isbn_to_asin(query)
    results.extend(google_results)
```

This is **legal**, **maintains ASIN workflow**, and **might find your book**.

### Long Term (Future Enhancement)
Build **crowdsourced ASIN database** from user discoveries.

---

## Bottom Line

We can't fully replace Audible with Google Books/OpenLibrary because:
- The app downloads audiobooks (needs ASINs for Prowlarr)
- Audiobooks need specialized metadata (narrators, runtime)
- Torrent sites use ASINs, not ISBNs

But we **could supplement** Audible search with ISBN→ASIN lookups from Google Books!

Would you like me to implement that?
