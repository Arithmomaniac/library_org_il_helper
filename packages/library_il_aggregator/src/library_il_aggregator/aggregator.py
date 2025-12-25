"""Aggregator for combining data from multiple library.org.il websites."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from library_il_client import LibraryClient, LoginError

from library_il_aggregator.models import AggregatedBooks, AggregatedHistory


@dataclass
class LibraryAccount:
    """
    Represents credentials for a library account.
    
    Attributes:
        slug: Library identifier (e.g., "shemesh" for shemesh.library.org.il)
        username: Username (typically Teudat Zehut)
        password: Password for the account
        label: Optional label to distinguish multiple accounts at the same library
    """
    slug: str
    username: str
    password: str
    label: Optional[str] = None
    
    @property
    def account_id(self) -> str:
        """Unique identifier for this account (slug + username or label)."""
        if self.label:
            return f"{self.slug}:{self.label}"
        return f"{self.slug}:{self.username}"


class LibraryAggregator:
    """
    Aggregates library data from multiple library.org.il accounts.
    
    This class manages multiple LibraryClient instances and combines their
    data into unified views. It supports:
    - Multiple libraries
    - Multiple accounts at the same library (e.g., family members)
    - Different credentials per library
    
    Example with multiple accounts:
        >>> accounts = [
        ...     LibraryAccount("shemesh", "user1_tz", "user1_pass", label="parent"),
        ...     LibraryAccount("shemesh", "user2_tz", "user2_pass", label="child"),
        ...     LibraryAccount("betshemesh", "user1_tz", "user1_pass"),
        ... ]
        >>> with LibraryAggregator(accounts) as aggregator:
        ...     aggregator.login_all()
        ...     all_books = aggregator.get_all_checked_out_books()
        ...     for book in all_books.sorted_by_due_date():
        ...         print(f"[{book.library_slug}] {book.title}")
    
    Simple usage with same credentials:
        >>> with LibraryAggregator.from_slugs(
        ...     ["shemesh", "betshemesh"],
        ...     username="your_tz",
        ...     password="your_pass"
        ... ) as aggregator:
        ...     aggregator.login_all()
        ...     books = aggregator.get_all_checked_out_books()
    """
    
    def __init__(self, accounts: list[LibraryAccount]):
        """
        Initialize the aggregator with library accounts.
        
        Args:
            accounts: List of LibraryAccount objects with credentials for each library/account.
        """
        self.accounts = accounts
        self._clients: dict[str, LibraryClient] = {}  # account_id -> client
        self._logged_in: set[str] = set()  # account_ids that are logged in
    
    @classmethod
    def from_slugs(
        cls,
        slugs: list[str],
        username: str,
        password: str,
    ) -> "LibraryAggregator":
        """
        Create an aggregator using the same credentials for multiple libraries.
        
        This is a convenience method for when you use the same account across
        multiple libraries.
        
        Args:
            slugs: List of library identifiers
            username: Username (Teudat Zehut) to use for all libraries
            password: Password to use for all libraries
            
        Returns:
            LibraryAggregator configured with the specified libraries and credentials.
        """
        accounts = [
            LibraryAccount(slug=slug, username=username, password=password)
            for slug in slugs
        ]
        return cls(accounts)
    
    def __enter__(self) -> "LibraryAggregator":
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()
    
    def close(self) -> None:
        """Close all library clients."""
        for client in self._clients.values():
            client.close()
        self._clients.clear()
        self._logged_in.clear()
    
    def _get_or_create_client(self, account: LibraryAccount) -> LibraryClient:
        """Get or create a client for the specified account."""
        account_id = account.account_id
        if account_id not in self._clients:
            self._clients[account_id] = LibraryClient(
                account.slug,
                account.username,
                account.password,
            )
        return self._clients[account_id]
    
    def login(self, account: LibraryAccount) -> bool:
        """
        Login to a specific library account.
        
        Args:
            account: The LibraryAccount to login to.
            
        Returns:
            True if login succeeded, False otherwise.
        """
        client = self._get_or_create_client(account)
        try:
            client.login(account.username, account.password)
            self._logged_in.add(account.account_id)
            return True
        except LoginError:
            return False
    
    def login_all(self) -> dict[str, bool]:
        """
        Login to all configured library accounts.
        
        Returns:
            Dictionary mapping account_id to login success status.
        """
        results = {}
        for account in self.accounts:
            results[account.account_id] = self.login(account)
        return results
    
    def get_all_checked_out_books(self) -> AggregatedBooks:
        """
        Get checked out books from all logged-in library accounts.
        
        Returns:
            AggregatedBooks containing books from all accounts.
        """
        result = AggregatedBooks(libraries=list(self._logged_in))
        
        for account in self.accounts:
            account_id = account.account_id
            if account_id not in self._logged_in:
                continue
            
            client = self._clients.get(account_id)
            if not client:
                continue
            
            try:
                books = client.get_checked_out_books()
                # Attach account_id to each book for proper labeling
                for book in books:
                    book.account_id = account_id
                result.books.extend(books)
            except Exception as e:
                result.errors[account_id] = str(e)
        
        return result
    
    def get_all_checkout_history(self) -> AggregatedHistory:
        """
        Get checkout history from all logged-in library accounts.
        
        Returns:
            AggregatedHistory containing history from all accounts.
        """
        result = AggregatedHistory(libraries=list(self._logged_in))
        
        for account in self.accounts:
            account_id = account.account_id
            if account_id not in self._logged_in:
                continue
            
            client = self._clients.get(account_id)
            if not client:
                continue
            
            try:
                history = client.get_checkout_history()
                # Attach account_id to each history item for proper labeling
                for item in history.items:
                    item.account_id = account_id
                result.items.extend(history.items)
            except Exception as e:
                result.errors[account_id] = str(e)
        
        return result
