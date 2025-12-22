"""Data models for aggregated library data."""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from library_il_client import CheckedOutBook, HistoryItem


@dataclass
class AggregatedBooks:
    """Aggregated checked out books from multiple libraries."""
    
    books: list[CheckedOutBook] = field(default_factory=list)
    libraries: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    
    @property
    def total_count(self) -> int:
        """Total number of books across all libraries."""
        return len(self.books)
    
    @property
    def by_library(self) -> dict[str, list[CheckedOutBook]]:
        """Books grouped by library slug."""
        result: dict[str, list[CheckedOutBook]] = {}
        for book in self.books:
            slug = book.library_slug or "unknown"
            if slug not in result:
                result[slug] = []
            result[slug].append(book)
        return result
    
    def sorted_by_due_date(self) -> list[CheckedOutBook]:
        """Get all books sorted by due date (earliest first)."""
        return sorted(
            self.books,
            key=lambda b: (b.due_date or date.max, b.title),
        )


@dataclass
class AggregatedHistory:
    """Aggregated checkout history from multiple libraries."""
    
    items: list[HistoryItem] = field(default_factory=list)
    libraries: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    
    @property
    def total_count(self) -> int:
        """Total number of history items across all libraries."""
        return len(self.items)
    
    @property
    def by_library(self) -> dict[str, list[HistoryItem]]:
        """History items grouped by library slug."""
        result: dict[str, list[HistoryItem]] = {}
        for item in self.items:
            slug = item.library_slug or "unknown"
            if slug not in result:
                result[slug] = []
            result[slug].append(item)
        return result
    
    def sorted_by_return_date(self, descending: bool = True) -> list[HistoryItem]:
        """Get all history items sorted by return date."""
        return sorted(
            self.items,
            key=lambda i: (i.return_date or date.min, i.title),
            reverse=descending,
        )
