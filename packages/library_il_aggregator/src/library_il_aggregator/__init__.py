"""
Library IL Aggregator - Aggregates library data from multiple library.org.il websites.

This package provides functionality to combine checked out books and history
from multiple Israeli public libraries into a single unified view.
"""

from library_il_aggregator.aggregator import LibraryAccount, LibraryAggregator
from library_il_aggregator.models import (
    AggregatedBooks,
    AggregatedHistory,
    CombinedSearchResult,
    CombinedSearchResults,
    LibrarySearchInfo,
)
from library_il_aggregator.search import SearchAggregator

__all__ = [
    "LibraryAccount",
    "LibraryAggregator",
    "AggregatedBooks",
    "AggregatedHistory",
    "CombinedSearchResult",
    "CombinedSearchResults",
    "LibrarySearchInfo",
    "SearchAggregator",
]
