"""Command-line interface for viewing book copies across multiple libraries."""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Optional

from tabulate import tabulate

from library_il_aggregator import SearchAggregator

# Display truncation constants
MAX_TITLE_LEN = 40
MAX_AUTHOR_LEN = 25
MAX_ID_LEN = 15


def truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len, adding '...' suffix if needed."""
    if len(text) > max_len:
        return text[:max_len - 3] + "..."
    return text


def main() -> int:
    """Main entry point for the copies CLI."""
    return asyncio.run(async_main())


def parse_slug_id(value: str) -> tuple[str, str]:
    """
    Parse a slug-id pair from command line argument.
    
    Accepts formats:
    - "slug:id" (e.g., "shemesh:ABC123")
    - "slug/id" (e.g., "shemesh/ABC123")
    
    Returns:
        Tuple of (slug, id)
    
    Raises:
        ValueError: If the format is invalid
    """
    for sep in [":", "/"]:
        if sep in value:
            parts = value.split(sep, 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                return (parts[0], parts[1])
    
    raise ValueError(
        f"Invalid slug-id format: '{value}'. Expected 'slug:id' or 'slug/id'"
    )


async def async_main() -> int:
    """Async main function for the copies CLI."""
    parser = argparse.ArgumentParser(
        description="View book copies from multiple library.org.il websites",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # View copies for a single book
  library-il-copies shemesh:ABC123
  
  # View copies for multiple books across libraries
  library-il-copies shemesh:ABC123 betshemesh:DEF456
  
  # Use with search to get IDs first
  library-il-search --title "כראמל" --show-ids
  # Then copy the slug:id pairs and use them:
  library-il-copies shemesh:5057435A5F1154 betshemesh:555E43565E

Format:
  Each argument should be a slug:id pair where:
  - slug: Library identifier (e.g., "shemesh", "betshemesh")
  - id: Title ID from the library catalog (visible in URLs)

Note:
  Some columns (Status, Return Date) are only available when authenticated.
  The library-il-copies command uses public data by default.
""",
    )
    
    # Positional arguments for slug-id pairs
    parser.add_argument(
        "books",
        nargs="+",
        metavar="SLUG:ID",
        help="One or more slug:id pairs (e.g., shemesh:ABC123 betshemesh:DEF456)",
    )
    
    args = parser.parse_args()
    
    # Parse the slug-id pairs
    slug_id_pairs: list[tuple[str, str]] = []
    for arg in args.books:
        try:
            pair = parse_slug_id(arg)
            slug_id_pairs.append(pair)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    
    if not slug_id_pairs:
        print("Error: At least one slug:id pair is required", file=sys.stderr)
        return 1
    
    # Get unique library slugs for the aggregator
    unique_slugs = list(dict.fromkeys(slug for slug, _ in slug_id_pairs))
    
    async with SearchAggregator(unique_slugs) as aggregator:
        print(f"Fetching copies from {len(unique_slugs)} library(s): {', '.join(unique_slugs)}")
        print()
        
        # Fetch details for all books (preserving order from input)
        all_copies_data: list[dict] = []
        errors: list[str] = []
        has_authenticated_data = False
        
        for slug, title_id in slug_id_pairs:
            try:
                details = await aggregator.get_combined_details([(slug, title_id)])
                
                if details.errors:
                    for err_slug, error in details.errors.items():
                        errors.append(f"{err_slug}:{title_id} - {error}")
                    continue
                
                # Get the book details for this specific library
                for lib_details in details.library_details:
                    if lib_details.library_slug == slug:
                        # Add each copy as a row
                        for copy in lib_details.copies:
                            # Format return date
                            return_date_str = ""
                            if copy.return_date:
                                return_date_str = copy.return_date.strftime("%d/%m/%Y")
                            
                            # Check if we have authenticated data
                            if copy.status:
                                has_authenticated_data = True
                            
                            all_copies_data.append({
                                "slug": slug,
                                "id": title_id,
                                "title": lib_details.title,
                                "author": lib_details.author or "",
                                "barcode": copy.barcode or "",
                                "status": copy.status or "",
                                "location": copy.location or "",
                                "shelf_sign": copy.shelf_sign or "",
                                "return_date": return_date_str,
                                "hold_count": lib_details.hold_count,
                            })
                        
                        # If no copies, still show the book info
                        if not lib_details.copies:
                            all_copies_data.append({
                                "slug": slug,
                                "id": title_id,
                                "title": lib_details.title,
                                "author": lib_details.author or "",
                                "barcode": "(no copies)",
                                "status": "",
                                "location": "",
                                "shelf_sign": "",
                                "return_date": "",
                                "hold_count": lib_details.hold_count,
                            })
                        break
                else:
                    # Book details not found for this slug
                    errors.append(f"{slug}:{title_id} - No details found")
                    
            except Exception as e:
                errors.append(f"{slug}:{title_id} - {str(e)}")
        
        # Show errors if any
        if errors:
            print("**Errors:**")
            for error in errors:
                print(f"  ✗ {error}")
            print()
        
        if not all_copies_data:
            print("No copies found.")
            return 0
        
        print("## Book Copies")
        print()
        print(f"**Total: {len(all_copies_data)} copies**")
        print()
        
        # Prepare table data
        table_data = []
        for row in all_copies_data:
            row_data = [
                row["slug"],
                truncate(row["id"], MAX_ID_LEN),
                truncate(row["title"], MAX_TITLE_LEN),
                truncate(row["author"], MAX_AUTHOR_LEN),
                row["barcode"],
                row["status"],
                row["location"],
                row["shelf_sign"],
                row["return_date"],
            ]
            table_data.append(row_data)
        
        headers = ["Library", "ID", "Title", "Author", "Barcode", "Status", "Location", "Shelf", "Return Date"]
        print(tabulate(table_data, headers=headers, tablefmt="github"))
        
        # Show note if no authenticated data was found
        if not has_authenticated_data:
            print()
            print("*Note: Status and Return Date columns require authentication.*")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
