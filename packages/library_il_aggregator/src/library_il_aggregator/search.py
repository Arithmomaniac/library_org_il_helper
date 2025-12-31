"""Search aggregator for combining search results from multiple libraries."""

from __future__ import annotations

import asyncio
from typing import Optional

from library_il_client import BookDetails, LibraryClient, SearchResult, SearchResults

from library_il_aggregator.models import (
    CombinedBookDetails,
    CombinedSearchResult,
    CombinedSearchResults,
    LibrarySearchInfo,
)


class SearchAggregator:
    """
    Aggregates search results from multiple library.org.il websites.
    
    This class searches multiple libraries in parallel and combines the
    results with deduplication and ranking.
    
    Note: No login is required for searching - catalog searches are public.
    
    Example:
        >>> async with SearchAggregator(["shemesh", "betshemesh"]) as aggregator:
        ...     results = await aggregator.search(title="כראמל")
        ...     for item in results.items:
        ...         print(f"{item.primary.title} - found in {item.library_count} libraries")
    """
    
    def __init__(self, library_slugs: list[str]):
        """
        Initialize the search aggregator.
        
        Args:
            library_slugs: List of library identifiers to search
        """
        self.library_slugs = library_slugs
        self._clients: dict[str, LibraryClient] = {}
    
    async def __aenter__(self) -> "SearchAggregator":
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
    
    async def close(self) -> None:
        """Close all library clients."""
        close_tasks = [client.close() for client in self._clients.values()]
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
        self._clients.clear()
    
    def _get_or_create_client(self, slug: str) -> LibraryClient:
        """Get or create a client for the specified library."""
        if slug not in self._clients:
            self._clients[slug] = LibraryClient(slug)
        return self._clients[slug]
    
    async def search(
        self,
        title: Optional[str] = None,
        author: Optional[str] = None,
        series: Optional[str] = None,
        max_per_library: int = 20,
    ) -> CombinedSearchResults:
        """
        Search all configured libraries and combine results.
        
        Args:
            title: Search by title (כותר)
            author: Search by author (מחבר)
            series: Search by series (סדרה)
            max_per_library: Maximum results to fetch per library (default 20)
            
        Returns:
            CombinedSearchResults with merged and ranked results.
        """
        # Search all libraries in parallel
        async def search_library(slug: str) -> tuple[str, Optional[SearchResults], Optional[str]]:
            try:
                client = self._get_or_create_client(slug)
                results = await client.search(
                    title=title,
                    author=author,
                    series=series,
                    max_results=max_per_library,
                )
                return slug, results, None
            except Exception as e:
                return slug, None, str(e)
        
        tasks = [search_library(slug) for slug in self.library_slugs]
        search_results = await asyncio.gather(*tasks)
        
        # Collect results and errors
        all_results: dict[str, list[tuple[int, SearchResult]]] = {}
        library_info: list[LibrarySearchInfo] = []
        errors: dict[str, str] = {}
        
        for slug, results, error in search_results:
            if error:
                errors[slug] = error
                continue
            
            if results:
                library_info.append(LibrarySearchInfo(
                    library_slug=slug,
                    total_count=results.total_count,
                    fetched_count=len(results.items),
                ))
                
                # Store results with their original position (rank)
                all_results[slug] = [(i, item) for i, item in enumerate(results.items)]
        
        # Merge and rank results
        combined = self._merge_and_rank(all_results)
        
        return CombinedSearchResults(
            items=combined,
            library_info=library_info,
            errors=errors,
        )
    
    def _merge_and_rank(
        self,
        results_by_library: dict[str, list[tuple[int, SearchResult]]],
    ) -> list[CombinedSearchResult]:
        """
        Merge results from multiple libraries and rank them.
        
        The algorithm:
        1. Group results by normalized title+author key
        2. Score each group based on library count and best rank position
        3. Sort by score (highest first)
        """
        # Group all results by title+author key
        # Key: title_author_key -> list of (library, rank, result)
        title_author_groups: dict[tuple, list[tuple[str, int, SearchResult]]] = {}
        
        for slug, items in results_by_library.items():
            for rank, result in items:
                ta_key = result.title_author_key()
                if ta_key not in title_author_groups:
                    title_author_groups[ta_key] = []
                title_author_groups[ta_key].append((slug, rank, result))
        
        # Build combined results from title+author groups
        combined_results: list[CombinedSearchResult] = []
        
        for ta_key, group in title_author_groups.items():
            # Sort by rank first, then by library_slug for deterministic ties
            sorted_group = sorted(group, key=lambda x: (x[1], x[0]))
            
            # Get unique libraries in this group
            library_count = len(set(item[0] for item in group))
            
            # Get the best-ranked item for common fields
            best_result = sorted_group[0][2]
            best_rank = sorted_group[0][1]
            
            # Collect one result per library (best-ranked from each)
            library_results = []
            seen_libraries = set()
            for _, _, result in sorted_group:
                if result.library_slug not in seen_libraries:
                    library_results.append(result)
                    seen_libraries.add(result.library_slug)
            
            # Calculate score: library count + rank bonus
            score = self._calculate_score(
                library_count=library_count,
                best_rank=best_rank,
            )
            
            combined_results.append(CombinedSearchResult(
                title=best_result.title,
                author=best_result.author,
                series=best_result.series,
                series_number=best_result.series_number,
                library_results=library_results,
                score=score,
            ))
        
        # Sort by score (highest first)
        combined_results.sort(key=lambda x: x.score, reverse=True)
        
        return combined_results
    
    def _calculate_score(
        self,
        library_count: int,
        best_rank: int,
    ) -> float:
        """
        Calculate a score for ranking search results.
        
        Factors:
        - Library count: more libraries = higher score
        - Best rank: lower rank position = higher score
        """
        # Base score from library count
        score = library_count * 10
        
        # Bonus for higher ranking (lower position number)
        # Max bonus of 20 for rank 0, decreasing to 0 for rank 20+
        rank_bonus = max(0, 20 - best_rank)
        score += rank_bonus
        
        return float(score)
    
    async def get_combined_details(
        self,
        slug_id_pairs: list[tuple[str, str]],
    ) -> CombinedBookDetails:
        """
        Get combined book details from multiple libraries by slug-id pairs.
        
        This method fetches detailed book information (including copies and locations)
        for a book from multiple libraries and combines them into a single view.
        
        Note: This method does NOT require login - book details are public.
        
        Args:
            slug_id_pairs: List of (library_slug, title_id) tuples specifying
                          which books to fetch from which libraries.
                          
        Returns:
            CombinedBookDetails with all book details and copies from all libraries.
            
        Example:
            >>> async with SearchAggregator(["shemesh", "betshemesh"]) as aggregator:
            ...     # First search to get title_ids
            ...     results = await aggregator.search(title="כראמל")
            ...     # Get the slug-id pairs from the first result
            ...     pairs = [(r.library_slug, r.title_id) for r in results.items[0].library_results]
            ...     # Fetch combined details
            ...     details = await aggregator.get_combined_details(pairs)
            ...     print(f"Total copies: {details.total_copy_count}")
        """
        # Fetch details from all libraries in parallel
        async def fetch_details(slug: str, title_id: str) -> tuple[str, Optional[BookDetails], Optional[str]]:
            try:
                client = self._get_or_create_client(slug)
                details = await client.get_book_details(title_id)
                return slug, details, None
            except Exception as e:
                return slug, None, str(e)
        
        tasks = [fetch_details(slug, title_id) for slug, title_id in slug_id_pairs]
        results = await asyncio.gather(*tasks)
        
        # Collect results and errors
        library_details: list[BookDetails] = []
        errors: dict[str, str] = {}
        
        # Use the first successful result for common fields
        title = ""
        author = None
        series = None
        series_number = None
        
        for slug, details, error in results:
            if error:
                errors[slug] = error
                continue
            
            if details:
                library_details.append(details)
                
                # Set common fields from first successful result
                if not title:
                    title = details.title
                    author = details.author
                    series = details.series
                    series_number = details.series_number
        
        return CombinedBookDetails(
            title=title,
            author=author,
            series=series,
            series_number=series_number,
            library_details=library_details,
            errors=errors,
        )
