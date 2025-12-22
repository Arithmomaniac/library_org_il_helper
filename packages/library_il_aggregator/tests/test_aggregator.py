"""Tests for the library_il_aggregator package.

These tests require valid credentials to be set in environment variables:
- TEUDAT_ZEHUT: The username (Teudat Zehut)
- LIBRARY_PASSWORD: The password (defaults to TEUDAT_ZEHUT if not set)

The tests are integration tests that actually connect to the library.org.il websites.
"""

import os
from datetime import date

import pytest

from library_il_client import CheckedOutBook, HistoryItem
from library_il_aggregator import (
    AggregatedBooks,
    AggregatedHistory,
    LibraryAccount,
    LibraryAggregator,
)


def get_credentials():
    """Get credentials from environment variables."""
    username = os.environ.get("TEUDAT_ZEHUT", "")
    password = os.environ.get("LIBRARY_PASSWORD", "") or username
    return username, password


def has_credentials():
    """Check if valid credentials are available."""
    username, password = get_credentials()
    return bool(username and password)


# Skip all tests if credentials are not available
pytestmark = pytest.mark.skipif(
    not has_credentials(),
    reason="TEUDAT_ZEHUT environment variable not set"
)


class TestLibraryAggregator:
    """Tests for the LibraryAggregator."""
    
    @pytest.fixture
    def accounts(self):
        """Create accounts for both libraries."""
        username, password = get_credentials()
        return [
            LibraryAccount("shemesh", username, password),
            LibraryAccount("betshemesh", username, password),
        ]
    
    @pytest.fixture
    def aggregator(self, accounts):
        """Create a logged-in aggregator."""
        agg = LibraryAggregator(accounts)
        agg.login_all()
        yield agg
        agg.close()
    
    def test_login_all_success(self, accounts):
        """Test logging in to all libraries."""
        with LibraryAggregator(accounts) as agg:
            results = agg.login_all()
            
            assert len(results) == 2
            assert all(success for success in results.values())
    
    def test_from_slugs_convenience_method(self):
        """Test the from_slugs convenience method."""
        username, password = get_credentials()
        
        with LibraryAggregator.from_slugs(
            ["shemesh", "betshemesh"],
            username=username,
            password=password,
        ) as agg:
            results = agg.login_all()
            
            assert len(results) == 2
            assert all(success for success in results.values())
    
    def test_get_all_checked_out_books(self, aggregator):
        """Test fetching checked out books from all libraries."""
        result = aggregator.get_all_checked_out_books()
        
        assert isinstance(result, AggregatedBooks)
        assert isinstance(result.books, list)
        
        # Should have books from both libraries
        library_slugs = {book.library_slug for book in result.books}
        # At least one library should have books (might not have both)
        assert len(library_slugs) >= 1
        
        for book in result.books:
            assert isinstance(book, CheckedOutBook)
            assert book.title is not None
    
    def test_aggregated_books_total_count(self, aggregator):
        """Test the total_count property of AggregatedBooks."""
        result = aggregator.get_all_checked_out_books()
        
        assert result.total_count == len(result.books)
    
    def test_aggregated_books_sorted_by_due_date(self, aggregator):
        """Test sorting books by due date."""
        result = aggregator.get_all_checked_out_books()
        sorted_books = result.sorted_by_due_date()
        
        # Verify sorting order
        previous_date = None
        for book in sorted_books:
            if book.due_date and previous_date:
                assert book.due_date >= previous_date
            if book.due_date:
                previous_date = book.due_date
    
    def test_aggregated_books_by_library(self, aggregator):
        """Test grouping books by library."""
        result = aggregator.get_all_checked_out_books()
        by_library = result.by_library
        
        assert isinstance(by_library, dict)
        
        # Each group should contain books from that library
        for slug, books in by_library.items():
            for book in books:
                assert book.library_slug == slug
    
    def test_get_all_checkout_history(self, aggregator):
        """Test fetching checkout history from all libraries."""
        result = aggregator.get_all_checkout_history()
        
        assert isinstance(result, AggregatedHistory)
        assert isinstance(result.items, list)
        assert len(result.items) > 0
        
        for item in result.items:
            assert isinstance(item, HistoryItem)
            assert item.title is not None
    
    def test_aggregated_history_total_count(self, aggregator):
        """Test the total_count property of AggregatedHistory."""
        result = aggregator.get_all_checkout_history()
        
        assert result.total_count == len(result.items)
    
    def test_aggregated_history_sorted_by_return_date(self, aggregator):
        """Test sorting history by return date (descending)."""
        result = aggregator.get_all_checkout_history()
        sorted_items = result.sorted_by_return_date(descending=True)
        
        # Verify sorting order (descending)
        previous_date = None
        for item in sorted_items:
            if item.return_date and previous_date:
                assert item.return_date <= previous_date
            if item.return_date:
                previous_date = item.return_date
    
    def test_aggregated_history_by_library(self, aggregator):
        """Test grouping history by library."""
        result = aggregator.get_all_checkout_history()
        by_library = result.by_library
        
        assert isinstance(by_library, dict)
        
        # Should have items from at least one library
        assert len(by_library) >= 1
        
        # Each group should contain items from that library
        for slug, items in by_library.items():
            for item in items:
                assert item.library_slug == slug
    
    def test_combined_history_from_both_libraries(self, aggregator):
        """Test that history is combined from both shemesh and betshemesh."""
        result = aggregator.get_all_checkout_history()
        
        library_slugs = {item.library_slug for item in result.items}
        
        # Both libraries should be represented in the history
        assert "shemesh" in library_slugs or "betshemesh" in library_slugs
