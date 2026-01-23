"""Tests for the library_il_client package.

These tests require valid credentials to be set in environment variables:
- TEUDAT_ZEHUT: The username (Teudat Zehut)
- LIBRARY_PASSWORD: The password (defaults to TEUDAT_ZEHUT if not set)

The tests are integration tests that actually connect to the library.org.il websites.
"""

import os
from datetime import date

import pytest
import pytest_asyncio

from library_il_client import (
    CheckedOutBook,
    HistoryItem,
    LibraryClient,
    LibraryClientError,
    LoginError,
    PaginatedHistory,
)


# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


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
    
    @pytest_asyncio.fixture
    async def client(self):
        """Create a logged-in client for the shemesh library."""
        username, password = get_credentials()
        client = LibraryClient("shemesh", username, password)
        await client.login()
        yield client
        await client.close()
    
    @pytest.mark.asyncio
    async def test_login_success(self):
        """Test successful login to shemesh library."""
        username, password = get_credentials()
        async with LibraryClient("shemesh", username, password) as client:
            result = await client.login()
            assert result is True
            assert client.is_logged_in is True
    
    @pytest.mark.asyncio
    async def test_login_failure(self):
        """Test login failure with invalid credentials."""
        async with LibraryClient("shemesh", "invalid_user", "invalid_pass") as client:
            with pytest.raises(LoginError):
                await client.login()
    
    @pytest.mark.asyncio
    async def test_get_checked_out_books(self, client):
        """Test fetching checked out books from shemesh library."""
        books = await client.get_checked_out_books()
        
        assert isinstance(books, list)
        # All items should be CheckedOutBook instances
        for book in books:
            assert isinstance(book, CheckedOutBook)
            assert book.title is not None
            assert len(book.title) > 0
            assert book.library_slug == "shemesh"
    
    @pytest.mark.asyncio
    async def test_checked_out_books_have_due_dates(self, client):
        """Test that checked out books have due dates."""
        books = await client.get_checked_out_books()
        
        for book in books:
            if book.due_date:
                assert isinstance(book.due_date, date)
                # Due date should be in the future or today
                assert book.due_date >= date.today()
    
    @pytest.mark.asyncio
    async def test_checked_out_books_have_barcodes(self, client):
        """Test that checked out books have barcodes for renewal."""
        books = await client.get_checked_out_books()
        
        for book in books:
            # Barcode is required for renewal
            assert book.barcode is not None
            assert len(book.barcode) > 0
    
    @pytest.mark.asyncio
    async def test_get_checkout_history(self, client):
        """Test fetching checkout history from shemesh library."""
        history = await client.get_checkout_history()
        
        assert isinstance(history, PaginatedHistory)
        assert isinstance(history.items, list)
        
        # Should have some history items
        assert len(history.items) > 0
        
        for item in history.items:
            assert isinstance(item, HistoryItem)
            assert item.title is not None
            assert len(item.title) > 0
            assert item.library_slug == "shemesh"
    
    @pytest.mark.asyncio
    async def test_checkout_history_has_return_dates(self, client):
        """Test that history items have return dates."""
        history = await client.get_checkout_history()
        
        for item in history.items:
            if item.return_date:
                assert isinstance(item.return_date, date)
                # Return date should be in the past or today
                assert item.return_date <= date.today()
    
    @pytest.mark.asyncio
    async def test_checkout_history_has_authors(self, client):
        """Test that history items have author information."""
        history = await client.get_checkout_history()
        
        # At least some items should have authors
        items_with_authors = [item for item in history.items if item.author]
        assert len(items_with_authors) > 0
    
    @pytest.mark.asyncio
    async def test_not_logged_in_raises_error(self):
        """Test that operations fail when not logged in."""
        async with LibraryClient("shemesh") as client:
            with pytest.raises(LibraryClientError):
                await client.get_checked_out_books()
    
    @pytest.mark.asyncio
    async def test_download_html_success(self, client):
        """Test downloading HTML content with authenticated session."""
        html = await client.download_html("/user-loans")
        
        assert isinstance(html, str)
        assert len(html) > 0
        # HTML should contain some expected content
        assert "<html" in html.lower() or "<!doctype" in html.lower()
    
    @pytest.mark.asyncio
    async def test_download_html_relative_path(self, client):
        """Test downloading HTML with relative path."""
        # Use a different known valid path
        html = await client.download_html("/loans-history")
        
        assert isinstance(html, str)
        assert len(html) > 0
    
    @pytest.mark.asyncio
    async def test_download_html_not_logged_in(self):
        """Test that download_html fails when not logged in."""
        async with LibraryClient("shemesh") as client:
            with pytest.raises(LibraryClientError):
                await client.download_html("/user-loans")
    
    @pytest.mark.asyncio
    async def test_download_html_rejects_absolute_urls(self, client):
        """Test that download_html rejects absolute URLs for security."""
        with pytest.raises(LibraryClientError) as exc_info:
            await client.download_html("https://malicious.example.com/steal")
        assert "relative path" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_download_html_rejects_non_slash_paths(self, client):
        """Test that download_html rejects paths not starting with /."""
        with pytest.raises(LibraryClientError):
            await client.download_html("user-loans")
    
    @pytest.mark.asyncio
    async def test_download_html_rejects_protocol_relative_urls(self, client):
        """Test that download_html rejects protocol-relative URLs for security."""
        with pytest.raises(LibraryClientError) as exc_info:
            await client.download_html("//malicious.example.com/steal")
        assert "protocol-relative" in str(exc_info.value).lower()


class TestLibraryClientBetshemesh:
    """Tests for the LibraryClient with the betshemesh library."""
    
    @pytest_asyncio.fixture
    async def client(self):
        """Create a logged-in client for the betshemesh library."""
        username, password = get_credentials()
        client = LibraryClient("betshemesh", username, password)
        await client.login()
        yield client
        await client.close()
    
    @pytest.mark.asyncio
    async def test_login_success(self):
        """Test successful login to betshemesh library."""
        username, password = get_credentials()
        async with LibraryClient("betshemesh", username, password) as client:
            result = await client.login()
            assert result is True
            assert client.is_logged_in is True
    
    @pytest.mark.asyncio
    async def test_get_checked_out_books(self, client):
        """Test fetching checked out books from betshemesh library."""
        books = await client.get_checked_out_books()
        
        assert isinstance(books, list)
        for book in books:
            assert isinstance(book, CheckedOutBook)
            assert book.title is not None
            assert book.library_slug == "betshemesh"
    
    @pytest.mark.asyncio
    async def test_get_checkout_history(self, client):
        """Test fetching checkout history from betshemesh library."""
        history = await client.get_checkout_history()
        
        assert isinstance(history, PaginatedHistory)
        assert isinstance(history.items, list)
        
        for item in history.items:
            assert isinstance(item, HistoryItem)
            assert item.title is not None
            assert item.library_slug == "betshemesh"
    
    @pytest.mark.asyncio
    async def test_download_html_success(self, client):
        """Test downloading HTML content from betshemesh library."""
        html = await client.download_html("/user-loans")
        
        assert isinstance(html, str)
        assert len(html) > 0
        assert "<html" in html.lower() or "<!doctype" in html.lower()
