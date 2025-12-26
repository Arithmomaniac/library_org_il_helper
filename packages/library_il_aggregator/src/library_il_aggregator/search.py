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
        1. Group results by metadata key for exact matches
        2. For items not exactly matching, group by title+author
        3. Score each item based on:
           - Match quality (exact > title+author > title only)
           - Number of libraries containing the item
           - Original position in each library's results
        4. Sort by score (highest first)
        """
        # Build groups for deduplication
        # Key: metadata_key or title_author_key -> list of (library, rank, result)
        exact_groups: dict[tuple, list[tuple[str, int, SearchResult]]] = {}
        title_author_groups: dict[tuple, list[tuple[str, int, SearchResult]]] = {}
        
        for slug, items in results_by_library.items():
            for rank, result in items:
                # Try exact match first
                exact_key = result.metadata_key()
                if exact_key not in exact_groups:
                    exact_groups[exact_key] = []
                exact_groups[exact_key].append((slug, rank, result))
                
                # Also index by title+author
                ta_key = result.title_author_key()
                if ta_key not in title_author_groups:
                    title_author_groups[ta_key] = []
                title_author_groups[ta_key].append((slug, rank, result))
        
        # Build combined results
        combined_results: list[CombinedSearchResult] = []
        processed_results: set[tuple] = set()  # Track processed exact keys
        
        # First, process exact matches (all metadata identical)
        for exact_key, group in exact_groups.items():
            if exact_key in processed_results:
                continue
            
            # Check if this group has items from multiple libraries
            libraries_in_group = set(item[0] for item in group)
            
            if len(libraries_in_group) > 1:
                # Multiple libraries have exact same metadata - merge
                primary = group[0][2]
                duplicates = [item[2] for item in group[1:]]
                best_rank = min(item[1] for item in group)
                
                # Score based on match level and library count
                score = self._calculate_score(
                    match_level="exact",
                    library_count=len(libraries_in_group),
                    best_rank=best_rank,
                )
                
                combined_results.append(CombinedSearchResult(
                    primary=primary,
                    duplicates=duplicates,
                    match_level="exact",
                    score=score,
                ))
                
                processed_results.add(exact_key)
            else:
                # Single library - check for title+author matches
                ta_key = group[0][2].title_author_key()
                ta_group = title_author_groups.get(ta_key, [])
                ta_libraries = set(item[0] for item in ta_group)
                
                if len(ta_libraries) > 1:
                    # Multiple libraries have same title+author but different metadata
                    # Keep items separate but note they may be related
                    _, rank, result = group[0]
                    score = self._calculate_score(
                        match_level="title_author",
                        library_count=len(ta_libraries),
                        best_rank=rank,
                    )
                    
                    combined_results.append(CombinedSearchResult(
                        primary=result,
                        duplicates=[],
                        match_level="title_author",
                        score=score,
                    ))
                else:
                    # Unique to single library
                    _, rank, result = group[0]
                    score = self._calculate_score(
                        match_level="unique",
                        library_count=1,
                        best_rank=rank,
                    )
                    
                    combined_results.append(CombinedSearchResult(
                        primary=result,
                        duplicates=[],
                        match_level="unique",
                        score=score,
                    ))
                
                processed_results.add(exact_key)
        
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
