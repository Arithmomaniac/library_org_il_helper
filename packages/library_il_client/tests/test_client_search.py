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
from library_il_client.models import normalize_text


# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


class TestNormalizeText:
    """Tests for the normalize_text function used in deduplication."""
    
    def test_removes_parentheses(self):
        """Test that parentheses are replaced with spaces."""
        assert normalize_text("כראמל (10) הסוף") == "כראמל 10 הסוף"
    
    def test_removes_punctuation(self):
        """Test that various punctuation is replaced with spaces."""
        assert normalize_text("Hello, World!") == "Hello World"
        assert normalize_text("Test: (1) - [2] {3}") == "Test 1 2 3"
    
    def test_replaces_hyphens_with_spaces(self):
        """Test that hyphens are replaced with spaces, not removed."""
        assert normalize_text("ברנע-גולדברג, מאירה") == "ברנע גולדברג מאירה"
    
    def test_collapses_multiple_spaces(self):
        """Test that multiple spaces are collapsed to single space."""
        assert normalize_text("word   word") == "word word"
        assert normalize_text("a  ,  b") == "a b"
    
    def test_strips_whitespace(self):
        """Test that leading/trailing whitespace is stripped."""
        assert normalize_text("  text  ") == "text"
    
    def test_handles_none(self):
        """Test that None input returns None."""
        assert normalize_text(None) is None
    
    def test_handles_empty_string(self):
        """Test that empty string returns None."""
        assert normalize_text("") is None
        assert normalize_text("   ") is None
    
    def test_preserves_hebrew_letters(self):
        """Test that Hebrew letters are preserved."""
        assert normalize_text("שלום עולם") == "שלום עולם"
    
    def test_preserves_numbers(self):
        """Test that numbers are preserved."""
        assert normalize_text("כראמל 10") == "כראמל 10"


class TestSearchResultKeys:
    """Tests for SearchResult key methods."""
    
    def test_metadata_key_normalized(self):
        """Test that metadata_key returns normalized values."""
        result = SearchResult(
            title="כראמל (10) הסוף?",
            author="ברנע-גולדברג, מאירה",
            classification="קריאה מתקדמת",
        )
        
        key = result.metadata_key()
        assert key[0] == "כראמל 10 הסוף"  # Title normalized
        assert key[1] == "ברנע גולדברג מאירה"  # Author normalized
    
    def test_matching_results_have_same_keys(self):
        """Test that similar results with different formatting have the same keys."""
        result1 = SearchResult(
            title="כראמל 10 הסוף?",
            author="ברנע-גולדברג, מאירה",
            classification="קריאה מתקדמת",
        )
        
        result2 = SearchResult(
            title="כראמל (10) הסוף?",
            author="ברנע גולדברג , מאירה",
            classification="קריאה מתקדמת",
        )
        
        assert result1.metadata_key() == result2.metadata_key()
        assert result1.title_author_key() == result2.title_author_key()
        assert result1.title_key() == result2.title_key()


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
