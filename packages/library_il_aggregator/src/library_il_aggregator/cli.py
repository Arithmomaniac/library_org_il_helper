"""Command-line interface for the Library IL Aggregator."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date
from typing import Optional

from tabulate import tabulate

from library_il_aggregator import LibraryAccount, LibraryAggregator, SearchAggregator


def main() -> int:
    """Main entry point for the CLI."""
    return asyncio.run(async_main())


def create_aggregate_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Create the parser for the 'aggregate' subcommand."""
    parser = subparsers.add_parser(
        "aggregate",
        help="Aggregate library data (checked out books, history)",
        description="Aggregate library data from multiple library.org.il websites",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use same credentials for multiple libraries (from environment)
  export TEUDAT_ZEHUT=your_tz
  export LIBRARY_PASSWORD=your_password
  library-il aggregate --libraries shemesh betshemesh --all
  
  # Specify credentials on command line
  library-il aggregate --libraries shemesh --username YOUR_TZ --password YOUR_PASS --books
  
  # Use a JSON config file for multiple accounts
  library-il aggregate --config accounts.json --all
  
  # Config file format (accounts.json):
  # [
  #   {"slug": "shemesh", "username": "tz1", "password": "pass1", "label": "parent"},
  #   {"slug": "shemesh", "username": "tz2", "password": "pass2", "label": "child"},
  #   {"slug": "betshemesh", "username": "tz1", "password": "pass1"}
  # ]
""",
    )
    
    # Account configuration options
    config_group = parser.add_argument_group("Account Configuration")
    config_group.add_argument(
        "--config",
        "-c",
        help="Path to JSON config file with account credentials",
    )
    config_group.add_argument(
        "--libraries",
        "-l",
        nargs="+",
        help="Library slugs (use with --username/--password for same credentials)",
    )
    config_group.add_argument(
        "--username",
        "-u",
        help="Username (Teudat Zehut). Uses TEUDAT_ZEHUT env var if not provided.",
    )
    config_group.add_argument(
        "--password",
        "-p",
        help="Password. Uses LIBRARY_PASSWORD env var if not provided.",
    )
    
    # Output options
    output_group = parser.add_argument_group("Output Options")
    output_group.add_argument(
        "--books",
        "-b",
        action="store_true",
        help="Show currently checked out books",
    )
    output_group.add_argument(
        "--history",
        "-H",
        action="store_true",
        help="Show checkout history",
    )
    output_group.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Show both checked out books and history",
    )
    output_group.add_argument(
        "--limit",
        "-n",
        type=int,
        default=0,
        help="Limit number of results (0 = no limit)",
    )
    
    return parser


def create_search_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Create the parser for the 'search' subcommand."""
    parser = subparsers.add_parser(
        "search",
        help="Search across multiple libraries",
        description="Search across multiple library.org.il websites",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search for books by title across default libraries
  library-il search --title "כראמל"
  
  # Search for books by author
  library-il search --author "רולינג"
  
  # Search for books by series
  library-il search --series "הארי פוטר"
  
  # Search specific libraries with custom limit
  library-il search --libraries shemesh betshemesh --title "כראמל" --max-per-library 20
  
  # Limit total displayed results
  library-il search --title "ספר" --limit 10
  
  # Show slug:id pairs for use with library-il copies command
  library-il search --title "כראמל" --show-ids
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
        "--show-ids",
        "-i",
        action="store_true",
        help="Show slug:id pairs in output (for use with library-il copies command)",
    )
    
    return parser


def create_copies_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Create the parser for the 'copies' subcommand."""
    parser = subparsers.add_parser(
        "copies",
        help="View book copies across multiple libraries",
        description="View book copies from multiple library.org.il websites",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # View copies for a single book (public data only)
  library-il copies shemesh:ABC123
  
  # View copies with authentication (shows status, return dates)
  library-il copies shemesh:ABC123 --username YOUR_TZ --password YOUR_PASS
  
  # Use environment variables for credentials
  export TEUDAT_ZEHUT=your_tz
  export LIBRARY_PASSWORD=your_password
  library-il copies shemesh:ABC123 betshemesh:DEF456
  
  # Use a JSON config file for credentials
  library-il copies shemesh:ABC123 --config accounts.json
  
  # Config file format (accounts.json):
  # [
  #   {"slug": "shemesh", "username": "tz", "password": "pass"},
  #   {"slug": "betshemesh", "username": "tz", "password": "pass"}
  # ]

Format:
  Each positional argument should be a slug:id pair where:
  - slug: Library identifier (e.g., "shemesh", "betshemesh")
  - id: Title ID from the library catalog (visible in URLs)

Authentication:
  When authenticated, additional columns are available:
  - Status (e.g., "מושאל" = checked out, "זמין" = available)
  - Return Date (when a copy is checked out)
  - Hold count for the title
""",
    )
    
    # Positional arguments for slug-id pairs
    parser.add_argument(
        "books",
        nargs="+",
        metavar="SLUG:ID",
        help="One or more slug:id pairs (e.g., shemesh:ABC123 betshemesh:DEF456)",
    )
    
    # Authentication options
    auth_group = parser.add_argument_group("Authentication")
    auth_group.add_argument(
        "--config",
        "-c",
        help="Path to JSON config file with account credentials",
    )
    auth_group.add_argument(
        "--username",
        "-u",
        help="Username (Teudat Zehut). Uses TEUDAT_ZEHUT env var if not provided.",
    )
    auth_group.add_argument(
        "--password",
        "-p",
        help="Password. Uses LIBRARY_PASSWORD env var if not provided.",
    )
    
    return parser


async def async_main() -> int:
    """Async main function for the CLI."""
    parser = argparse.ArgumentParser(
        description="Library IL Helper - Interact with library.org.il Israeli public library websites",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  aggregate  Aggregate library data (checked out books, history)
  search     Search across multiple libraries
  copies     View book copies across multiple libraries

Use 'library-il <command> --help' for more information on a specific command.
""",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Create subparsers for each command
    create_aggregate_parser(subparsers)
    create_search_parser(subparsers)
    create_copies_parser(subparsers)
    
    args = parser.parse_args()
    
    # Dispatch to the appropriate command handler
    if args.command == "aggregate":
        return await run_aggregate_command(args)
    elif args.command == "search":
        return await run_search_command(args)
    elif args.command == "copies":
        return await run_copies_command(args)
    else:
        parser.print_help()
        return 0


async def run_aggregate_command(args: argparse.Namespace) -> int:
    """Run the aggregate command."""
    
    # Default to showing all if nothing specified
    if not args.books and not args.history and not args.all:
        args.all = True
    
    if args.all:
        args.books = True
        args.history = True
    
    # Build accounts list
    accounts: list[LibraryAccount] = []
    
    if args.config:
        # Load from config file
        try:
            with open(args.config) as f:
                config_data = json.load(f)
            
            for item in config_data:
                accounts.append(LibraryAccount(
                    slug=item["slug"],
                    username=item["username"],
                    password=item["password"],
                    label=item.get("label"),
                ))
        except FileNotFoundError:
            print(f"Error: Config file not found: {args.config}", file=sys.stderr)
            return 1
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error: Invalid config file: {e}", file=sys.stderr)
            return 1
    elif args.libraries:
        # Use --libraries with shared credentials
        username = args.username or os.environ.get("TEUDAT_ZEHUT", "")
        password = args.password or os.environ.get("LIBRARY_PASSWORD", "")
        
        if not username:
            print("Error: Username required. Use --username or set TEUDAT_ZEHUT.", file=sys.stderr)
            return 1
        if not password:
            print("Error: Password required. Use --password or set LIBRARY_PASSWORD.", file=sys.stderr)
            return 1
        
        for slug in args.libraries:
            accounts.append(LibraryAccount(
                slug=slug,
                username=username,
                password=password,
            ))
    else:
        # Default to shemesh and betshemesh with env credentials
        username = args.username or os.environ.get("TEUDAT_ZEHUT", "")
        password = args.password or os.environ.get("LIBRARY_PASSWORD", "")
        
        if not username or not password:
            print("Error: Credentials required. Use --config, --libraries with credentials,", file=sys.stderr)
            print("       or set TEUDAT_ZEHUT and LIBRARY_PASSWORD environment variables.", file=sys.stderr)
            return 1
        
        accounts = [
            LibraryAccount(slug="shemesh", username=username, password=password),
            LibraryAccount(slug="betshemesh", username=username, password=password),
        ]
    
    if not accounts:
        print("Error: No library accounts configured.", file=sys.stderr)
        return 1
    
    # Build a mapping for display labels
    # Map from slug or account_id to label
    label_map: dict[str, str] = {}
    for account in accounts:
        if account.label:
            label_map[account.account_id] = account.label
        else:
            label_map[account.account_id] = f"{account.slug}:{account.username}"
    
    async with LibraryAggregator(accounts) as aggregator:
        # Login to all accounts
        print(f"Logging in to {len(accounts)} account(s)...")
        login_results = await aggregator.login_all()
        
        for account_id, success in login_results.items():
            status = "✓" if success else "✗"
            label = label_map.get(account_id, account_id)
            print(f"  {status} {label}")
        
        if not any(login_results.values()):
            print("Error: Failed to login to any account", file=sys.stderr)
            return 1
        
        print()
        
        # Show checked out books
        if args.books:
            print("## Currently Checked Out Books")
            print()
            
            all_books = await aggregator.get_all_checked_out_books()
            
            if all_books.errors:
                for account_id, error in all_books.errors.items():
                    label = label_map.get(account_id, account_id)
                    print(f"  Warning: {label}: {error}", file=sys.stderr)
            
            books = all_books.sorted_by_due_date()
            if args.limit > 0:
                books = books[:args.limit]
            
            if not books:
                print("No books currently checked out.")
            else:
                print(f"**Total: {all_books.total_count} books**")
                print()
                
                # Prepare table data
                table_data = []
                for book in books:
                    # Get the label using the account_id attached to the book
                    library_label = book.library_slug
                    if hasattr(book, 'account_id'):
                        library_label = label_map.get(book.account_id, book.library_slug)
                    else:
                        # Fallback to slug matching for backwards compatibility
                        for account in accounts:
                            if account.slug == book.library_slug:
                                library_label = label_map.get(account.account_id, book.library_slug)
                                break
                    
                    # Truncate long library labels
                    if len(library_label) > 18:
                        library_label = library_label[:15] + "..."
                    
                    # Truncate long titles
                    title = book.title
                    if len(title) > 58:
                        title = title[:55] + "..."
                    
                    due_date_str = str(book.due_date) if book.due_date else "N/A"
                    days_str = ""
                    if book.due_date:
                        days_remaining = (book.due_date - date.today()).days
                        days_str = str(days_remaining)
                    else:
                        days_str = "N/A"
                    
                    table_data.append([library_label, title, due_date_str, days_str])
                
                headers = ["Library", "Title", "Due Date", "Days Remaining"]
                print(tabulate(table_data, headers=headers, tablefmt="github"))
            
            print()
        
        # Show checkout history
        if args.history:
            print("## Checkout History")
            print()
            
            all_history = await aggregator.get_all_checkout_history()
            
            if all_history.errors:
                for account_id, error in all_history.errors.items():
                    label = label_map.get(account_id, account_id)
                    print(f"  Warning: {label}: {error}", file=sys.stderr)
            
            items = all_history.sorted_by_return_date()
            if args.limit > 0:
                items = items[:args.limit]
            
            if not items:
                print("No checkout history found.")
            else:
                print(f"**Total: {all_history.total_count} items**")
                print()
                
                # Prepare table data
                table_data = []
                for item in items:
                    # Get the label using the account_id attached to the item
                    library_label = item.library_slug
                    if hasattr(item, 'account_id'):
                        library_label = label_map.get(item.account_id, item.library_slug)
                    else:
                        # Fallback to slug matching for backwards compatibility
                        for account in accounts:
                            if account.slug == item.library_slug:
                                library_label = label_map.get(account.account_id, item.library_slug)
                                break
                    
                    # Truncate long library labels
                    if len(library_label) > 18:
                        library_label = library_label[:15] + "..."
                    
                    # Truncate long titles
                    title = item.title
                    if len(title) > 58:
                        title = title[:55] + "..."
                    
                    # Truncate long author names
                    author = item.author or ""
                    if len(author) > 28:
                        author = author[:25] + "..."
                    
                    return_date_str = str(item.return_date) if item.return_date else "N/A"
                    
                    table_data.append([library_label, title, author, return_date_str])
                
                headers = ["Library", "Title", "Author", "Return Date"]
                print(tabulate(table_data, headers=headers, tablefmt="github"))
            
            print()
    
    return 0


async def run_search_command(args: argparse.Namespace) -> int:
    """Run the search command."""
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
            
            # Add slug:id pairs column if --show-ids was specified
            if args.show_ids:
                slug_ids = []
                for r in item.library_results:
                    if r.library_slug and r.title_id:
                        slug_ids.append(f"{r.library_slug}:{r.title_id}")
                ids_str = " ".join(slug_ids)
                row.append(ids_str)
            
            table_data.append(row)
        
        headers = ["Title", "Author", "Series", "Libraries"]
        if args.show_ids:
            headers.append("Slug:ID")
        
        print(tabulate(table_data, headers=headers, tablefmt="github"))
        
        # Show if results were truncated
        if args.limit > 0 and results.total_unique_count > args.limit:
            print()
            print(f"*Showing {args.limit} of {results.total_unique_count} results*")
    
    return 0


# Display truncation constants for copies command
MAX_TITLE_LEN = 40
MAX_AUTHOR_LEN = 25
MAX_ID_LEN = 15


def truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len, adding '...' suffix if needed."""
    if len(text) > max_len:
        return text[:max_len - 3] + "..."
    return text


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


async def run_copies_command(args: argparse.Namespace) -> int:
    """Run the copies command."""
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
    
    # Build credentials map from arguments
    credentials: dict[str, tuple[str, str]] = {}
    
    if args.config:
        # Load from config file
        try:
            with open(args.config) as f:
                config_data = json.load(f)
            
            for item in config_data:
                slug = item["slug"]
                if slug in unique_slugs:
                    credentials[slug] = (item["username"], item["password"])
        except FileNotFoundError:
            print(f"Error: Config file not found: {args.config}", file=sys.stderr)
            return 1
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error: Invalid config file: {e}", file=sys.stderr)
            return 1
    else:
        # Use --username/--password or environment variables
        username = args.username or os.environ.get("TEUDAT_ZEHUT", "")
        password = args.password or os.environ.get("LIBRARY_PASSWORD", "")
        
        if username and password:
            # Apply same credentials to all unique slugs
            for slug in unique_slugs:
                credentials[slug] = (username, password)
    
    async with SearchAggregator(unique_slugs) as aggregator:
        # Login if credentials were provided (in parallel)
        if credentials:
            print(f"Logging in to {len(credentials)} library(s)...")
            login_results = await aggregator.login_all(credentials)
            for slug, success in login_results.items():
                status = "✓" if success else "✗"
                print(f"  {status} {slug}")
            print()
        
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
                        # Track if we've added hold count to first unavailable copy
                        first_unavailable_with_holds = True
                        
                        # Add each copy as a row
                        for copy in lib_details.copies:
                            # Format return date
                            return_date_str = ""
                            if copy.return_date:
                                return_date_str = copy.return_date.strftime("%d/%m/%Y")
                            
                            # Check if we have authenticated data
                            if copy.status:
                                has_authenticated_data = True
                            
                            # For the first not available copy, append hold count
                            status_str = copy.status or ""
                            is_available = status_str and "זמין" in status_str
                            if (first_unavailable_with_holds and 
                                not is_available and 
                                status_str and 
                                lib_details.hold_count is not None):
                                status_str = f"{status_str} ({lib_details.hold_count})"
                                first_unavailable_with_holds = False
                            
                            all_copies_data.append({
                                "slug": slug,
                                "id": title_id,
                                "title": lib_details.title,
                                "author": lib_details.author or "",
                                "barcode": copy.barcode or "",
                                "status": status_str,
                                "location": copy.location or "",
                                "classification": copy.classification or "",
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
                                "classification": "",
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
                row["classification"],
                row["shelf_sign"],
                row["return_date"],
            ]
            table_data.append(row_data)
        
        headers = ["Library", "ID", "Title", "Author", "Barcode", "Status", "Location", "Classification", "Shelf", "Return Date"]
        print(tabulate(table_data, headers=headers, tablefmt="github"))
        
        # Show note if no authenticated data was found
        if not has_authenticated_data:
            print()
            print("*Note: Status and Return Date columns require authentication.*")
            print("*Use --username and --password, or set TEUDAT_ZEHUT and LIBRARY_PASSWORD.*")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
