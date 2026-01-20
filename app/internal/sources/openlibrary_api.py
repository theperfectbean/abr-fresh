"""
OpenLibrary API integration for book search and metadata enrichment.
"""

from datetime import datetime
from typing import TypedDict
from aiohttp import ClientSession
from pydantic import BaseModel
from app.internal.models import Audiobook
from app.internal.sources.isbn_utils import normalize_isbn
from app.util.log import logger


class OpenLibraryDoc(TypedDict, total=False):
    """Simplified OpenLibrary search result document."""

    key: str
    title: str
    author_name: list[str]
    first_publish_year: int
    isbn: list[str]
    cover_i: int
    publisher: list[str]


class OpenLibrarySearchResult(BaseModel):
    """Response model for OpenLibrary search."""

    key: str
    title: str
    authors: list[str]
    published_year: int | None
    isbn: list[str]
    cover_url: str | None


def _extract_cover_url(cover_id: int | None) -> str | None:
    """Generate cover URL from OpenLibrary cover ID."""
    if not cover_id:
        return None
    return f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"


async def search_openlibrary(
    session: ClientSession,
    query: str,
    max_results: int = 40,
) -> list[OpenLibrarySearchResult]:
    """
    Search OpenLibrary API for books.
    Returns up to max_results books.
    """
    logger.debug("Searching OpenLibrary", query=query, max_results=max_results)

    url = "https://openlibrary.org/search.json"
    params = {
        "q": query,
        "limit": min(max_results, 100),  # OpenLibrary supports up to 100
        "lang": "en",
    }

    try:
        async with session.get(url, params=params) as response:
            if not response.ok:
                logger.warning(
                    "OpenLibrary API error",
                    query=query,
                    status=response.status,
                )
                return []

            data = await response.json()
            docs = data.get("docs", [])

            results = []
            for doc in docs:
                # Skip if missing critical fields
                if not doc.get("title"):
                    continue

                isbns = [normalize_isbn(isbn) for isbn in doc.get("isbn", [])]

                result = OpenLibrarySearchResult(
                    key=doc.get("key", ""),
                    title=doc.get("title", ""),
                    authors=doc.get("author_name", []),
                    published_year=doc.get("first_publish_year"),
                    isbn=isbns,
                    cover_url=_extract_cover_url(doc.get("cover_i")),
                )
                results.append(result)

            logger.info(
                "OpenLibrary search complete",
                query=query,
                results_found=len(results),
            )
            return results

    except Exception as e:
        logger.error("Error searching OpenLibrary", query=query, error=str(e))
        return []


async def search_openlibrary_by_author(
    session: ClientSession,
    author_name: str,
    max_results: int = 40,
) -> list[OpenLibrarySearchResult]:
    """
    Search OpenLibrary for all books by an author.
    """
    logger.debug(
        "Searching OpenLibrary by author",
        author_name=author_name,
        max_results=max_results,
    )

    query = f"author:{author_name}"
    return await search_openlibrary(session, query, max_results)


async def get_openlibrary_by_isbn(
    session: ClientSession,
    isbn: str,
) -> OpenLibrarySearchResult | None:
    """Lookup a specific book by ISBN."""
    logger.debug("Fetching OpenLibrary by ISBN", isbn=isbn)

    url = "https://openlibrary.org/search.json"
    params = {
        "q": f"isbn:{isbn}",
        "limit": 1,
    }

    try:
        async with session.get(url, params=params) as response:
            if not response.ok:
                return None

            data = await response.json()
            docs = data.get("docs", [])

            if not docs:
                return None

            doc = docs[0]
            isbns = [normalize_isbn(isbn) for isbn in doc.get("isbn", [])]

            return OpenLibrarySearchResult(
                key=doc.get("key", ""),
                title=doc.get("title", ""),
                authors=doc.get("author_name", []),
                published_year=doc.get("first_publish_year"),
                isbn=isbns,
                cover_url=_extract_cover_url(doc.get("cover_i")),
            )

    except Exception as e:
        logger.error("Error fetching OpenLibrary by ISBN", isbn=isbn, error=str(e))
        return None


def openlibrary_result_to_audiobook(
    result: OpenLibrarySearchResult,
    source: str = "openlibrary",
) -> Audiobook:
    """Convert an OpenLibrary search result to an Audiobook object."""
    release_date = None
    if result.published_year:
        try:
            release_date = datetime(result.published_year, 1, 1)
        except (ValueError, TypeError):
            pass

    # Extract ISBN-10 and ISBN-13
    isbn_10 = None
    isbn_13 = None
    for isbn in result.isbn:
        if len(isbn) == 10:
            isbn_10 = isbn
        elif len(isbn) == 13:
            isbn_13 = isbn

    return Audiobook(
        title=result.title,
        subtitle=None,
        authors=result.authors,
        narrators=[],  # OpenLibrary doesn't have narrators
        cover_image=result.cover_url,
        release_date=release_date,
        runtime_length_min=None,  # OpenLibrary doesn't have runtime
        isbn_10=isbn_10,
        isbn_13=isbn_13,
        source=source,
    )
