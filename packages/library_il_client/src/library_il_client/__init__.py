"""
Library IL Client - A utility library for interacting with library.org.il websites.

This library provides functionality to:
- Login to Israeli public library websites
- Get currently checked out books
- Renew checked out books
- Get checkout history with pagination
"""

from library_il_client.client import (
    LibraryClient,
    LibraryClientError,
    LoginError,
    SessionExpiredError,
)
from library_il_client.models import (
    BookCopy,
    BookDetails,
    CheckedOutBook,
    HistoryItem,
    PaginatedHistory,
    RenewalResult,
    SearchResult,
    SearchResults,
)

__all__ = [
    "LibraryClient",
    "LibraryClientError",
    "LoginError",
    "SessionExpiredError",
    "BookCopy",
    "BookDetails",
    "CheckedOutBook",
    "HistoryItem",
    "PaginatedHistory",
    "RenewalResult",
    "SearchResult",
    "SearchResults",
]
