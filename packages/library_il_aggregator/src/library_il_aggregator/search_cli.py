"""Command-line interface for combined library search."""

from __future__ import annotations

import argparse
import asyncio
import sys

from tabulate import tabulate

from library_il_aggregator import SearchAggregator


def main() -> int:
    """Main entry point for the search CLI."""
    return asyncio.run(async_main())


async def async_main() -> int:
    """Async main function for the search CLI."""
    parser = argparse.ArgumentParser(
        description="Search across multiple library.org.il websites",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search for books by title across default libraries
  library-il-search --title "כראמל"
  
  # Search for books by author
  library-il-search --author "רולינג"
  
  # Search for books by series
  library-il-search --series "הארי פוטר"
  
  # Search specific libraries with custom limit
  library-il-search --libraries shemesh betshemesh --title "כראמל" --max-per-library 20
  
  # Limit total displayed results
  library-il-search --title "ספר" --limit 10
  
  # Show detailed copy information (locations, counts)
  library-il-search --title "כראמל" --details
""",
    )
    
    # Library configuration
    parser.add_argument(
        "--libraries",
        "-l",
        nargs="+",
        default=["shemesh", "betshemesh"],
        help="Library slugs to search (default: shemesh betshemesh)",
    )
    
    # Search parameters
    search_group = parser.add_argument_group("Search Parameters")
    search_group.add_argument(
        "--title",
        "-t",
        help="Search by title (כותר)",
    )
    search_group.add_argument(
        "--author",
        "-a",
        help="Search by author (מחבר)",
    )
    search_group.add_argument(
        "--series",
        "-s",
        help="Search by series (סדרה)",
    )
    
    # Result options
    result_group = parser.add_argument_group("Result Options")
    result_group.add_argument(
        "--max-per-library",
        "-m",
        type=int,
        default=20,
        help="Maximum results per library (default: 20)",
    )
    result_group.add_argument(
        "--limit",
        "-n",
        type=int,
        default=0,
        help="Limit total displayed results (0 = no limit)",
    )
    result_group.add_argument(
        "--details",
        "-d",
        action="store_true",
        help="Show detailed copy information (locations, copy counts per library)",
    )
    
    args = parser.parse_args()
    
    # Validate search parameters
    if not args.title and not args.author and not args.series:
        print("Error: At least one search parameter is required (--title, --author, or --series)", file=sys.stderr)
        return 1
    
    async with SearchAggregator(args.libraries) as aggregator:
        print(f"Searching {len(args.libraries)} libraries: {', '.join(args.libraries)}")
        print()
        
        results = await aggregator.search(
            title=args.title,
            author=args.author,
            series=args.series,
            max_per_library=args.max_per_library,
        )
        
        # Show library info
        print("## Library Results Summary")
        print()
        
        for info in results.library_info:
            status = "✓" if info.fetched_count > 0 else "○"
            print(f"  {status} {info.library_slug}: {info.fetched_count} of {info.total_count} results")
        
        # Show errors
        if results.errors:
            print()
            for slug, error in results.errors.items():
                print(f"  ✗ {slug}: {error}")
        
        # Show warnings
        warnings = results.get_warnings()
        if warnings:
            print()
            print("**Warnings:**")
            for warning in warnings:
                print(f"  ⚠ {warning}")
        
        print()
        print("## Combined Search Results")
        print()
        print(f"**Total unique results: {results.total_unique_count}**")
        print()
        
        if not results.items:
            print("No results found.")
            return 0
        
        # Prepare table data
        items_to_show = results.items
        if args.limit > 0:
            items_to_show = items_to_show[:args.limit]
        
        # If --details flag is set, fetch detailed info for each result
        details_map = {}
        if args.details:
            print("Fetching copy details...")
            print()
            for item in items_to_show:
                # Get slug-id pairs from the search result
                pairs = []
                for r in item.library_results:
                    if r.library_slug and r.title_id:
                        pairs.append((r.library_slug, r.title_id))
                
                if pairs:
                    combined_details = await aggregator.get_combined_details(pairs)
                    # Use title as key (normalized for matching)
                    details_map[item.title] = combined_details
        
        table_data = []
        for item in items_to_show:
            # Title (truncate if too long)
            title = item.title
            title_display = title
            if len(title_display) > 50:
                title_display = title_display[:47] + "..."
            
            # Author (truncate if too long)
            author = item.author or ""
            if len(author) > 30:
                author = author[:27] + "..."
            
            # Libraries
            libs = ", ".join(item.library_slugs)
            if len(libs) > 25:
                libs = libs[:22] + "..."
            
            # Series info
            series_info = ""
            if item.series:
                series_info = item.series
                if item.series_number:
                    series_info += f" #{item.series_number}"
            elif item.series_number:
                series_info = f"#{item.series_number}"
            
            row = [
                title_display,
                author,
                series_info,
                libs,
            ]
            
            # Add copies column if --details was specified
            if args.details:
                copies_info = ""
                if title in details_map:
                    details = details_map[title]
                    copies_info = details.format_copies_summary()
                row.append(copies_info)
            
            table_data.append(row)
        
        headers = ["Title", "Author", "Series", "Libraries"]
        if args.details:
            headers.append("Copies")
        
        print(tabulate(table_data, headers=headers, tablefmt="github"))
        
        # Show if results were truncated
        if args.limit > 0 and results.total_unique_count > args.limit:
            print()
            print(f"*Showing {args.limit} of {results.total_unique_count} results*")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
