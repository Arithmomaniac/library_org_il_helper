"""Command-line interface for the Library IL Aggregator."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from datetime import date

from tabulate import tabulate

from library_il_aggregator import LibraryAccount, LibraryAggregator


def export_to_csv(
    sections: list[tuple[str, list[str], list[list[str]]]],
    filepath: str,
) -> None:
    """
    Export data to a CSV file with UTF-8 encoding (with BOM for Excel compatibility).
    
    Args:
        sections: List of tuples (section_name, headers, data)
        filepath: Output file path
    """
    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        for i, (section_name, headers, data) in enumerate(sections):
            if i > 0:
                # Add empty row between sections
                writer.writerow([])
            writer.writerow([section_name])
            writer.writerow(headers)
            writer.writerows(data)


def export_to_markdown(
    sections: list[tuple[str, list[str], list[list[str]]]],
    filepath: str,
) -> None:
    """
    Export data to a Markdown file with UTF-8 encoding.
    
    Args:
        sections: List of tuples (section_name, headers, data)
        filepath: Output file path
    """
    with open(filepath, "w", encoding="utf-8") as f:
        for i, (section_name, headers, data) in enumerate(sections):
            if i > 0:
                f.write("\n\n")
            f.write(f"## {section_name}\n\n")
            f.write(tabulate(data, headers=headers, tablefmt="github"))
            f.write("\n")


def main() -> int:
    """Main entry point for the CLI."""
    return asyncio.run(async_main())


async def async_main() -> int:
    """Async main function for the CLI."""
    parser = argparse.ArgumentParser(
        description="Aggregate library data from multiple library.org.il websites",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use same credentials for multiple libraries (from environment)
  export TEUDAT_ZEHUT=your_tz
  export LIBRARY_PASSWORD=your_password
  library-il-aggregate --libraries shemesh betshemesh --all
  
  # Specify credentials on command line
  library-il-aggregate --libraries shemesh --username YOUR_TZ --password YOUR_PASS --books
  
  # Use a JSON config file for multiple accounts
  library-il-aggregate --config accounts.json --all
  
  # Export results to CSV file (default format)
  library-il-aggregate --libraries shemesh --books --output books.csv
  
  # Export results to Markdown file
  library-il-aggregate --libraries shemesh --all --output results.md --format markdown
  
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
    output_group.add_argument(
        "--output",
        "-o",
        help="Export results to file (supports CSV and Markdown)",
    )
    output_group.add_argument(
        "--format",
        "-f",
        choices=["csv", "markdown"],
        default="csv",
        help="Output file format: csv (default) or markdown",
    )
    
    args = parser.parse_args()
    
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
        
        # Collect sections for export
        export_sections: list[tuple[str, list[str], list[list[str]]]] = []
        
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
                
                # Prepare table data (full data for export, truncated for console)
                table_data = []
                table_data_full = []
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
                    
                    due_date_str = str(book.due_date) if book.due_date else "N/A"
                    days_str = ""
                    if book.due_date:
                        days_remaining = (book.due_date - date.today()).days
                        days_str = str(days_remaining)
                    else:
                        days_str = "N/A"
                    
                    # Full data for export
                    table_data_full.append([library_label, book.title, due_date_str, days_str])
                    
                    # Truncated data for console display
                    library_label_truncated = library_label
                    if len(library_label_truncated) > 18:
                        library_label_truncated = library_label_truncated[:15] + "..."
                    
                    title_truncated = book.title
                    if len(title_truncated) > 58:
                        title_truncated = title_truncated[:55] + "..."
                    
                    table_data.append([library_label_truncated, title_truncated, due_date_str, days_str])
                
                headers = ["Library", "Title", "Due Date", "Days Remaining"]
                print(tabulate(table_data, headers=headers, tablefmt="github"))
                
                # Add to export sections
                if args.output and table_data_full:
                    export_sections.append(("Currently Checked Out Books", headers, table_data_full))
            
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
                
                # Prepare table data (full data for export, truncated for console)
                table_data = []
                table_data_full = []
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
                    
                    return_date_str = str(item.return_date) if item.return_date else "N/A"
                    author = item.author or ""
                    
                    # Full data for export
                    table_data_full.append([library_label, item.title, author, return_date_str])
                    
                    # Truncated data for console display
                    library_label_truncated = library_label
                    if len(library_label_truncated) > 18:
                        library_label_truncated = library_label_truncated[:15] + "..."
                    
                    title_truncated = item.title
                    if len(title_truncated) > 58:
                        title_truncated = title_truncated[:55] + "..."
                    
                    author_truncated = author
                    if len(author_truncated) > 28:
                        author_truncated = author_truncated[:25] + "..."
                    
                    table_data.append([library_label_truncated, title_truncated, author_truncated, return_date_str])
                
                headers = ["Library", "Title", "Author", "Return Date"]
                print(tabulate(table_data, headers=headers, tablefmt="github"))
                
                # Add to export sections
                if args.output and table_data_full:
                    export_sections.append(("Checkout History", headers, table_data_full))
            
            print()
        
        # Export to file if requested
        if args.output and export_sections:
            if args.format == "csv":
                export_to_csv(export_sections, args.output)
            else:
                export_to_markdown(export_sections, args.output)
            print(f"Exported to {args.output}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
