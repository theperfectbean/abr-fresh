# Aggressive Search Solutions Analysis

**Date:** 2026-01-19  
**Status:** Exploration - Not Implemented

---

## Problem Recap

Audible's **public search API** (`/1.0/catalog/products`) doesn't return all audiobooks that exist on audible.com. Books with ISBN-style ASINs (like `1797101021`) are often missing.

---

## Aggressive Solution Options

### Option 1: Scrape Audible.com Search Results

**How it works:**
```python
async def scrape_audible_search(query: str) -> list[str]:
    """Scrape ASINs from audible.com search page"""
    url = f"https://www.audible.com/search?keywords={query}"
    
    async with ClientSession() as session:
        async with session.get(url, headers={"User-Agent": "Mozilla/5.0..."}) as response:
            html = await response.text()
            
    # Parse HTML to extract ASINs
    # Example: <a href="/pd/Book-Title-Audiobook/1797101021">
    asins = re.findall(r'/pd/[^/]+/([B0-9A-Z]{10})', html)
    return list(set(asins))
```

**Pros:**
- ✅ Gets ALL books that appear on website
- ✅ Finds books missing from API
- ✅ Same results users see in browser

**Cons:**
- ❌ **Violates Audible Terms of Service**
- ❌ Fragile - breaks when HTML structure changes
- ❌ Slower than API (needs HTML parsing)
- ❌ May trigger rate limiting/blocking
- ❌ Requires maintenance when site updates

**Risk Level:** 🔴 **HIGH** - Could result in IP bans or legal issues

---

### Option 2: Scrape Audible Author Pages

**How it works:**
```python
async def scrape_author_page(author_asin: str) -> list[str]:
    """Get all books by author from their Audible page"""
    url = f"https://www.audible.com/author/{author_name}/{author_asin}"
    
    # 1. Fetch author page HTML
    # 2. Parse book listings
    # 3. Extract all book ASINs
    # 4. Return complete list
```

**Implementation:**
- Build author ASIN → book ASINs mapping
- When user searches "bart ehrman", look up author page
- Return all books from that author

**Pros:**
- ✅ Gets complete author catalog
- ✅ More stable than search page scraping
- ✅ Can build comprehensive database

**Cons:**
- ❌ **Still violates ToS**
- ❌ Only works for known authors
- ❌ Requires author name → ASIN mapping
- ❌ Doesn't help with title-only searches

**Risk Level:** 🟠 **MEDIUM-HIGH** - Less fragile but still against ToS

---

### Option 3: Browser Automation (Selenium/Playwright)

**How it works:**
```python
from playwright.async_api import async_playwright

async def browser_search(query: str) -> list[str]:
    """Use headless browser to get real search results"""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        await page.goto(f"https://www.audible.com/search?keywords={query}")
        
        # Wait for results to load
        await page.wait_for_selector('.productListItem')
        
        # Extract ASINs from loaded page
        asins = await page.eval_on_selector_all(
            '.productListItem',
            'elements => elements.map(e => e.dataset.asin)'
        )
        
        await browser.close()
        return asins
```

**Pros:**
- ✅ Gets exact results user would see
- ✅ Handles JavaScript rendering
- ✅ More reliable than HTML scraping

**Cons:**
- ❌ **Violates ToS**
- ❌ Extremely slow (2-5 seconds per search)
- ❌ High resource usage (requires Chrome)
- ❌ Easier to detect and block
- ❌ Complicated deployment

**Risk Level:** 🔴 **HIGH** - Obvious automation, easy to detect

---

### Option 4: Reverse Engineer Mobile App API

**Theory:**
The Audible mobile app may use a different API with better indexing.

**How to investigate:**
```bash
# 1. Install Audible app on Android emulator
# 2. Use mitmproxy to intercept HTTP requests
# 3. Capture API endpoints when searching in app
# 4. Analyze authentication and request format
# 5. Replicate in our code
```

**Pros:**
- ✅ Might have better book coverage
- ✅ Faster than web scraping
- ✅ More structured data (JSON)

**Cons:**
- ❌ **Violates ToS**
- ❌ Requires reverse engineering effort
- ❌ App API may have same limitations
- ❌ Authentication/encryption challenges
- ❌ May require app credentials

**Risk Level:** 🔴 **VERY HIGH** - Clear ToS violation

---

### Option 5: Build Book Catalog from External Sources

**How it works:**
Aggregate book data from multiple sources:

```python
# 1. Google Books API - Get books by author
google_books = search_google_books("Bart Ehrman")

# 2. OpenLibrary - Get book ISBNs
open_library = search_openlibrary("Bart Ehrman")

# 3. Goodreads - Get book titles
# (Note: Goodreads API is deprecated)

# 4. Cross-reference ISBNs to Audible ASINs
for isbn in all_isbns:
    # Try direct lookup on Audible
    asin = try_isbn_as_asin(isbn)
    if asin and book_exists(asin):
        store_in_database(asin)
```

**Pros:**
- ✅ Legal (using public APIs)
- ✅ Builds comprehensive catalog over time
- ✅ Can find books Audible search misses

**Cons:**
- ❌ Complex ISBN→ASIN mapping
- ❌ Not all books have ISBNs
- ❌ External APIs may have rate limits
- ❌ Takes time to build complete catalog
- ❌ Doesn't guarantee finding specific books

**Risk Level:** 🟢 **LOW** - Legal if done properly

---

### Option 6: Crowdsourced Book Database

**How it works:**
```python
# Every time a user finds a book (any method), store it
def on_book_discovered(book: Audiobook, search_query: str):
    """Build searchable local index over time"""
    
    # Store in database with full-text search
    db.execute("""
        INSERT INTO discovered_books (asin, title, authors, discovered_via)
        VALUES (?, ?, ?, ?)
    """, (book.asin, book.title, book.authors, search_query))
    
    # Index for full-text search
    search_index.add(book)

# When searching, check local database first
def search_books(query: str):
    # 1. Search local database
    local_results = full_text_search_local(query)
    
    # 2. Search Audible API
    api_results = audible_search(query)
    
    # 3. Merge and deduplicate
    return merge_results(local_results, api_results)
```

**Pros:**
- ✅ Completely legal
- ✅ Gets better over time
- ✅ Leverages community knowledge
- ✅ No external dependencies

**Cons:**
- ❌ Slow to build catalog initially
- ❌ Only finds books someone searched for before
- ❌ Requires database full-text search setup
- ❌ Doesn't help first user to search for a book

**Risk Level:** 🟢 **NONE** - Completely safe

---

## Recommendation Matrix

| Solution | Effectiveness | Risk | Complexity | Legality |
|----------|--------------|------|------------|----------|
| Scrape search results | ⭐⭐⭐⭐⭐ | 🔴 High | Medium | ❌ Illegal |
| Scrape author pages | ⭐⭐⭐⭐ | 🟠 Med-High | Medium | ❌ Illegal |
| Browser automation | ⭐⭐⭐⭐⭐ | 🔴 High | High | ❌ Illegal |
| Reverse engineer app | ⭐⭐⭐⭐ | 🔴 Very High | Very High | ❌ Illegal |
| External sources | ⭐⭐⭐ | 🟢 None | High | ✅ Legal |
| Crowdsourced DB | ⭐⭐⭐ | 🟢 None | Medium | ✅ Legal |

---

## Realistic Implementation: Hybrid Approach

**Combine legal methods for best results:**

```python
async def hybrid_search(query: str) -> list[Audiobook]:
    """Multi-source search with fallbacks"""
    
    results = []
    
    # 1. Local database (fast, free)
    local = search_local_database(query)
    results.extend(local)
    
    # 2. Audible API (official, limited)
    try:
        audible = await search_audible_api(query)
        results.extend(audible)
    except Exception as e:
        logger.warning("Audible API failed", error=e)
    
    # 3. Cross-reference external sources for ASINs
    if len(results) < 10:
        # Get book titles from Google Books
        google_books = await search_google_books_api(query)
        
        # Try to find matching ASINs
        for book in google_books:
            # Try ISBN as ASIN
            for isbn in book.isbns:
                if asin_exists(isbn):
                    results.append(fetch_book(isbn))
    
    # Deduplicate and rank
    return deduplicate_and_rank(results)
```

**This approach:**
- ✅ Legal (uses public APIs only)
- ✅ Gets better over time (local DB grows)
- ✅ Has multiple fallbacks
- ✅ No ToS violations

---

## Sample Implementation: Option 1 (Scraping)

**For educational purposes only - NOT RECOMMENDED:**

```python
import re
from bs4 import BeautifulSoup
import aiohttp

async def scrape_audible_search(query: str) -> list[str]:
    """
    ⚠️ WARNING: This violates Audible Terms of Service
    ⚠️ Use at your own risk - may result in IP ban
    """
    
    url = f"https://www.audible.com/search"
    params = {"keywords": query, "ref": "a_search_c1_srch"}
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, headers=headers) as response:
            if response.status != 200:
                logger.error("Scraping failed", status=response.status)
                return []
            
            html = await response.text()
    
    # Parse HTML
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find all product links (structure may change!)
    # Example: <a href="/pd/Book-Title-Audiobook/1797101021?ref=...">
    asins = []
    for link in soup.find_all('a', href=True):
        match = re.search(r'/pd/[^/]+/([B0-9A-Z]{10})', link['href'])
        if match:
            asins.append(match.group(1))
    
    return list(set(asins))

# Usage in list_audible_books():
async def list_audible_books_with_scraping(session, client_session, query, ...):
    # Try API first
    api_results = await search_audible_api(query)
    
    if len(api_results) < 10:
        # Fallback to scraping (NOT RECOMMENDED)
        logger.warning("Falling back to web scraping", query=query)
        scraped_asins = await scrape_audible_search(query)
        
        # Fetch details for scraped ASINs
        for asin in scraped_asins:
            book = await get_book_by_asin(client_session, asin, region)
            if book:
                api_results.append(book)
    
    return api_results
```

**Required dependencies:**
```bash
pip install beautifulsoup4 lxml
```

**Risks:**
- Audible can detect and ban your IP
- Legal liability for ToS violation
- Code breaks when HTML structure changes
- Performance issues with HTML parsing

---

## My Professional Recommendation

**Do NOT implement aggressive solutions.**

Instead:
1. Keep current implementation (direct ASIN search + improved ranking)
2. Add crowdsourced book database (Option 6)
3. Add Google Books API integration for ISBN cross-referencing (Option 5)
4. Document the limitation clearly for users

**Add a UI hint:**
```
"Can't find a book? Try:
- Searching by title instead of author
- Using the ASIN directly (found on audible.com)
- Adding more specific keywords"
```

This is honest, legal, and sustainable long-term.
