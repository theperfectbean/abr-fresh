"""Google Books API integration for hybrid search."""

from aiohttp import ClientSession
from typing import Any
from app.util.log import logger

GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1/volumes"


async def search_google_books(
    session: ClientSession,
    query: str,
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """
    Search Google Books API for books.

    Args:
        session: aiohttp ClientSession
        query: Search query string
        max_results: Maximum number of results to return (default 20)

    Returns:
        List of Google Books volume items
    """
    params = {
        "q": query,
        "maxResults": min(max_results, 40),  # API limit
        "printType": "books",
    }

    logger.debug("Searching Google Books", query=query, max_results=max_results)

    try:
        async with session.get(GOOGLE_BOOKS_API, params=params) as resp:
            if not resp.ok:
                logger.error(
                    "Google Books API error",
                    status=resp.status,
                    text=await resp.text(),
                )
                return []

            data = await resp.json()
            items = data.get("items", [])
            logger.info("Google Books search complete", results=len(items))
            return items

    except Exception as e:
        logger.error("Failed to search Google Books", error=str(e))
        return []


def extract_isbns(volume_info: dict[str, Any]) -> tuple[str | None, str | None]:
    """
    Extract ISBN-10 and ISBN-13 from Google Books volume info.

    Args:
        volume_info: The volumeInfo dict from a Google Books item

    Returns:
        Tuple of (isbn_10, isbn_13), either may be None
    """
    isbn_10 = None
    isbn_13 = None

    for identifier in volume_info.get("industryIdentifiers", []):
        id_type = identifier.get("type")
        id_value = identifier.get("identifier", "").replace("-", "")

        if id_type == "ISBN_10":
            isbn_10 = id_value
        elif id_type == "ISBN_13":
            isbn_13 = id_value

    return isbn_10, isbn_13


def extract_basic_info(item: dict[str, Any]) -> dict[str, Any]:
    """
    Extract basic book information from a Google Books item.

    Args:
        item: A Google Books API item

    Returns:
        Dictionary with title, authors, description, etc.
    """
    volume_info = item.get("volumeInfo", {})

    return {
        "google_books_id": item.get("id"),
        "title": volume_info.get("title", ""),
        "subtitle": volume_info.get("subtitle"),
        "authors": volume_info.get("authors", []),
        "description": volume_info.get("description"),
        "publisher": volume_info.get("publisher"),
        "published_date": volume_info.get("publishedDate"),
        "page_count": volume_info.get("pageCount"),
        "cover_url": volume_info.get("imageLinks", {}).get("thumbnail"),
    }
