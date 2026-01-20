"""
Multi-source book discovery and search integration.
Supports Audible, Google Books, OpenLibrary, and more.
"""

from app.internal.sources.isbn_utils import (
    validate_isbn10,
    validate_isbn13,
    isbn10_to_isbn13,
    isbn13_to_isbn10,
    normalize_isbn,
    is_isbn,
    is_asin,
)
from app.internal.sources.google_books_api import (
    search_google_books,
    search_google_books_by_author,
    get_google_books_by_isbn,
    google_books_result_to_audiobook,
)
from app.internal.sources.openlibrary_api import (
    search_openlibrary,
    search_openlibrary_by_author,
    get_openlibrary_by_isbn,
    openlibrary_result_to_audiobook,
)
from app.internal.sources.unified_search import (
    unified_search,
    search_author_books,
)

__all__ = [
    # ISBN utilities
    "validate_isbn10",
    "validate_isbn13",
    "isbn10_to_isbn13",
    "isbn13_to_isbn10",
    "normalize_isbn",
    "is_isbn",
    "is_asin",
    # Google Books
    "search_google_books",
    "search_google_books_by_author",
    "get_google_books_by_isbn",
    "google_books_result_to_audiobook",
    # OpenLibrary
    "search_openlibrary",
    "search_openlibrary_by_author",
    "get_openlibrary_by_isbn",
    "openlibrary_result_to_audiobook",
    # Unified search
    "unified_search",
    "search_author_books",
]
