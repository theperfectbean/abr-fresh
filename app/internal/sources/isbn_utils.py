"""
ISBN conversion and validation utilities.
Supports ISBN-10 to ISBN-13 conversion and vice versa.
"""

import re


def validate_isbn10(isbn: str) -> bool:
    """Validate ISBN-10 format and checksum."""
    isbn = isbn.replace("-", "").replace(" ", "")
    if len(isbn) != 10:
        return False
    if not isbn[:-1].isdigit() or not (isbn[-1].isdigit() or isbn[-1].upper() == "X"):
        return False

    # Validate checksum
    total = sum((10 - i) * int(isbn[i]) for i in range(9))
    check = isbn[9].upper()
    expected = (10 - (total % 10)) % 10
    return check == (str(expected) if expected != 10 else "X")


def validate_isbn13(isbn: str) -> bool:
    """Validate ISBN-13 format and checksum."""
    isbn = isbn.replace("-", "").replace(" ", "")
    if len(isbn) != 13 or not isbn.isdigit():
        return False

    # Validate checksum
    total = sum(int(isbn[i]) * (1 if i % 2 == 0 else 3) for i in range(12))
    check = (10 - (total % 10)) % 10
    return int(isbn[12]) == check


def isbn10_to_isbn13(isbn10: str) -> str | None:
    """
    Convert ISBN-10 to ISBN-13.
    Returns None if the ISBN-10 is invalid.
    """
    isbn10 = isbn10.replace("-", "").replace(" ", "").upper()

    if not validate_isbn10(isbn10):
        return None

    # ISBN-13 always starts with 978 or 979
    # Most pre-2007 books use 978
    isbn13_base = "978" + isbn10[:-1]

    # Calculate checksum
    total = sum(int(isbn13_base[i]) * (1 if i % 2 == 0 else 3) for i in range(12))
    check = (10 - (total % 10)) % 10

    return isbn13_base + str(check)


def isbn13_to_isbn10(isbn13: str) -> str | None:
    """
    Convert ISBN-13 to ISBN-10.
    Only works for ISBN-13s starting with 978.
    Returns None for 979 ISBN-13s or invalid inputs.
    """
    isbn13 = isbn13.replace("-", "").replace(" ", "")

    if not validate_isbn13(isbn13):
        return None

    # Only 978 prefix can be converted to ISBN-10
    if not isbn13.startswith("978"):
        return None

    isbn10_base = isbn13[3:-1]  # Remove 978 and check digit

    # Calculate ISBN-10 checksum
    total = sum((10 - i) * int(isbn10_base[i]) for i in range(9))
    check = (10 - (total % 10)) % 10
    check_char = str(check) if check != 10 else "X"

    return isbn10_base + check_char


def normalize_isbn(isbn: str) -> str:
    """Remove hyphens and spaces from ISBN."""
    return isbn.replace("-", "").replace(" ", "")


def is_isbn(value: str) -> bool:
    """Check if value looks like an ISBN (10 or 13 digits)."""
    clean = normalize_isbn(value).upper()
    if len(clean) == 10:
        return clean[:-1].isdigit() and (clean[-1].isdigit() or clean[-1] == "X")
    elif len(clean) == 13:
        return clean.isdigit() and clean.startswith(("978", "979"))
    return False


def is_asin(value: str) -> bool:
    """Check if value looks like an ASIN (10 alphanumeric characters)."""
    return len(value) == 10 and value.replace("-", "").isalnum()
