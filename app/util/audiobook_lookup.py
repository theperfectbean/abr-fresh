"""
Utility functions for looking up audiobooks by various identifiers.
Bridges ASIN-based API with UUID-based database.
"""

import uuid
from sqlmodel import Session, select, col
from app.internal.models import Audiobook


async def get_audiobook_by_asin(session: Session, asin: str) -> Audiobook | None:
    """Lookup audiobook by ASIN (for backward compatibility)."""
    return session.exec(select(Audiobook).where(col(Audiobook.asin) == asin)).first()


def get_audiobook_by_id(session: Session, audiobook_id: uuid.UUID) -> Audiobook | None:
    """Lookup audiobook by UUID."""
    return session.exec(
        select(Audiobook).where(col(Audiobook.id) == audiobook_id)
    ).first()


def resolve_audiobook_identifier(session: Session, identifier: str) -> Audiobook | None:
    """
    Resolve an audiobook by either ASIN (10-36 chars) or UUID.
    Returns the Audiobook if found, None otherwise.
    """
    # Try UUID first
    try:
        audiobook_id = uuid.UUID(identifier)
        return get_audiobook_by_id(session, audiobook_id)
    except ValueError:
        pass

    # Fall back to ASIN
    return get_audiobook_by_asin(session, identifier)
