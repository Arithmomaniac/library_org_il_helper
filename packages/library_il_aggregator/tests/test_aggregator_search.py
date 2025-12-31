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
            assert item.title is not None
            assert len(item.library_results) > 0
            assert item.score > 0
    
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


class TestSearchAggregatorCombinedDetails:
    """Tests for the get_combined_details functionality."""
    
    @pytest_asyncio.fixture
    async def aggregator(self):
        """Create a search aggregator for two libraries."""
        agg = SearchAggregator(["shemesh", "betshemesh"])
        yield agg
        await agg.close()
    
    @pytest.mark.asyncio
    async def test_get_combined_details_returns_details(self, aggregator):
        """Test that get_combined_details returns CombinedBookDetails."""
        from library_il_aggregator import CombinedBookDetails
        
        # First search to get title_ids
        results = await aggregator.search(title="כראמל", max_per_library=5)
        assert len(results.items) > 0
        
        # Get the slug-id pairs from the first result
        item = results.items[0]
        pairs = [
            (r.library_slug, r.title_id)
            for r in item.library_results
            if r.library_slug and r.title_id
        ]
        assert len(pairs) > 0
        
        # Fetch combined details
        details = await aggregator.get_combined_details(pairs)
        
        assert isinstance(details, CombinedBookDetails)
        assert details.title is not None
        assert len(details.title) > 0
    
    @pytest.mark.asyncio
    async def test_combined_details_has_copies_from_multiple_libraries(self, aggregator):
        """Test that combined details includes copies from multiple libraries."""
        # First search to get title_ids
        results = await aggregator.search(title="כראמל", max_per_library=5)
        assert len(results.items) > 0
        
        # Find a result that's in multiple libraries
        multi_lib_item = None
        for item in results.items:
            if item.library_count >= 2:
                multi_lib_item = item
                break
        
        if multi_lib_item is None:
            pytest.skip("No multi-library results found")
        
        # Get the slug-id pairs
        pairs = [
            (r.library_slug, r.title_id)
            for r in multi_lib_item.library_results
            if r.library_slug and r.title_id
        ]
        
        # Fetch combined details
        details = await aggregator.get_combined_details(pairs)
        
        assert details.library_count >= 2
        assert details.total_copy_count > 0
        
        # Check that copies are from multiple libraries
        copies_by_lib = details.copies_by_library()
        assert len(copies_by_lib) >= 2
    
    @pytest.mark.asyncio
    async def test_combined_details_format_copies_summary(self, aggregator):
        """Test that format_copies_summary returns a formatted string."""
        # First search to get title_ids
        results = await aggregator.search(title="כראמל", max_per_library=5)
        assert len(results.items) > 0
        
        # Get the slug-id pairs from the first result
        item = results.items[0]
        pairs = [
            (r.library_slug, r.title_id)
            for r in item.library_results
            if r.library_slug and r.title_id
        ]
        
        # Fetch combined details
        details = await aggregator.get_combined_details(pairs)
        
        summary = details.format_copies_summary()
        assert isinstance(summary, str)
        assert len(summary) > 0
        # Should contain library:count format
        assert ":" in summary
