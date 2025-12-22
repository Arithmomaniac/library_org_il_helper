"""Tests for the library_il_client package.

These tests require valid credentials to be set in environment variables:
- TEUDAT_ZEHUT: The username (Teudat Zehut)
- LIBRARY_PASSWORD: The password (defaults to TEUDAT_ZEHUT if not set)

The tests are integration tests that actually connect to the library.org.il websites.
"""

import os
from datetime import date

import pytest

from library_il_client import (
    CheckedOutBook,
    HistoryItem,
    LibraryClient,
    LibraryClientError,
    LoginError,
    PaginatedHistory,
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


class TestLibraryClientShemesh:
    """Tests for the LibraryClient with the shemesh library."""
    
    @pytest.fixture
    def client(self):
        """Create a logged-in client for the shemesh library."""
        username, password = get_credentials()
        client = LibraryClient("shemesh", username, password)
        client.login()
        yield client
        client.close()
    
    def test_login_success(self):
        """Test successful login to shemesh library."""
        username, password = get_credentials()
        with LibraryClient("shemesh", username, password) as client:
            result = client.login()
            assert result is True
            assert client.is_logged_in is True
    
    def test_login_failure(self):
        """Test login failure with invalid credentials."""
        with LibraryClient("shemesh", "invalid_user", "invalid_pass") as client:
            with pytest.raises(LoginError):
                client.login()
    
    def test_get_checked_out_books(self, client):
        """Test fetching checked out books from shemesh library."""
        books = client.get_checked_out_books()
        
        assert isinstance(books, list)
        # All items should be CheckedOutBook instances
        for book in books:
            assert isinstance(book, CheckedOutBook)
            assert book.title is not None
            assert len(book.title) > 0
            assert book.library_slug == "shemesh"
    
    def test_checked_out_books_have_due_dates(self, client):
        """Test that checked out books have due dates."""
        books = client.get_checked_out_books()
        
        for book in books:
            if book.due_date:
                assert isinstance(book.due_date, date)
                # Due date should be in the future or today
                assert book.due_date >= date.today()
    
    def test_checked_out_books_have_barcodes(self, client):
        """Test that checked out books have barcodes for renewal."""
        books = client.get_checked_out_books()
        
        for book in books:
            # Barcode is required for renewal
            assert book.barcode is not None
            assert len(book.barcode) > 0
    
    def test_get_checkout_history(self, client):
        """Test fetching checkout history from shemesh library."""
        history = client.get_checkout_history()
        
        assert isinstance(history, PaginatedHistory)
        assert isinstance(history.items, list)
        
        # Should have some history items
        assert len(history.items) > 0
        
        for item in history.items:
            assert isinstance(item, HistoryItem)
            assert item.title is not None
            assert len(item.title) > 0
            assert item.library_slug == "shemesh"
    
    def test_checkout_history_has_return_dates(self, client):
        """Test that history items have return dates."""
        history = client.get_checkout_history()
        
        for item in history.items:
            if item.return_date:
                assert isinstance(item.return_date, date)
                # Return date should be in the past or today
                assert item.return_date <= date.today()
    
    def test_checkout_history_has_authors(self, client):
        """Test that history items have author information."""
        history = client.get_checkout_history()
        
        # At least some items should have authors
        items_with_authors = [item for item in history.items if item.author]
        assert len(items_with_authors) > 0
    
    def test_not_logged_in_raises_error(self):
        """Test that operations fail when not logged in."""
        with LibraryClient("shemesh") as client:
            with pytest.raises(LibraryClientError):
                client.get_checked_out_books()


class TestLibraryClientBetshemesh:
    """Tests for the LibraryClient with the betshemesh library."""
    
    @pytest.fixture
    def client(self):
        """Create a logged-in client for the betshemesh library."""
        username, password = get_credentials()
        client = LibraryClient("betshemesh", username, password)
        client.login()
        yield client
        client.close()
    
    def test_login_success(self):
        """Test successful login to betshemesh library."""
        username, password = get_credentials()
        with LibraryClient("betshemesh", username, password) as client:
            result = client.login()
            assert result is True
            assert client.is_logged_in is True
    
    def test_get_checked_out_books(self, client):
        """Test fetching checked out books from betshemesh library."""
        books = client.get_checked_out_books()
        
        assert isinstance(books, list)
        for book in books:
            assert isinstance(book, CheckedOutBook)
            assert book.title is not None
            assert book.library_slug == "betshemesh"
    
    def test_get_checkout_history(self, client):
        """Test fetching checkout history from betshemesh library."""
        history = client.get_checkout_history()
        
        assert isinstance(history, PaginatedHistory)
        assert isinstance(history.items, list)
        
        for item in history.items:
            assert isinstance(item, HistoryItem)
            assert item.title is not None
            assert item.library_slug == "betshemesh"
