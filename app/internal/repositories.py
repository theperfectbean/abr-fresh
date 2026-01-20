"""
Repository layer for data access with explicit eager-loading and batch operations.

This layer isolates ORM interactions and provides strongly-typed queries that avoid N+1 problems.
"""

import uuid
from typing import Optional

from sqlmodel import Session, col, select

from app.internal.models import Audiobook, AudiobookRequest


class AudiobookRepository:
    """Repository for Audiobook data access."""

    session: Session

    def __init__(self, session: Session):
        self.session = session

    def get_by_asin(self, asin: str) -> Optional[Audiobook]:
        """Get audiobook by ASIN."""
        statement = select(Audiobook).where(col(Audiobook.asin) == asin)
        return self.session.exec(statement).first()

    def get_by_id(self, audiobook_id: uuid.UUID) -> Optional[Audiobook]:
        """Get audiobook by ID."""
        statement = select(Audiobook).where(col(Audiobook.id) == audiobook_id)
        return self.session.exec(statement).first()

    def get_many_by_asins(self, asins: set[str]) -> dict[str, Audiobook]:
        """
        Batch fetch audiobooks by ASINs.

        Returns a dict mapping ASIN -> Audiobook for efficient lookup.
        """
        if not asins:
            return {}

        statement = select(Audiobook).where(col(Audiobook.asin).in_(asins))
        books = self.session.exec(statement).all()
        return {book.asin: book for book in books if book.asin}

    def get_many_by_ids(self, audiobook_ids: list[uuid.UUID]) -> list[Audiobook]:
        """
        Batch fetch audiobooks by IDs.

        Preserves the order of the input IDs.
        """
        if not audiobook_ids:
            return []

        statement = select(Audiobook).where(col(Audiobook.id).in_(audiobook_ids))
        books = self.session.exec(statement).all()

        # Preserve order of input IDs
        book_map = {book.id: book for book in books}
        return [book_map[book_id] for book_id in audiobook_ids if book_id in book_map]


class AudiobookRequestRepository:
    """Repository for AudiobookRequest data access."""

    session: Session

    def __init__(self, session: Session):
        self.session = session

    def get_by_audiobook_and_user(
        self, audiobook_id: uuid.UUID, username: str
    ) -> Optional[AudiobookRequest]:
        """Get a single request by audiobook ID and username."""
        statement = (
            select(AudiobookRequest)
            .where(col(AudiobookRequest.audiobook_id) == audiobook_id)
            .where(col(AudiobookRequest.user_username) == username)
        )
        return self.session.exec(statement).first()

    def count_by_audiobook_id(self, audiobook_id: uuid.UUID) -> int:
        """Count requests for a specific audiobook."""
        statement = select(Audiobook).where(col(Audiobook.id) == audiobook_id)
        audiobook = self.session.exec(statement).first()
        if not audiobook:
            return 0
        return len(audiobook.requests)

    def count_requests_by_audiobook_ids(
        self, audiobook_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        """
        Batch count requests per audiobook ID.

        Returns a dict mapping audiobook_id -> request_count.
        """
        if not audiobook_ids:
            return {}

        # Fetch all audiobooks with their requests
        statement = select(Audiobook).where(col(Audiobook.id).in_(audiobook_ids))
        audiobooks = self.session.exec(statement).all()

        # Build count dict
        counts: dict[uuid.UUID, int] = {}
        for audiobook in audiobooks:
            counts[audiobook.id] = len(audiobook.requests)

        # Ensure all requested IDs are in the dict (even if they have 0 requests)
        for audiobook_id in audiobook_ids:
            if audiobook_id not in counts:
                counts[audiobook_id] = 0

        return counts

    def get_all_for_audiobook(self, audiobook_id: uuid.UUID) -> list[AudiobookRequest]:
        """Get all requests for a specific audiobook."""
        statement = select(AudiobookRequest).where(
            col(AudiobookRequest.audiobook_id) == audiobook_id
        )
        return list(self.session.exec(statement).all())

    def get_all_for_user(self, username: str) -> list[AudiobookRequest]:
        """Get all requests made by a specific user."""
        statement = select(AudiobookRequest).where(
            col(AudiobookRequest.user_username) == username
        )
        return list(self.session.exec(statement).all())

    def has_user_requested_audiobook(
        self, audiobook_id: uuid.UUID, username: str
    ) -> bool:
        """Check if a specific user has requested an audiobook."""
        return self.get_by_audiobook_and_user(audiobook_id, username) is not None
