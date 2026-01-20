"""
Book discovery and browsing routes.
Includes author browse, genre browse, and direct lookups.
"""

from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, HTTPException, Query, Security
from sqlmodel import Session

from app.internal.auth.authentication import APIKeyAuth, DetailedUser
from app.internal.sources.unified_search import search_author_books
from app.internal.models import AudiobookSearchResult
from app.util.connection import get_connection
from app.util.db import get_session

router = APIRouter(prefix="/browse", tags=["Browse"])


@router.get("/author", response_model=list[AudiobookSearchResult])
async def browse_author(
    author_name: Annotated[str, Query(..., description="Author name to search for")],
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(APIKeyAuth())],
    max_results: int = 100,
    page: int = 0,
):
    """
    Browse all books by a specific author from multiple sources.

    This is a comprehensive author bibliography that combines:
    - Google Books (best metadata)
    - OpenLibrary (comprehensive coverage)
    - Audible (ASIN enrichment)

    Results are deduplicated by ISBN and ranked by metadata completeness.
    Books with ASIN are marked as "On Audible" and can be requested.
    Books without ASIN are marked as "Not on Audible" (informational only).
    """
    if not author_name or len(author_name.strip()) < 2:
        raise HTTPException(
            status_code=400,
            detail="Author name must be at least 2 characters",
        )

    try:
        books = await search_author_books(
            session=session,
            client_session=client_session,
            author_name=author_name.strip(),
            num_results=max_results,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to search for author: {str(e)}",
        )

    # Apply pagination
    start = page * 30  # 30 results per page
    end = start + 30
    paginated_books = books[start:end]

    return [
        AudiobookSearchResult(
            book=book,
            requests=book.requests,
            username=user.username,
        )
        for book in paginated_books
    ]


@router.get("/author/{author_name}/count")
async def author_book_count(
    author_name: Annotated[str, ...],
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(APIKeyAuth())],
):
    """
    Get the total count of books by an author without pagination.
    """
    if not author_name or len(author_name.strip()) < 2:
        raise HTTPException(
            status_code=400,
            detail="Author name must be at least 2 characters",
        )

    try:
        books = await search_author_books(
            session=session,
            client_session=client_session,
            author_name=author_name.strip(),
            num_results=1000,  # Get comprehensive count
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to count author books: {str(e)}",
        )

    # Count books with ASIN (available on Audible)
    available_count = sum(1 for book in books if book.asin)

    return {
        "author_name": author_name,
        "total_books": len(books),
        "available_on_audible": available_count,
        "not_available_on_audible": len(books) - available_count,
    }
