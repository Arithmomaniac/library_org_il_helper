"""Data models for aggregated library data."""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from library_il_client import CheckedOutBook, HistoryItem, SearchResult


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


@dataclass
class LibrarySearchInfo:
    """Information about search results from a single library."""
    
    library_slug: str
    total_count: int
    fetched_count: int
    
    @property
    def has_more(self) -> bool:
        """Check if there are more results than were fetched."""
        return self.total_count > self.fetched_count


@dataclass
class CombinedSearchResult:
    """A search result that may combine books from multiple libraries.
    
    This represents either a single book or a group of books that are
    considered the same (matching title and author) across multiple libraries.
    
    Only logically common fields (title, author) are exposed at the top level.
    Library-specific fields (classification, shelf_sign, etc.) are accessed
    through the library_results list.
    """
    
    # Common fields (from highest-ranked result, deterministic on ties)
    title: str
    author: Optional[str] = None
    
    # All library-specific results for this book
    # Ordered by rank (best first), then alphabetically by library_slug for ties
    library_results: list[SearchResult] = field(default_factory=list)
    
    # Combined score based on library count and ranking position
    score: float = 0.0
    
    @property
    def library_slugs(self) -> list[str]:
        """Get all library slugs where this book was found."""
        seen = set()
        slugs = []
        for result in self.library_results:
            if result.library_slug and result.library_slug not in seen:
                slugs.append(result.library_slug)
                seen.add(result.library_slug)
        return slugs
    
    @property
    def library_count(self) -> int:
        """Number of libraries where this book was found."""
        return len(self.library_slugs)


@dataclass
class CombinedSearchResults:
    """Combined search results from multiple libraries."""
    
    # Merged and sorted results
    items: list[CombinedSearchResult] = field(default_factory=list)
    
    # Information about results from each library
    library_info: list[LibrarySearchInfo] = field(default_factory=list)
    
    # Errors encountered during search
    errors: dict[str, str] = field(default_factory=dict)
    
    @property
    def total_unique_count(self) -> int:
        """Total number of unique results (after merging)."""
        return len(self.items)
    
    @property
    def libraries_searched(self) -> list[str]:
        """List of library slugs that were searched."""
        return [info.library_slug for info in self.library_info]
    
    def get_warnings(self) -> list[str]:
        """Get warnings about libraries with more results than fetched."""
        warnings = []
        for info in self.library_info:
            if info.has_more:
                remaining = info.total_count - info.fetched_count
                warnings.append(
                    f"{info.library_slug}: {remaining} more results available "
                    f"(showing {info.fetched_count} of {info.total_count})"
                )
        return warnings
