"""Tests for the search functionality in library_il_client package.

These tests do NOT require credentials since catalog searches are public.
They are integration tests that actually connect to the library.org.il websites.
"""

import pytest
import pytest_asyncio

from library_il_client import (
    LibraryClient,
    SearchResult,
    SearchResults,
)


# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


class TestLibraryClientSearch:
    """Tests for the search functionality."""
    
    @pytest_asyncio.fixture
    async def client(self):
        """Create a client for the betshemesh library (no login needed for search)."""
        client = LibraryClient("betshemesh")
        yield client
        await client.close()
    
    @pytest.mark.asyncio
    async def test_search_by_title(self, client):
        """Test searching by title returns results."""
        results = await client.search(title="כראמל", max_results=5)
        
        assert isinstance(results, SearchResults)
        assert results.total_count > 0
        assert len(results.items) > 0
        assert len(results.items) <= 5
        
        # All items should be SearchResult instances
        for item in results.items:
            assert isinstance(item, SearchResult)
            assert item.title is not None
            assert len(item.title) > 0
            assert item.library_slug == "betshemesh"
    
    @pytest.mark.asyncio
    async def test_search_result_has_author(self, client):
        """Test that search results include author information."""
        results = await client.search(title="כראמל", max_results=5)
        
        # At least some items should have authors
        items_with_authors = [item for item in results.items if item.author]
        assert len(items_with_authors) > 0
    
    @pytest.mark.asyncio
    async def test_search_result_has_classification(self, client):
        """Test that search results include classification information."""
        results = await client.search(title="כראמל", max_results=5)
        
        # At least some items should have classification
        items_with_classification = [item for item in results.items if item.classification]
        assert len(items_with_classification) > 0
    
    @pytest.mark.asyncio
    async def test_search_no_results(self, client):
        """Test search with term that returns no results."""
        results = await client.search(title="xyznonexistentbook123456", max_results=5)
        
        assert isinstance(results, SearchResults)
        assert results.total_count == 0
        assert len(results.items) == 0
    
    @pytest.mark.asyncio
    async def test_search_pagination(self, client):
        """Test that search correctly reports total count and pages."""
        results = await client.search(title="כראמל", max_results=5)
        
        # Should have total count greater than items returned
        assert results.total_count >= len(results.items)
        
        # Should have correct page info
        assert results.page == 1
        if results.total_count > 20:
            assert results.total_pages > 1
    
    @pytest.mark.asyncio
    async def test_search_without_login(self):
        """Test that search works without logging in."""
        async with LibraryClient("betshemesh") as client:
            # Should work without calling login()
            results = await client.search(title="ספר", max_results=3)
            
            assert isinstance(results, SearchResults)
            assert results.total_count > 0


class TestLibraryClientSearchShemesh:
    """Tests for search on the shemesh library."""
    
    @pytest_asyncio.fixture
    async def client(self):
        """Create a client for the shemesh library."""
        client = LibraryClient("shemesh")
        yield client
        await client.close()
    
    @pytest.mark.asyncio
    async def test_search_shemesh(self, client):
        """Test that search works on shemesh library."""
        results = await client.search(title="כראמל", max_results=5)
        
        assert isinstance(results, SearchResults)
        assert len(results.items) >= 0  # May have results or not
        
        for item in results.items:
            assert isinstance(item, SearchResult)
            assert item.library_slug == "shemesh"
