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
    CheckedOutBook,
    HistoryItem,
    PaginatedHistory,
    RenewalResult,
)

__all__ = [
    "LibraryClient",
    "LibraryClientError",
    "LoginError",
    "SessionExpiredError",
    "CheckedOutBook",
    "HistoryItem",
    "PaginatedHistory",
    "RenewalResult",
]
