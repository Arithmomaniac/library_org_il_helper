"""Search aggregator for combining search results from multiple libraries."""

from __future__ import annotations

import asyncio
from typing import Optional

from library_il_client import LibraryClient, SearchResult, SearchResults

from library_il_aggregator.models import (
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
        2. For items in the same group, check if all metadata matches (exact match)
        3. Score each merged item based on:
           - Match quality (exact > title+author > unique)
           - Number of libraries containing the item
           - Original position in each library's results
        4. Sort by score (highest first)
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
            # Get unique libraries in this group
            libraries_in_group = set(item[0] for item in group)
            library_count = len(libraries_in_group)
            
            # Check if all items have the same metadata (exact match)
            metadata_keys = set(item[2].metadata_key() for item in group)
            is_exact_match = len(metadata_keys) == 1 and library_count > 1
            
            # Get the best-ranked item as primary
            best_rank = min(item[1] for item in group)
            primary_item = next(item for item in group if item[1] == best_rank)
            primary = primary_item[2]
            
            # Collect duplicates (items from other libraries)
            duplicates = []
            if library_count > 1:
                # Get one item per library (the best-ranked from each)
                seen_libraries = {primary.library_slug}
                for _, _, result in sorted(group, key=lambda x: x[1]):
                    if result.library_slug not in seen_libraries:
                        duplicates.append(result)
                        seen_libraries.add(result.library_slug)
            
            # Determine match level
            if library_count == 1:
                match_level = "unique"
            elif is_exact_match:
                match_level = "exact"
            else:
                match_level = "title_author"
            
            # Calculate score
            score = self._calculate_score(
                match_level=match_level,
                library_count=library_count,
                best_rank=best_rank,
            )
            
            combined_results.append(CombinedSearchResult(
                primary=primary,
                duplicates=duplicates,
                match_level=match_level,
                score=score,
            ))
        
        # Sort by score (highest first)
        combined_results.sort(key=lambda x: x.score, reverse=True)
        
        return combined_results
    
    def _calculate_score(
        self,
        match_level: str,
        library_count: int,
        best_rank: int,
    ) -> float:
        """
        Calculate a score for ranking search results.
        
        Factors:
        - Match level: exact > title_author > title_only > unique
        - Library count: more libraries = higher score
        - Best rank: lower rank = higher score
        """
        # Base score from match level
        match_scores = {
            "exact": 100,
            "title_author": 75,
            "title_only": 50,
            "unique": 25,
        }
        score = match_scores.get(match_level, 0)
        
        # Bonus for being in multiple libraries
        score += library_count * 10
        
        # Bonus for higher ranking (lower position number)
        # Max bonus of 20 for rank 0, decreasing to 0 for rank 20+
        rank_bonus = max(0, 20 - best_rank)
        score += rank_bonus
        
        return float(score)
