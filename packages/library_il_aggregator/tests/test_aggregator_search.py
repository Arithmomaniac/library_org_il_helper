"""Tests for the combined search functionality in library_il_aggregator package.

These tests do NOT require credentials since catalog searches are public.
They are integration tests that actually connect to the library.org.il websites.
"""

import pytest
import pytest_asyncio

from library_il_aggregator import (
    CombinedSearchResult,
    CombinedSearchResults,
    LibrarySearchInfo,
    SearchAggregator,
)


# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


class TestSearchAggregator:
    """Tests for the SearchAggregator class."""
    
    @pytest_asyncio.fixture
    async def aggregator(self):
        """Create a search aggregator for two libraries."""
        agg = SearchAggregator(["shemesh", "betshemesh"])
        yield agg
        await agg.close()
    
    @pytest.mark.asyncio
    async def test_combined_search_by_title(self, aggregator):
        """Test combined search by title returns results from multiple libraries."""
        results = await aggregator.search(title="כראמל", max_per_library=5)
        
        assert isinstance(results, CombinedSearchResults)
        assert len(results.library_info) > 0
        
        # Should have results from at least one library
        total_fetched = sum(info.fetched_count for info in results.library_info)
        assert total_fetched > 0
    
    @pytest.mark.asyncio
    async def test_library_info_contains_counts(self, aggregator):
        """Test that library info contains correct counts."""
        results = await aggregator.search(title="כראמל", max_per_library=5)
        
        for info in results.library_info:
            assert isinstance(info, LibrarySearchInfo)
            assert info.library_slug in ["shemesh", "betshemesh"]
            assert info.total_count >= 0
            assert info.fetched_count >= 0
            assert info.fetched_count <= info.total_count
    
    @pytest.mark.asyncio
    async def test_combined_results_have_items(self, aggregator):
        """Test that combined results contain CombinedSearchResult items."""
        results = await aggregator.search(title="כראמל", max_per_library=5)
        
        for item in results.items:
            assert isinstance(item, CombinedSearchResult)
            assert item.primary is not None
            assert item.primary.title is not None
            assert item.score > 0
            assert item.match_level in ["exact", "title_author", "title_only", "unique"]
    
    @pytest.mark.asyncio
    async def test_combined_results_library_slugs(self, aggregator):
        """Test that combined results track library slugs correctly."""
        results = await aggregator.search(title="כראמל", max_per_library=5)
        
        for item in results.items:
            slugs = item.library_slugs
            assert len(slugs) > 0
            assert item.library_count == len(slugs)
            
            # All slugs should be from the searched libraries
            for slug in slugs:
                assert slug in ["shemesh", "betshemesh"]
    
    @pytest.mark.asyncio
    async def test_warnings_for_truncated_results(self, aggregator):
        """Test that warnings are generated when results are truncated."""
        results = await aggregator.search(title="כראמל", max_per_library=5)
        
        # If any library has more than 5 results, there should be a warning
        for info in results.library_info:
            if info.total_count > info.fetched_count:
                warnings = results.get_warnings()
                assert len(warnings) > 0
                break
    
    @pytest.mark.asyncio
    async def test_search_no_results(self, aggregator):
        """Test combined search with term that returns no results."""
        results = await aggregator.search(
            title="xyznonexistentbook123456",
            max_per_library=5,
        )
        
        assert isinstance(results, CombinedSearchResults)
        assert len(results.items) == 0
    
    @pytest.mark.asyncio
    async def test_total_unique_count(self, aggregator):
        """Test that total_unique_count matches number of items."""
        results = await aggregator.search(title="כראמל", max_per_library=5)
        
        assert results.total_unique_count == len(results.items)
    
    @pytest.mark.asyncio
    async def test_libraries_searched_property(self, aggregator):
        """Test that libraries_searched returns correct list."""
        results = await aggregator.search(title="כראמל", max_per_library=5)
        
        searched = results.libraries_searched
        # Should have attempted to search both libraries
        assert "shemesh" in searched or "betshemesh" in searched


class TestSearchAggregatorSingleLibrary:
    """Tests for searching a single library."""
    
    @pytest.mark.asyncio
    async def test_single_library_search(self):
        """Test search with a single library."""
        async with SearchAggregator(["betshemesh"]) as aggregator:
            results = await aggregator.search(title="כראמל", max_per_library=5)
            
            assert len(results.library_info) == 1
            assert results.library_info[0].library_slug == "betshemesh"
