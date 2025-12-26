"""Data models for library.org.il interactions."""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class CheckedOutBook:
    """Represents a book that is currently checked out."""
    
    title: str
    author: Optional[str] = None
    barcode: Optional[str] = None
    media_type: Optional[str] = None  # e.g., "ספרים" (books), "סרטים" (movies)
    checkout_date: Optional[date] = None
    due_date: Optional[date] = None
    library_slug: Optional[str] = None
    can_renew: bool = True
    
    def __str__(self) -> str:
        due_str = f" (due: {self.due_date})" if self.due_date else ""
        author_str = f" by {self.author}" if self.author else ""
        return f"{self.title}{author_str}{due_str}"


@dataclass
class HistoryItem:
    """Represents a book from checkout history."""
    
    title: str
    author: Optional[str] = None
    barcode: Optional[str] = None
    media_type: Optional[str] = None  # e.g., "ספרים" (books), "סרטים" (movies)
    checkout_date: Optional[date] = None
    return_date: Optional[date] = None
    library_slug: Optional[str] = None
    
    def __str__(self) -> str:
        author_str = f" by {self.author}" if self.author else ""
        date_str = ""
        if self.checkout_date and self.return_date:
            date_str = f" ({self.checkout_date} - {self.return_date})"
        elif self.return_date:
            date_str = f" (returned: {self.return_date})"
        return f"{self.title}{author_str}{date_str}"


@dataclass
class RenewalResult:
    """Result of a book renewal attempt."""
    
    book: CheckedOutBook
    success: bool
    message: str = ""
    new_due_date: Optional[date] = None
    
    def __str__(self) -> str:
        status = "✓" if self.success else "✗"
        msg = f" - {self.message}" if self.message else ""
        return f"{status} {self.book.title}{msg}"


@dataclass  
class PaginatedHistory:
    """Paginated checkout history results."""
    
    items: list[HistoryItem] = field(default_factory=list)
    page: int = 1
    total_pages: int = 1
    total_items: Optional[int] = None
    has_next: bool = False
    has_previous: bool = False


@dataclass
class SearchResult:
    """Represents a book from search results."""
    
    title: str
    author: Optional[str] = None
    classification: Optional[str] = None  # מס' מיון - classification number
    shelf_sign: Optional[str] = None  # סימן מדף
    series: Optional[str] = None  # סדרה
    series_number: Optional[str] = None  # מס' בסדרה
    title_id: Optional[str] = None  # Internal ID for the book
    library_slug: Optional[str] = None
    
    def __str__(self) -> str:
        author_str = f" / {self.author}" if self.author else ""
        return f"{self.title}{author_str}"
    
    def metadata_key(self) -> tuple:
        """Return a tuple of all metadata fields for comparison/deduplication."""
        return (
            self.title,
            self.author,
            self.classification,
            self.shelf_sign,
            self.series,
            self.series_number,
        )
    
    def title_author_key(self) -> tuple:
        """Return a tuple of title and author for matching."""
        return (self.title, self.author)
    
    def title_key(self) -> str:
        """Return just the title for matching."""
        return self.title


@dataclass
class SearchResults:
    """Paginated search results."""
    
    items: list[SearchResult] = field(default_factory=list)
    total_count: int = 0
    page: int = 1
    total_pages: int = 1
    library_slug: Optional[str] = None
    
    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages
    
    @property
    def has_previous(self) -> bool:
        return self.page > 1
