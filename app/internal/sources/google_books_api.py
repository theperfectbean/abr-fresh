"""
Google Books API integration for book search and metadata enrichment.
"""

from datetime import datetime
from typing import TypedDict
from aiohttp import ClientSession
from pydantic import BaseModel
from app.internal.models import Audiobook
from app.internal.sources.isbn_utils import normalize_isbn
from app.util.log import logger


class GoogleBooksVolume(TypedDict, total=False):
    """Simplified Google Books Volume object."""
    id: str
    title: str
    authors: list[str]
    publishedDate: str
    description: str
    industryIdentifiers: list[dict]
    imageLinks: dict
    language: str


class GoogleBooksSearchResult(BaseModel):
    """Response model for Google Books search."""
    id: str
    title: str
    authors: list[str]
    published_date: str | None
    isbn_10: str | None
    isbn_13: str | None
    cover_url: str | None
    description: str | None


def _extract_isbn(identifiers: list[dict]) -> tuple[str | None, str | None]:
    """Extract ISBN-10 and ISBN-13 from industryIdentifiers."""
    isbn_10 = None
    isbn_13 = None

    for identifier in identifiers:
        if identifier.get("type") == "ISBN_10":
            isbn_10 = normalize_isbn(identifier.get("identifier", ""))
        elif identifier.get("type") == "ISBN_13":
            isbn_13 = normalize_isbn(identifier.get("identifier", ""))

    return isbn_10, isbn_13


def _extract_cover_url(image_links: dict | None) -> str | None:
    """Extract cover URL from image links."""
    if not image_links:
        return None
    return image_links.get("thumbnail") or image_links.get("smallThumbnail")


async def search_google_books(
    session: ClientSession,
    query: str,
    max_results: int = 40,
) -> list[GoogleBooksSearchResult]:
    """
    Search Google Books API for books.
    Returns up to max_results books.
    """
    logger.debug("Searching Google Books", query=query, max_results=max_results)

    url = "https://www.googleapis.com/books/v1/volumes"
    params = {
        "q": query,
        "maxResults": min(max_results, 40),  # Google Books API limit
        "printType": "books",
    }

    try:
        async with session.get(url, params=params) as response:
            if not response.ok:
                logger.warning(
                    "Google Books API error",
                    query=query,
                    status=response.status,
                )
                return []

            data = await response.json()
            items = data.get("items", [])

            results = []
            for item in items:
                volume_info = item.get("volumeInfo", {})

                # Skip if missing critical fields
                if not volume_info.get("title"):
                    continue

                isbn_10, isbn_13 = _extract_isbn(
                    volume_info.get("industryIdentifiers", [])
                )

                result = GoogleBooksSearchResult(
                    id=item.get("id", ""),
                    title=volume_info.get("title", ""),
                    authors=volume_info.get("authors", []),
                    published_date=volume_info.get("publishedDate"),
                    isbn_10=isbn_10,
                    isbn_13=isbn_13,
                    cover_url=_extract_cover_url(volume_info.get("imageLinks")),
                    description=volume_info.get("description"),
                )
                results.append(result)

            logger.info(
                "Google Books search complete",
                query=query,
                results_found=len(results),
            )
            return results

    except Exception as e:
        logger.error("Error searching Google Books", query=query, error=str(e))
        return []


async def search_google_books_by_author(
    session: ClientSession,
    author_name: str,
    max_results: int = 40,
) -> list[GoogleBooksSearchResult]:
    """
    Search Google Books for all books by an author.
    Uses the `inauthor:` filter for comprehensive results.
    """
    logger.debug(
        "Searching Google Books by author",
        author_name=author_name,
        max_results=max_results,
    )

    # Use special inauthor: filter for author search
    query = f'inauthor:"{author_name}"'
    return await search_google_books(session, query, max_results)


async def get_google_books_by_isbn(
    session: ClientSession,
    isbn: str,
) -> GoogleBooksSearchResult | None:
    """Lookup a specific book by ISBN."""
    logger.debug("Fetching Google Books by ISBN", isbn=isbn)

    url = "https://www.googleapis.com/books/v1/volumes"
    params = {
        "q": f"isbn:{isbn}",
        "maxResults": 1,
    }

    try:
        async with session.get(url, params=params) as response:
            if not response.ok:
                return None

            data = await response.json()
            items = data.get("items", [])

            if not items:
                return None

            item = items[0]
            volume_info = item.get("volumeInfo", {})

            isbn_10, isbn_13 = _extract_isbn(
                volume_info.get("industryIdentifiers", [])
            )

            return GoogleBooksSearchResult(
                id=item.get("id", ""),
                title=volume_info.get("title", ""),
                authors=volume_info.get("authors", []),
                published_date=volume_info.get("publishedDate"),
                isbn_10=isbn_10,
                isbn_13=isbn_13,
                cover_url=_extract_cover_url(volume_info.get("imageLinks")),
                description=volume_info.get("description"),
            )

    except Exception as e:
        logger.error("Error fetching Google Books by ISBN", isbn=isbn, error=str(e))
        return None


def google_books_result_to_audiobook(
    result: GoogleBooksSearchResult,
    source: str = "google_books",
) -> Audiobook:
    """Convert a Google Books search result to an Audiobook object."""
    # Parse release date
    release_date = None
    if result.published_date:
        try:
            release_date = datetime.fromisoformat(result.published_date)
        except (ValueError, TypeError):
            pass

    return Audiobook(
        title=result.title,
        subtitle=None,
        authors=result.authors,
        narrators=[],  # Google Books doesn't have narrators
        cover_image=result.cover_url,
        release_date=release_date,
        runtime_length_min=None,  # Google Books doesn't have runtime
        isbn_10=result.isbn_10,
        isbn_13=result.isbn_13,
        google_books_id=result.id,
        source=source,
    )
