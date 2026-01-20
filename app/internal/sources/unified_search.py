"""
Unified multi-source book search coordinator.
Searches Audible, Google Books, and OpenLibrary in parallel.
Deduplicates results by ISBN and merges metadata.
"""

from aiohttp import ClientSession
from sqlmodel import Session
from app.internal.models import Audiobook
from app.internal.book_search import (
    list_audible_books,
    audible_region_type,
    get_region_from_settings,
)
from app.internal.sources.google_books_api import (
    search_google_books,
    google_books_result_to_audiobook,
)
from app.internal.sources.openlibrary_api import (
    search_openlibrary,
    openlibrary_result_to_audiobook,
)
from app.util.log import logger


def _merge_books(existing: Audiobook, new: Audiobook) -> Audiobook:
    """
    Merge two Audiobook objects, preferring data from 'existing' (higher priority).
    Fills in missing fields from 'new'.
    """
    # Prefer existing ASIN if present
    if not existing.asin and new.asin:
        existing.asin = new.asin

    # Prefer existing ISBN if present
    if not existing.isbn_10 and new.isbn_10:
        existing.isbn_10 = new.isbn_10
    if not existing.isbn_13 and new.isbn_13:
        existing.isbn_13 = new.isbn_13

    # Merge narrators and authors (if new has data that existing doesn't)
    if not existing.narrators and new.narrators:
        existing.narrators = new.narrators
    if not existing.authors and new.authors:
        existing.authors = new.authors

    # Prefer existing cover, but use new if missing
    if not existing.cover_image and new.cover_image:
        existing.cover_image = new.cover_image

    # Prefer existing release date
    if not existing.release_date and new.release_date:
        existing.release_date = new.release_date

    # Prefer existing runtime
    if not existing.runtime_length_min and new.runtime_length_min:
        existing.runtime_length_min = new.runtime_length_min

    # Mark source as hybrid if merged from multiple sources
    if existing.source and new.source and existing.source != new.source:
        existing.source = "hybrid"

    return existing


async def deduplicate_by_isbn(
    audible_results: list[Audiobook],
    google_results: list[Audiobook],
    openlibrary_results: list[Audiobook],
) -> list[Audiobook]:
    """
    Merge books from multiple sources using ISBN matching.
    Priority: Audible (has ASIN) > Google Books > OpenLibrary
    """
    # Map ISBN-13 → Audiobook (highest priority)
    isbn13_map: dict[str, Audiobook] = {}
    # Map ISBN-10 → Audiobook (fallback)
    isbn10_map: dict[str, Audiobook] = {}
    # Map by ASIN (highest priority for Audible)
    asin_map: dict[str, Audiobook] = {}

    # Process Audible results first (highest priority)
    for book in audible_results:
        if book.asin:
            asin_map[book.asin] = book
        if book.isbn_13:
            isbn13_map[book.isbn_13] = book
        elif book.isbn_10:
            isbn10_map[book.isbn_10] = book

    # Process Google Books results (medium priority)
    for book in google_results:
        if book.isbn_13:
            if book.isbn_13 not in isbn13_map:
                isbn13_map[book.isbn_13] = book
            else:
                # Merge metadata
                isbn13_map[book.isbn_13] = _merge_books(isbn13_map[book.isbn_13], book)
        elif book.isbn_10:
            if book.isbn_10 not in isbn10_map:
                isbn10_map[book.isbn_10] = book
            else:
                isbn10_map[book.isbn_10] = _merge_books(isbn10_map[book.isbn_10], book)

    # Process OpenLibrary results (lowest priority)
    for book in openlibrary_results:
        if book.isbn_13:
            if book.isbn_13 not in isbn13_map:
                isbn13_map[book.isbn_13] = book
            else:
                # Merge only if existing book is incomplete
                existing = isbn13_map[book.isbn_13]
                if not existing.narrators:
                    existing.narrators = book.narrators
        elif book.isbn_10:
            if book.isbn_10 not in isbn10_map:
                isbn10_map[book.isbn_10] = book
            else:
                existing = isbn10_map[book.isbn_10]
                if not existing.narrators:
                    existing.narrators = book.narrators

    # Combine all results (ISBN-13 has priority over ISBN-10)
    all_books = list(isbn13_map.values()) + list(isbn10_map.values())

    # Also include any ASIN-only books that didn't appear in ISBN maps
    for asin, book in asin_map.items():
        if book not in all_books:
            all_books.append(book)

    logger.info(
        "Deduplication complete",
        unique_books=len(all_books),
        isbn13_unique=len(isbn13_map),
        isbn10_unique=len(isbn10_map),
    )

    return all_books


async def unified_search(
    session: Session,
    client_session: ClientSession,
    query: str,
    num_results: int = 30,
    region: audible_region_type | None = None,
    sources: list[str] | None = None,
) -> list[Audiobook]:
    """
    Search multiple book APIs in parallel, deduplicate by ISBN.

    Args:
        session: Database session
        client_session: Async HTTP session
        query: Search query string
        num_results: Maximum results to return
        region: Audible region (e.g., "us", "uk")
        sources: List of sources to search (default: all available)

    Returns:
        List of Audiobook objects from all sources, deduplicated
    """
    if region is None:
        region = get_region_from_settings()

    if sources is None:
        sources = ["audible", "google_books", "openlibrary"]

    logger.info(
        "Starting unified search",
        query=query,
        sources=sources,
        num_results=num_results,
    )

    # Execute searches in parallel with error handling
    audible_results = []
    google_results = []
    openlibrary_results = []

    if "audible" in sources:
        try:
            audible_results = await list_audible_books(
                session=session,
                client_session=client_session,
                query=query,
                num_results=num_results,
                page=0,
                audible_region=region,
            )
        except Exception as e:
            logger.error("Audible search failed", query=query, error=str(e))

    if "google_books" in sources:
        try:
            google_search_results = await search_google_books(
                client_session,
                query,
                max_results=num_results,
            )
            google_results = [
                google_books_result_to_audiobook(r) for r in google_search_results
            ]
        except Exception as e:
            logger.error("Google Books search failed", query=query, error=str(e))

    if "openlibrary" in sources:
        try:
            openlibrary_search_results = await search_openlibrary(
                client_session,
                query,
                max_results=num_results,
            )
            openlibrary_results = [
                openlibrary_result_to_audiobook(r) for r in openlibrary_search_results
            ]
        except Exception as e:
            logger.error("OpenLibrary search failed", query=query, error=str(e))

    # Deduplicate and merge
    merged_results = await deduplicate_by_isbn(
        audible_results,
        google_results,
        openlibrary_results,
    )

    logger.info(
        "Unified search complete",
        query=query,
        total_results=len(merged_results),
        audible_count=len(audible_results),
        google_count=len(google_results),
        openlibrary_count=len(openlibrary_results),
    )

    return merged_results[:num_results]


async def search_author_books(
    session: Session,
    client_session: ClientSession,
    author_name: str,
    num_results: int = 100,
    sources: list[str] | None = None,
) -> list[Audiobook]:
    """
    Search for all books by an author across multiple sources.
    Comprehensive author bibliography from Google Books, OpenLibrary, and Audible.

    Args:
        session: Database session
        client_session: Async HTTP session
        author_name: Author name to search for
        num_results: Maximum results to return
        sources: List of sources to search (default: all available)

    Returns:
        List of Audiobook objects for books by the author, deduplicated
    """
    if sources is None:
        sources = ["google_books", "openlibrary", "audible"]

    logger.info(
        "Starting author search",
        author_name=author_name,
        sources=sources,
        num_results=num_results,
    )

    # Search each source for books by author
    google_results = []
    openlibrary_results = []
    audible_results = []

    if "google_books" in sources:
        try:
            from app.internal.sources.google_books_api import (
                search_google_books_by_author,
            )

            google_search_results = await search_google_books_by_author(
                client_session,
                author_name,
                max_results=num_results,
            )
            google_results = [
                google_books_result_to_audiobook(r) for r in google_search_results
            ]
        except Exception as e:
            logger.error(
                "Google Books author search failed",
                author_name=author_name,
                error=str(e),
            )

    if "openlibrary" in sources:
        try:
            from app.internal.sources.openlibrary_api import (
                search_openlibrary_by_author,
            )

            openlibrary_search_results = await search_openlibrary_by_author(
                client_session,
                author_name,
                max_results=num_results,
            )
            openlibrary_results = [
                openlibrary_result_to_audiobook(r) for r in openlibrary_search_results
            ]
        except Exception as e:
            logger.error(
                "OpenLibrary author search failed",
                author_name=author_name,
                error=str(e),
            )

    if "audible" in sources:
        try:
            # For Audible, use regular search with author name
            audible_results = await list_audible_books(
                session=session,
                client_session=client_session,
                query=author_name,
                num_results=min(num_results, 50),  # Audible API limit
                page=0,
                audible_region=get_region_from_settings(),
            )
        except Exception as e:
            logger.error(
                "Audible author search failed",
                author_name=author_name,
                error=str(e),
            )

    # Deduplicate and merge
    merged_results = await deduplicate_by_isbn(
        audible_results,
        google_results,
        openlibrary_results,
    )

    logger.info(
        "Author search complete",
        author_name=author_name,
        total_results=len(merged_results),
        audible_count=len(audible_results),
        google_count=len(google_results),
        openlibrary_count=len(openlibrary_results),
    )

    return merged_results[:num_results]
