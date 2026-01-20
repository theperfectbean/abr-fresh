"""
Data Transfer Objects (DTOs) for the search pipeline.

These DTOs decouple the search results from ORM objects, preventing ObjectDeletedError
when cached results are accessed after database cleanup.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.internal.models import Audiobook, AudiobookRequest


class SearchResultDTO(BaseModel):
    """Lightweight DTO for search results - can be safely cached without ORM issues."""

    # Primary identifiers
    audiobook_id: uuid.UUID
    asin: Optional[str] = None

    # Basic metadata
    title: str
    subtitle: Optional[str] = None
    authors: list[str] = []
    narrators: list[str] = []

    # Media
    cover_image: Optional[str] = None
    runtime_length_min: Optional[int] = None

    # Alternative identifiers for hybrid search
    isbn_10: Optional[str] = None
    isbn_13: Optional[str] = None
    google_books_id: Optional[str] = None

    # Source tracking
    source: str = "audible"

    # Metadata
    release_date: Optional[datetime] = None
    updated_at: datetime
    downloaded: bool = False

    # Request info (calculated, not from ORM)
    request_count: int = 0
    user_has_requested: bool = False

    @property
    def runtime_length_hrs(self) -> Optional[float]:
        """Convert minutes to hours."""
        if self.runtime_length_min is None:
            return None
        return round(self.runtime_length_min / 60, 1)

    @classmethod
    def from_audiobook_orm(cls, audiobook: Audiobook) -> "SearchResultDTO":
        """Create DTO from ORM object."""
        return cls(
            audiobook_id=audiobook.id,
            asin=audiobook.asin,
            title=audiobook.title,
            subtitle=audiobook.subtitle,
            authors=audiobook.authors,
            narrators=audiobook.narrators,
            cover_image=audiobook.cover_image,
            runtime_length_min=audiobook.runtime_length_min,
            isbn_10=audiobook.isbn_10,
            isbn_13=audiobook.isbn_13,
            google_books_id=audiobook.google_books_id,
            source=audiobook.source,
            release_date=audiobook.release_date,
            updated_at=audiobook.updated_at,
            downloaded=audiobook.downloaded,
        )

    @classmethod
    def from_audible_api(
        cls,
        title: str,
        asin: Optional[str] = None,
        subtitle: Optional[str] = None,
        authors: Optional[list[str]] = None,
        narrators: Optional[list[str]] = None,
        cover_image: Optional[str] = None,
        runtime_length_min: Optional[int] = None,
        release_date: Optional[datetime] = None,
        isbn_10: Optional[str] = None,
        isbn_13: Optional[str] = None,
    ) -> "SearchResultDTO":
        """Create DTO from Audible API response."""
        now = datetime.now()
        return cls(
            audiobook_id=uuid.uuid4(),  # Temporary ID, will be replaced when stored in DB
            asin=asin,
            title=title,
            subtitle=subtitle,
            authors=authors or [],
            narrators=narrators or [],
            cover_image=cover_image,
            runtime_length_min=runtime_length_min,
            isbn_10=isbn_10,
            isbn_13=isbn_13,
            google_books_id=None,
            source="audible",
            release_date=release_date,
            updated_at=now,
            downloaded=False,
        )

    def with_request_count(self, count: int) -> "SearchResultDTO":
        """Return a copy of this DTO with the request count set."""
        return self.model_copy(update={"request_count": count})

    def with_user_request_status(self, has_requested: bool) -> "SearchResultDTO":
        """Return a copy of this DTO with the user request status set."""
        return self.model_copy(update={"user_has_requested": has_requested})


class AudiobookWishlistDTO(BaseModel):
    """DTO for wishlist items with request metadata."""

    audiobook_id: uuid.UUID
    asin: Optional[str] = None
    title: str
    subtitle: Optional[str] = None
    authors: list[str] = []
    narrators: list[str] = []
    cover_image: Optional[str] = None
    runtime_length_min: Optional[int] = None
    source: str = "audible"
    downloaded: bool = False
    request_count: int = 0
    requested_by_usernames: list[str] = []
    download_error: Optional[str] = None

    @property
    def runtime_length_hrs(self) -> Optional[float]:
        if self.runtime_length_min is None:
            return None
        return round(self.runtime_length_min / 60, 1)

    @classmethod
    def from_orm_and_requests(
        cls,
        audiobook: Audiobook,
        requests: list[AudiobookRequest],
        download_error: Optional[str] = None,
    ) -> "AudiobookWishlistDTO":
        """Create wishlist DTO from ORM objects."""
        return cls(
            audiobook_id=audiobook.id,
            asin=audiobook.asin,
            title=audiobook.title,
            subtitle=audiobook.subtitle,
            authors=audiobook.authors,
            narrators=audiobook.narrators,
            cover_image=audiobook.cover_image,
            runtime_length_min=audiobook.runtime_length_min,
            source=audiobook.source,
            downloaded=audiobook.downloaded,
            request_count=len(requests),
            requested_by_usernames=[req.user_username for req in requests],
            download_error=download_error,
        )
