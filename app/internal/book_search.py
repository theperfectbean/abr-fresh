import asyncio
import re
import time
from datetime import datetime
from typing import Literal, TypedDict, cast
from urllib.parse import urlencode

from aiohttp import ClientSession
from pydantic import BaseModel
from sqlalchemy import CursorResult, delete
from sqlalchemy.exc import InvalidRequestError
from sqlmodel import Session, col, not_, select

from app.internal.env_settings import Settings
from app.internal.models import Audiobook, AudiobookRequest
from app.util.log import logger

REFETCH_TTL = 60 * 60 * 24 * 7  # 1 week

audible_region_type = Literal[
    "us",
    "ca",
    "uk",
    "au",
    "fr",
    "de",
    "jp",
    "it",
    "in",
    "es",
    "br",
]
audible_regions: dict[audible_region_type, str] = {
    "us": ".com",
    "ca": ".ca",
    "uk": ".co.uk",
    "au": ".com.au",
    "fr": ".fr",
    "de": ".de",
    "jp": ".co.jp",
    "it": ".it",
    "in": ".in",
    "es": ".es",
    "br": ".com.br",
}


def clear_old_book_caches(session: Session):
    """Deletes outdated cached audiobooks that haven't been requested by anyone"""
    delete_query = delete(Audiobook).where(
        col(Audiobook.updated_at) < datetime.fromtimestamp(time.time() - REFETCH_TTL),
        col(Audiobook.id).not_in(select(col(AudiobookRequest.audiobook_id).distinct())),
        not_(Audiobook.downloaded),
    )
    result = cast(CursorResult[Audiobook], session.execute(delete_query))
    session.commit()
    logger.debug("Cleared old book caches", rowcount=result.rowcount)


def get_region_from_settings() -> audible_region_type:
    region = Settings().app.default_region
    if region not in audible_regions:
        return "us"
    return region


class _AudnexusResponse(BaseModel):
    class _Author(TypedDict):
        name: str

    asin: str
    title: str
    subtitle: str | None
    authors: list[_Author]
    narrators: list[_Author]
    image: str | None
    releaseDate: str
    runtimeLengthMin: int


async def _get_audnexus_book(
    session: ClientSession,
    asin: str,
    region: audible_region_type,
) -> Audiobook | None:
    """
    https://audnex.us/#tag/Books/operation/getBookById
    """
    logger.debug("Fetching book from Audnexus", asin=asin, region=region)
    try:
        async with session.get(
            f"https://api.audnex.us/books/{asin}?region={region}",
            headers={"Client-Agent": "audiobookrequest"},
        ) as response:
            if not response.ok:
                logger.warning(
                    "Failed to fetch book from Audnexus",
                    asin=asin,
                    status=response.status,
                    reason=response.reason,
                )
                return None
            audnexus_response = _AudnexusResponse.model_validate(await response.json())
    except Exception as e:
        logger.error("Exception while fetching book from Audnexus", asin=asin, error=e)
        return None
    return Audiobook(
        asin=audnexus_response.asin,
        title=audnexus_response.title,
        subtitle=audnexus_response.subtitle,
        authors=[author["name"] for author in audnexus_response.authors],
        narrators=[narrator["name"] for narrator in audnexus_response.narrators],
        cover_image=audnexus_response.image,
        release_date=datetime.fromisoformat(audnexus_response.releaseDate),
        runtime_length_min=audnexus_response.runtimeLengthMin,
    )


class _AudimetaResponse(BaseModel):
    class _Author(TypedDict):
        name: str

    asin: str
    title: str
    subtitle: str | None
    authors: list[_Author]
    narrators: list[_Author]
    imageUrl: str | None
    releaseDate: str
    lengthMinutes: int | None


class _AudimetaSearchResult(BaseModel):
    """Minimal model for Audimeta search results - we only need ASINs"""
    asin: str


async def _search_audimeta(
    session: ClientSession,
    query: str,
) -> list[str]:
    """
    Search Audimeta for books and return list of ASINs.
    
    Returns up to 10 ASINs per query based on Audimeta's search algorithm.
    """
    logger.debug("Searching Audimeta", query=query)
    try:
        async with session.get(
            f"https://audimeta.de/search?query={query}",
            headers={"Client-Agent": "audiobookrequest"},
        ) as response:
            if not response.ok:
                logger.warning(
                    "Failed to search Audimeta",
                    query=query,
                    status=response.status,
                    reason=response.reason,
                )
                return []
            results = [_AudimetaSearchResult.model_validate(item) for item in await response.json()]
            return [result.asin for result in results]
    except Exception as e:
        logger.warning("Exception while searching Audimeta", query=query, error=e)
        return []


async def _get_audimeta_book(
    session: ClientSession,
    asin: str,
    region: audible_region_type,
) -> Audiobook | None:
    """
    https://audimeta.de/api-docs/#/book/get_book__asin_
    """
    logger.debug("Fetching book from Audimeta", asin=asin, region=region)
    try:
        async with session.get(
            f"https://audimeta.de/book/{asin}?region={region}",
            headers={"Client-Agent": "audiobookrequest"},
        ) as response:
            if not response.ok:
                logger.warning(
                    "Failed to fetch book from Audimeta",
                    asin=asin,
                    status=response.status,
                    reason=response.reason,
                )
                return None
            audimeta_response = _AudimetaResponse.model_validate(await response.json())
    except Exception as e:
        logger.error("Exception while fetching book from Audimeta", asin=asin, error=e)
        return None
    return Audiobook(
        asin=audimeta_response.asin,
        title=audimeta_response.title,
        subtitle=audimeta_response.subtitle,
        authors=[author["name"] for author in audimeta_response.authors],
        narrators=[narrator["name"] for narrator in audimeta_response.narrators],
        cover_image=audimeta_response.imageUrl,
        release_date=datetime.fromisoformat(audimeta_response.releaseDate),
        runtime_length_min=audimeta_response.lengthMinutes or 0,
    )


async def get_book_by_asin(
    session: ClientSession,
    asin: str,
    audible_region: audible_region_type | None = None,
) -> Audiobook | None:
    if audible_region is None:
        audible_region = get_region_from_settings()
    book = await _get_audimeta_book(session, asin, audible_region)
    if book:
        return book
    logger.debug(
        "Audimeta did not have the book, trying Audnexus",
        asin=asin,
        region=audible_region,
    )
    book = await _get_audnexus_book(session, asin, audible_region)
    if book:
        return book
    logger.warning(
        "Did not find the book on both Audnexus and Audimeta",
        asin=asin,
        region=audible_region,
    )


class CacheQuery(BaseModel, frozen=True):
    query: str
    num_results: int
    page: int
    audible_region: audible_region_type


class CacheResult[T](BaseModel, frozen=True):
    value: T
    timestamp: float


# simple caching of search results to avoid having to fetch from audible so frequently
search_cache: dict[CacheQuery, CacheResult[list[Audiobook]]] = {}
search_suggestions_cache: dict[str, CacheResult[list[str]]] = {}


class _AudibleSuggestionsResponse(BaseModel):
    class _Items(BaseModel):
        class _Item(BaseModel):
            class _Model(BaseModel):
                class _Metadata(BaseModel):
                    class _Title(BaseModel):
                        value: str

                    title: _Title

                class _TitleGroup(BaseModel):
                    class _Title(BaseModel):
                        value: str

                    title: _Title

                product_metadata: _Metadata | None = None
                title_group: _TitleGroup | None = None

                @property
                def title(self) -> str | None:
                    if self.product_metadata and self.product_metadata.title:
                        return self.product_metadata.title.value
                    if self.title_group and self.title_group.title:
                        return self.title_group.title.value
                    return None

            model: _Model

        items: list[_Item]

    model: _Items


async def get_search_suggestions(
    client_session: ClientSession,
    query: str,
    audible_region: audible_region_type | None = None,
) -> list[str]:
    if audible_region is None:
        audible_region = get_region_from_settings()
    cache_result = search_suggestions_cache.get(query)
    if cache_result and time.time() - cache_result.timestamp < REFETCH_TTL:
        return cache_result.value

    params = {
        "key_strokes": query,
        "site_variant": "desktop",
    }
    base_url = (
        f"https://api.audible{audible_regions[audible_region]}/1.0/searchsuggestions?"
    )
    url = base_url + urlencode(params)

    try:
        async with client_session.get(url) as response:
            response.raise_for_status()
            suggestions = _AudibleSuggestionsResponse.model_validate(
                await response.json()
            )
    except Exception as e:
        logger.error(
            "Exception while fetching search suggestions from Audible",
            query=query,
            region=audible_region,
            error=e,
        )
        return []

    titles = [item.model.title for item in suggestions.model.items if item.model.title]
    search_suggestions_cache[query] = CacheResult(
        value=titles,
        timestamp=time.time(),
    )

    return titles


class _AudibleSearchResponse(BaseModel):
    class _AsinObj(BaseModel):
        asin: str

    products: list[_AsinObj]


def _expand_search_queries(query: str) -> list[str]:
    """
    Generate multiple query variants to improve search recall.
    
    For "bart ehrman" returns: ["bart ehrman", "ehrman", "bart"]
    For "heaven and hell" returns: ["heaven and hell", "heaven hell", "hell", "heaven"]
    """
    parts = query.strip().split()
    
    if len(parts) == 0:
        return [query]
    
    queries = [query]  # Original query first
    
    # For 2+ word queries (likely author names), try surname-only variations
    if len(parts) >= 2:
        surname = parts[-1]
        queries.append(surname)
        
        # Also try first word (often a first name)
        queries.append(parts[0])
    
    # Try removing articles and common words for title queries
    articles = {"the", "a", "an", "and", "of", "or", "in", "on"}
    meaningful = [p for p in parts if p.lower() not in articles]
    if meaningful and len(meaningful) < len(parts):
        queries.append(" ".join(meaningful))
    
    return queries


async def list_audible_books(
    session: Session,
    client_session: ClientSession,
    query: str,
    num_results: int = 20,
    page: int = 0,
    audible_region: audible_region_type | None = None,
) -> list[Audiobook]:
    """
    https://audible.readthedocs.io/en/latest/misc/external_api.html#get--1.0-catalog-products

    We first use the audible search API to get a list of matching ASINs. Using these ASINs we check our database
    if we have any of the books already to save on the amount of requests we have to do.
    Any books we don't already have locally, we fetch all the details from audnexus.
    
    IMPROVEMENT: Multi-query search strategy for better recall
    - Expands query into multiple variants ("bart ehrman" → ["bart ehrman", "ehrman", "bart"])
    - Searches Audible API with each variant (50 results per variant)
    - Deduplicates ASINs across all variants
    - Returns up to num_results books, prioritizing best rank across variants
    
    DIRECT ASIN SEARCH: If query matches ASIN format (B0XXXXXXXXX or 10-digit ISBN), 
    attempts direct lookup since some books aren't indexed in Audible's search API.
    
    Note: Even with these improvements, some books may not be found due to Audible's ranking algorithm.
    Books that don't rank highly in Audible's relevance scoring won't appear in the top 50 results per variant.
    Users can improve results by adding specific subject terms (e.g., "ehrman afterlife" vs just "ehrman").
    """
    if audible_region is None:
        audible_region = get_region_from_settings()
    
    # NEW: Direct ASIN lookup if query matches ASIN format
    # Some audiobooks (especially ISBN-style ASINs) aren't indexed in search but can be fetched directly
    query_stripped = query.strip()
    if re.match(r'^[0-9]{10}$|^B[0-9A-Z]{9}$', query_stripped):
        logger.info("Query appears to be ASIN, attempting direct lookup", asin=query_stripped, region=audible_region)
        book = await get_book_by_asin(client_session, query_stripped, audible_region)
        if book:
            # Store in DB and return
            existing_books = get_existing_books(session, {book.asin})
            if book.asin not in existing_books:
                store_new_books(session, [book])
            else:
                book = existing_books[book.asin]
                session.add(book)
                session.refresh(book)
            logger.info("Direct ASIN lookup successful", asin=query_stripped)
            return [book]
        logger.info("Direct ASIN lookup failed, falling back to search", asin=query_stripped)
    
    # First, try the original query directly (for cache/performance)
    cache_key = CacheQuery(
        query=query,
        num_results=num_results,
        page=page,
        audible_region=audible_region,
    )
    cache_result = search_cache.get(cache_key)

    if cache_result and time.time() - cache_result.timestamp < REFETCH_TTL:
        try:
            for book in cache_result.value:
                # add back books to the session so we can access their attributes
                session.add(book)
                session.refresh(book)
            logger.debug(
                "Using cached search result", query=query, region=audible_region
            )
            return cache_result.value
        except InvalidRequestError:
            logger.debug(
                "Cached search result contained deleted book, refetching",
                query=query,
                region=audible_region,
            )

    # Collect results from original + variant queries
    # IMPROVED: Track best (lowest) position per ASIN across all query variants
    all_asins = {}  # ASIN -> best_position (lower is better)
    
    expanded_queries = _expand_search_queries(query)
    logger.debug("Search query expansion", original=query, expanded=expanded_queries)
    
    # Fetch more results per variant to improve recall, but still limit final output to num_results
    fetch_per_variant = min(50, num_results * 2)
    
    # Search Audible with expanded queries
    for expanded_query in expanded_queries:
        params = {
            "num_results": fetch_per_variant,
            "products_sort_by": "Relevance",
            "keywords": expanded_query,
            "page": page,
        }
        base_url = (
            f"https://api.audible{audible_regions[audible_region]}/1.0/catalog/products?"
        )
        url = base_url + urlencode(params)

        try:
            async with client_session.get(url) as response:
                response.raise_for_status()
                audible_response = _AudibleSearchResponse.model_validate(
                    await response.json()
                )
                
                # Track best position per ASIN across all variants
                # If book ranks #14 in "ehrman" but #23 in "bart ehrman", use #14
                for idx, asin_obj in enumerate(audible_response.products):
                    asin = asin_obj.asin
                    if asin not in all_asins or idx < all_asins[asin]:
                        all_asins[asin] = idx
                        
                logger.debug(
                    f"Query variant found results",
                    variant_query=expanded_query,
                    count=len(audible_response.products),
                    total_unique_so_far=len(all_asins)
                )
        except Exception as e:
            logger.warning(
                "Exception while fetching search results for variant",
                variant_query=expanded_query,
                region=audible_region,
                error=e,
            )
            continue

    if not all_asins:
        logger.warning("No results from any search variant", query=query)
        return []

    # do not fetch book results we already have locally
    asins = set(all_asins.keys())
    books = get_existing_books(session, asins)
    for key in books.keys():
        asins.remove(key)

    # book ASINs we do not have => fetch and store
    coros = [get_book_by_asin(client_session, asin, audible_region) for asin in asins]
    new_books = await asyncio.gather(*coros)
    new_books = [b for b in new_books if b]

    store_new_books(session, new_books)

    for b in new_books:
        books[b.asin] = b

    # IMPROVED: Return books sorted by best position across all variants
    # Books with better rankings in any variant appear first
    sorted_asins = sorted(all_asins.keys(), key=lambda a: all_asins[a])
    ordered: list[Audiobook] = []
    for asin in sorted_asins:
        if len(ordered) >= num_results:
            break
        book = books.get(asin)
        if book:
            ordered.append(book)
    
    logger.info(
        "Multi-query search complete",
        original_query=query,
        total_results=len(ordered),
        queries_tried=len(expanded_queries),
        unique_asins_found=len(all_asins)
    )

    search_cache[cache_key] = CacheResult(
        value=ordered,
        timestamp=time.time(),
    )

    # clean up cache slightly
    for k in list(search_cache.keys()):
        if time.time() - search_cache[k].timestamp > REFETCH_TTL:
            try:
                del search_cache[k]
            except KeyError:  # ignore in race conditions
                pass

    logger.info(
        "Multi-query search complete",
        original_query=query,
        total_results=len(ordered),
        queries_tried=len(expanded_queries),
    )
    
    return ordered


async def hybrid_search(
    session: Session,
    client_session: ClientSession,
    query: str,
    region: audible_region_type = "us",
    num_results: int = 30,
) -> list[Audiobook]:
    """
    Hybrid search using both Audible and Google Books.
    
    This addresses the issue where some audiobooks exist on Audible but don't
    appear in Audible's search API results (e.g., "bart ehrman" not showing
    "Heaven and Hell" with ASIN 1797101021).
    
    Strategy:
    1. Search Audible API first (audiobook-specific, fast)
    2. If < 10 results, query Google Books as fallback
    3. For each Google Books result, try ISBN as potential ASIN
    4. If ASIN exists on Audible, fetch and add to results with ISBN enrichment
    5. Return combined deduplicated results
    
    Args:
        session: Database session
        client_session: HTTP client session
        query: Search query string
        region: Audible region code
        num_results: Maximum number of results to return
    
    Returns:
        List of Audiobook objects from combined sources
    """
    from app.internal.google_books import search_google_books, extract_isbns
    
    # Step 1: Audible search (existing implementation)
    logger.info("Starting hybrid search", query=query)
    audible_results = await list_audible_books(
        session, client_session, query, num_results, 0, region
    )
    
    # If we have enough results, return early
    if len(audible_results) >= 20:
        logger.info(
            "Audible returned sufficient results, skipping Google Books",
            count=len(audible_results),
        )
        return audible_results
    
    # Step 2: Google Books fallback
    logger.info(
        "Audible returned few results, trying Google Books",
        audible_count=len(audible_results),
    )
    
    try:
        google_books = await search_google_books(client_session, query, max_results=20)
    except Exception as e:
        logger.error("Google Books search failed", error=str(e))
        google_books = []
    
    found_via_google: list[Audiobook] = []
    
    for item in google_books:
        volume_info = item.get("volumeInfo", {})
        isbn_10, isbn_13 = extract_isbns(volume_info)
        
        if not isbn_10 and not isbn_13:
            continue
        
        # Try ISBN-10 first (10-digit format common for older books)
        # Many older audiobooks use ISBN-10 as their ASIN
        potential_asins = [isbn_10, isbn_13] if isbn_10 else [isbn_13] if isbn_13 else []
        
        for potential_asin in potential_asins:
            if not potential_asin:
                continue
                
            potential_asin = potential_asin.replace("-", "")
            
            # Try to fetch from Audible using this ISBN as ASIN
            try:
                book = await get_book_by_asin(client_session, potential_asin, region)
                if book:
                    # Enrich with ISBN data
                    book.isbn_10 = isbn_10
                    book.isbn_13 = isbn_13
                    book.google_books_id = item.get("id")
                    book.source = "google_books_hybrid"
                    found_via_google.append(book)
                    
                    logger.info(
                        "Found audiobook via Google Books ISBN",
                        title=book.title,
                        isbn=potential_asin,
                        asin=book.asin,
                    )
                    break  # Found it, no need to try other ISBNs
                    
            except Exception as e:
                logger.debug(
                    "ISBN not found on Audible",
                    isbn=potential_asin,
                    error=str(e),
                )
    
    # Step 3: Combine and deduplicate results
    all_results = audible_results + found_via_google

    seen_asins: set[str | None] = set()
    unique_results: list[Audiobook] = []

    for book in all_results:
        # Use ASIN for deduplication if available, otherwise use UUID
        dedup_key = book.asin if book.asin else str(book.id)

        if dedup_key not in seen_asins:
            seen_asins.add(dedup_key)
            unique_results.append(book)

    logger.info(
        "Hybrid search complete",
        total_results=len(unique_results),
        audible_results=len(audible_results),
        google_books_results=len(found_via_google),
    )

    return unique_results[:num_results]


def get_existing_books(session: Session, asins: set[str]) -> dict[str, Audiobook]:
    books = list(
        session.exec(select(Audiobook).where(col(Audiobook.asin).in_(asins))).all()
    )

    ok_books: list[Audiobook] = []
    for b in books:
        if b.updated_at.timestamp() + REFETCH_TTL < time.time():
            continue
        ok_books.append(b)

    return {b.asin: b for b in ok_books}


def store_new_books(session: Session, books: list[Audiobook]):
    asins = {b.asin: b for b in books}

    existing = list(
        session.exec(
            select(Audiobook).where(col(Audiobook.asin).in_(asins.keys()))
        ).all()
    )

    to_update: list[Audiobook] = []
    for b in existing:
        new_book = asins[b.asin]
        b.title = new_book.title
        b.subtitle = new_book.subtitle
        b.authors = new_book.authors
        b.narrators = new_book.narrators
        b.cover_image = new_book.cover_image
        b.release_date = new_book.release_date
        b.runtime_length_min = new_book.runtime_length_min
        to_update.append(b)

    existing_asins = {b.asin for b in existing}
    to_add = [b for b in books if b.asin not in existing_asins]

    logger.info(
        "Storing new search results in BookRequest cache/db",
        to_add_count=len(to_add),
        to_update_count=len(to_update),
        existing_count=len(existing),
    )

    session.add_all(to_add + existing)
    session.commit()
