from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, HTTPException, Query, Security
from sqlmodel import Session

from app.internal import book_search
from app.internal.auth.authentication import APIKeyAuth, DetailedUser
from app.internal.book_search import (
    audible_region_type,
    audible_regions,
    clear_old_book_caches,
    get_region_from_settings,
    hybrid_search,
    list_audible_books,
)
from app.internal.models import AudiobookSearchResult
from app.util.connection import get_connection
from app.util.db import get_session

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("", response_model=list[AudiobookSearchResult])
async def search_books(
    client_session: Annotated[ClientSession, Depends(get_connection)],
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(APIKeyAuth())],
    query: Annotated[str | None, Query(alias="q")] = None,
    num_results: int = 20,
    page: int = 0,
    region: audible_region_type | None = None,
    use_hybrid: bool = True,  # Enable hybrid search by default
):
    if region is None:
        region = get_region_from_settings()
    if audible_regions.get(region) is None:
        raise HTTPException(status_code=400, detail="Invalid region")
    if query:
        clear_old_book_caches(session)
        
        # Use hybrid search (Audible + Google Books) or Audible-only
        if use_hybrid:
            results = await hybrid_search(
                session=session,
                client_session=client_session,
                query=query,
                region=region,
                num_results=num_results,
            )
            # Apply pagination
            start = page * num_results
            results = results[start : start + num_results]
        else:
            results = await list_audible_books(
                session=session,
                client_session=client_session,
                query=query,
                num_results=num_results,
                page=page,
                audible_region=region,
            )
    else:
        results = []

    # Convert results to include requests info
    response_results = []
    for book in results:
        # If book has requests relationship loaded, use it; otherwise, query separately
        if hasattr(book, "requests") and book.requests is not None:
            requests_list = book.requests
        else:
            # For books that aren't from the database session (e.g., from Google Books),
            # try to find them by ASIN and get their requests
            if book.asin:
                existing = session.exec(
                    select(Audiobook).where(Audiobook.asin == book.asin)
                ).first()
                requests_list = existing.requests if existing else []
            else:
                requests_list = []

        response_results.append(
            AudiobookSearchResult(
                book=book,
                requests=requests_list,
                username=user.username,
            )
        )

    return response_results


@router.get("/suggestions", response_model=list[str])
async def search_suggestions(
    query: Annotated[str, Query(alias="q")],
    _: Annotated[DetailedUser, Security(APIKeyAuth())],
    region: audible_region_type | None = None,
):
    if region is None:
        region = get_region_from_settings()
    async with ClientSession() as client_session:
        return await book_search.get_search_suggestions(client_session, query, region)
