"""Aggregator for combining data from multiple library.org.il websites."""

from __future__ import annotations

import asyncio
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
    Aggregates library data from multiple library.org.il accounts using async operations.
    
    This class manages multiple LibraryClient instances and combines their
    data into unified views. It supports:
    - Multiple libraries
    - Multiple accounts at the same library (e.g., family members)
    - Different credentials per library
    - Parallel fetching for improved performance
    
    Example with multiple accounts:
        >>> accounts = [
        ...     LibraryAccount("shemesh", "user1_tz", "user1_pass", label="parent"),
        ...     LibraryAccount("shemesh", "user2_tz", "user2_pass", label="child"),
        ...     LibraryAccount("betshemesh", "user1_tz", "user1_pass"),
        ... ]
        >>> async with LibraryAggregator(accounts) as aggregator:
        ...     await aggregator.login_all()
        ...     all_books = await aggregator.get_all_checked_out_books()
        ...     for book in all_books.sorted_by_due_date():
        ...         print(f"[{book.library_slug}] {book.title}")
    
    Simple usage with same credentials:
        >>> async with LibraryAggregator.from_slugs(
        ...     ["shemesh", "betshemesh"],
        ...     username="your_tz",
        ...     password="your_pass"
        ... ) as aggregator:
        ...     await aggregator.login_all()
        ...     books = await aggregator.get_all_checked_out_books()
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
    
    async def __aenter__(self) -> "LibraryAggregator":
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
    
    async def close(self) -> None:
        """Close all library clients."""
        # Close all clients in parallel
        close_tasks = [client.close() for client in self._clients.values()]
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
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
    
    async def login(self, account: LibraryAccount) -> bool:
        """
        Login to a specific library account.
        
        Args:
            account: The LibraryAccount to login to.
            
        Returns:
            True if login succeeded, False otherwise.
        """
        client = self._get_or_create_client(account)
        try:
            await client.login(account.username, account.password)
            self._logged_in.add(account.account_id)
            return True
        except LoginError:
            return False
    
    async def login_all(self) -> dict[str, bool]:
        """
        Login to all configured library accounts in parallel.
        
        Returns:
            Dictionary mapping account_id to login success status.
        """
        # Create login tasks for all accounts in parallel
        login_tasks = [self.login(account) for account in self.accounts]
        results = await asyncio.gather(*login_tasks, return_exceptions=True)
        
        # Build results dictionary
        return {
            account.account_id: result if not isinstance(result, Exception) else False
            for account, result in zip(self.accounts, results)
        }
    
    async def get_all_checked_out_books(self) -> AggregatedBooks:
        """
        Get checked out books from all logged-in library accounts in parallel.
        
        Returns:
            AggregatedBooks containing books from all accounts.
        """
        result = AggregatedBooks(libraries=list(self._logged_in))
        
        # Create tasks to fetch books from all accounts in parallel
        async def fetch_books_for_account(account: LibraryAccount) -> tuple[str, list, Optional[str]]:
            account_id = account.account_id
            if account_id not in self._logged_in:
                return account_id, [], None
            
            client = self._clients.get(account_id)
            if not client:
                return account_id, [], None
            
            try:
                books = await client.get_checked_out_books()
                # Attach account_id to each book for proper labeling
                for book in books:
                    book.account_id = account_id
                return account_id, books, None
            except Exception as e:
                return account_id, [], str(e)
        
        # Fetch from all accounts in parallel
        tasks = [fetch_books_for_account(account) for account in self.accounts]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for result_item in results_list:
            if isinstance(result_item, Exception):
                continue
            account_id, books, error = result_item
            if error:
                result.errors[account_id] = error
            else:
                result.books.extend(books)
        
        return result
    
    async def get_all_checkout_history(self) -> AggregatedHistory:
        """
        Get checkout history from all logged-in library accounts in parallel.
        
        Returns:
            AggregatedHistory containing history from all accounts.
        """
        result = AggregatedHistory(libraries=list(self._logged_in))
        
        # Create tasks to fetch history from all accounts in parallel
        async def fetch_history_for_account(account: LibraryAccount) -> tuple[str, list, Optional[str]]:
            account_id = account.account_id
            if account_id not in self._logged_in:
                return account_id, [], None
            
            client = self._clients.get(account_id)
            if not client:
                return account_id, [], None
            
            try:
                history = await client.get_checkout_history()
                # Attach account_id to each history item for proper labeling
                for item in history.items:
                    item.account_id = account_id
                return account_id, history.items, None
            except Exception as e:
                return account_id, [], str(e)
        
        # Fetch from all accounts in parallel
        tasks = [fetch_history_for_account(account) for account in self.accounts]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for result_item in results_list:
            if isinstance(result_item, Exception):
                continue
            account_id, items, error = result_item
            if error:
                result.errors[account_id] = error
            else:
                result.items.extend(items)
        
        return result
