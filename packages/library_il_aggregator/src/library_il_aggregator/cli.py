"""Command-line interface for the Library IL Aggregator."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import date
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from library_il_aggregator import LibraryAccount, LibraryAggregator
from library_il_aggregator.export_utils import (
    OutputFormat,
    format_csv,
    format_markdown,
    write_output,
)

app = typer.Typer(
    help="Aggregate library data from multiple library.org.il websites",
    add_completion=False,
)

console = Console()
err_console = Console(stderr=True)


@app.command()
def main(
    config: Annotated[
        Optional[str],
        typer.Option("--config", "-c", help="Path to JSON config file with account credentials"),
    ] = None,
    libraries: Annotated[
        Optional[list[str]],
        typer.Option("--libraries", "-l", help="Library slugs (use with --username/--password for same credentials)"),
    ] = None,
    username: Annotated[
        Optional[str],
        typer.Option("--username", "-u", help="Username (Teudat Zehut). Uses TEUDAT_ZEHUT env var if not provided."),
    ] = None,
    password: Annotated[
        Optional[str],
        typer.Option("--password", "-p", help="Password. Uses LIBRARY_PASSWORD env var if not provided."),
    ] = None,
    books: Annotated[
        bool,
        typer.Option("--books", "-b", help="Show currently checked out books"),
    ] = False,
    history: Annotated[
        bool,
        typer.Option("--history", "-H", help="Show checkout history"),
    ] = False,
    all_data: Annotated[
        bool,
        typer.Option("--all", "-a", help="Show both checked out books and history"),
    ] = False,
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="Limit number of results (0 = no limit)"),
    ] = 0,
    output: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="Export results to file. If not specified with --format, outputs to stdout."),
    ] = None,
    output_format: Annotated[
        Optional[OutputFormat],
        typer.Option("--format", "-f", help="Output format: csv (default) or markdown. When specified without --output, outputs to stdout."),
    ] = None,
) -> None:
    """
    Aggregate library data from multiple library.org.il websites.
    
    Examples:
    
        # Use same credentials for multiple libraries (from environment)
        
        export TEUDAT_ZEHUT=your_tz
        
        export LIBRARY_PASSWORD=your_password
        
        library-il-aggregate --libraries shemesh betshemesh --all
        
        # Specify credentials on command line
        
        library-il-aggregate --libraries shemesh --username YOUR_TZ --password YOUR_PASS --books
        
        # Use a JSON config file for multiple accounts
        
        library-il-aggregate --config accounts.json --all
        
        # Export results to CSV file
        
        library-il-aggregate --libraries shemesh --books --output books.csv
        
        # Export results to stdout in CSV format
        
        library-il-aggregate --libraries shemesh --books --format csv
        
        # Export results to Markdown file
        
        library-il-aggregate --libraries shemesh --all --output results.md --format markdown
    """
    asyncio.run(async_main(
        config=config,
        libraries=libraries,
        username=username,
        password=password,
        books=books,
        history=history,
        all_data=all_data,
        limit=limit,
        output=output,
        output_format=output_format,
    ))


async def async_main(
    config: Optional[str],
    libraries: Optional[list[str]],
    username: Optional[str],
    password: Optional[str],
    books: bool,
    history: bool,
    all_data: bool,
    limit: int,
    output: Optional[str],
    output_format: Optional[OutputFormat],
) -> None:
    """Async main function for the CLI."""
    
    # Default to showing all if nothing specified
    show_books = books
    show_history = history
    if not books and not history and not all_data:
        show_books = True
        show_history = True
    if all_data:
        show_books = True
        show_history = True
    
    # Build accounts list
    accounts: list[LibraryAccount] = []
    
    if config:
        # Load from config file
        try:
            with open(config) as f:
                config_data = json.load(f)
            
            for item in config_data:
                accounts.append(LibraryAccount(
                    slug=item["slug"],
                    username=item["username"],
                    password=item["password"],
                    label=item.get("label"),
                ))
        except FileNotFoundError:
            err_console.print(f"Error: Config file not found: {config}")
            raise typer.Exit(code=1)
        except (json.JSONDecodeError, KeyError) as e:
            err_console.print(f"Error: Invalid config file: {e}")
            raise typer.Exit(code=1)
    elif libraries:
        # Use --libraries with shared credentials
        resolved_username = username or os.environ.get("TEUDAT_ZEHUT", "")
        resolved_password = password or os.environ.get("LIBRARY_PASSWORD", "")
        
        if not resolved_username:
            err_console.print("Error: Username required. Use --username or set TEUDAT_ZEHUT.")
            raise typer.Exit(code=1)
        if not resolved_password:
            err_console.print("Error: Password required. Use --password or set LIBRARY_PASSWORD.")
            raise typer.Exit(code=1)
        
        for slug in libraries:
            accounts.append(LibraryAccount(
                slug=slug,
                username=resolved_username,
                password=resolved_password,
            ))
    else:
        # Default to shemesh and betshemesh with env credentials
        resolved_username = username or os.environ.get("TEUDAT_ZEHUT", "")
        resolved_password = password or os.environ.get("LIBRARY_PASSWORD", "")
        
        if not resolved_username or not resolved_password:
            err_console.print("Error: Credentials required. Use --config, --libraries with credentials,")
            err_console.print("       or set TEUDAT_ZEHUT and LIBRARY_PASSWORD environment variables.")
            raise typer.Exit(code=1)
        
        accounts = [
            LibraryAccount(slug="shemesh", username=resolved_username, password=resolved_password),
            LibraryAccount(slug="betshemesh", username=resolved_username, password=resolved_password),
        ]
    
    if not accounts:
        err_console.print("Error: No library accounts configured.")
        raise typer.Exit(code=1)
    
    # Build a mapping for display labels
    label_map: dict[str, str] = {}
    for account in accounts:
        if account.label:
            label_map[account.account_id] = account.label
        else:
            label_map[account.account_id] = f"{account.slug}:{account.username}"
    
    # Determine if we're exporting or displaying
    is_exporting = output is not None or output_format is not None
    effective_format = output_format or OutputFormat.csv
    
    # Validate CSV export doesn't have multiple sections
    if is_exporting and effective_format == OutputFormat.csv and show_books and show_history:
        err_console.print("Error: CSV export does not support multiple sections. Use --books or --history, not both.")
        raise typer.Exit(code=1)
    
    async with LibraryAggregator(accounts) as aggregator:
        # Login to all accounts
        if not is_exporting:
            console.print(f"Logging in to {len(accounts)} account(s)...")
        
        login_results = await aggregator.login_all()
        
        if not is_exporting:
            for account_id, success in login_results.items():
                status = "✓" if success else "✗"
                label = label_map.get(account_id, account_id)
                console.print(f"  {status} {label}")
        
        if not any(login_results.values()):
            err_console.print("Error: Failed to login to any account")
            raise typer.Exit(code=1)
        
        if not is_exporting:
            console.print()
        
        # Collect sections for export
        export_sections: list[tuple[str, list[str], list[list[str]]]] = []
        
        # Fetch and display checked out books
        if show_books:
            all_books = await aggregator.get_all_checked_out_books()
            
            if all_books.errors and not is_exporting:
                for account_id, error in all_books.errors.items():
                    label = label_map.get(account_id, account_id)
                    err_console.print(f"  Warning: {label}: {error}")
            
            books_list = all_books.sorted_by_due_date()
            if limit > 0:
                books_list = books_list[:limit]
            
            # Prepare table data
            table_data_full: list[list[str]] = []
            for book in books_list:
                library_label = book.library_slug
                if hasattr(book, 'account_id'):
                    library_label = label_map.get(book.account_id, book.library_slug)
                else:
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
                
                table_data_full.append([library_label, book.title, due_date_str, days_str])
            
            headers = ["Library", "Title", "Due Date", "Days Remaining"]
            
            if is_exporting:
                if table_data_full:
                    export_sections.append(("Currently Checked Out Books", headers, table_data_full))
            else:
                # Display mode - show to console with rich formatting
                console.print("[bold]## Currently Checked Out Books[/bold]")
                console.print()
                
                if not books_list:
                    console.print("No books currently checked out.")
                else:
                    console.print(f"[bold]Total: {all_books.total_count} books[/bold]")
                    console.print()
                    
                    table = Table(show_header=True, header_style="bold")
                    table.add_column("Library", max_width=18)
                    table.add_column("Title", max_width=58)
                    table.add_column("Due Date")
                    table.add_column("Days Remaining")
                    
                    for book in books_list:
                        library_label = book.library_slug
                        if hasattr(book, 'account_id'):
                            library_label = label_map.get(book.account_id, book.library_slug)
                        else:
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
                        
                        # Truncate for display
                        if len(library_label) > 18:
                            library_label = library_label[:15] + "..."
                        title = book.title
                        if len(title) > 58:
                            title = title[:55] + "..."
                        
                        table.add_row(library_label, title, due_date_str, days_str)
                    
                    console.print(table)
                
                console.print()
        
        # Fetch and display checkout history
        if show_history:
            all_history = await aggregator.get_all_checkout_history()
            
            if all_history.errors and not is_exporting:
                for account_id, error in all_history.errors.items():
                    label = label_map.get(account_id, account_id)
                    err_console.print(f"  Warning: {label}: {error}")
            
            history_items = all_history.sorted_by_return_date()
            if limit > 0:
                history_items = history_items[:limit]
            
            # Prepare table data
            table_data_full = []
            for item in history_items:
                library_label = item.library_slug
                if hasattr(item, 'account_id'):
                    library_label = label_map.get(item.account_id, item.library_slug)
                else:
                    for account in accounts:
                        if account.slug == item.library_slug:
                            library_label = label_map.get(account.account_id, item.library_slug)
                            break
                
                return_date_str = str(item.return_date) if item.return_date else "N/A"
                author = item.author or ""
                
                table_data_full.append([library_label, item.title, author, return_date_str])
            
            headers = ["Library", "Title", "Author", "Return Date"]
            
            if is_exporting:
                if table_data_full:
                    export_sections.append(("Checkout History", headers, table_data_full))
            else:
                # Display mode - show to console with rich formatting
                console.print("[bold]## Checkout History[/bold]")
                console.print()
                
                if not history_items:
                    console.print("No checkout history found.")
                else:
                    console.print(f"[bold]Total: {all_history.total_count} items[/bold]")
                    console.print()
                    
                    table = Table(show_header=True, header_style="bold")
                    table.add_column("Library", max_width=18)
                    table.add_column("Title", max_width=58)
                    table.add_column("Author", max_width=28)
                    table.add_column("Return Date")
                    
                    for item in history_items:
                        library_label = item.library_slug
                        if hasattr(item, 'account_id'):
                            library_label = label_map.get(item.account_id, item.library_slug)
                        else:
                            for account in accounts:
                                if account.slug == item.library_slug:
                                    library_label = label_map.get(account.account_id, item.library_slug)
                                    break
                        
                        return_date_str = str(item.return_date) if item.return_date else "N/A"
                        author = item.author or ""
                        
                        # Truncate for display
                        if len(library_label) > 18:
                            library_label = library_label[:15] + "..."
                        title = item.title
                        if len(title) > 58:
                            title = title[:55] + "..."
                        if len(author) > 28:
                            author = author[:25] + "..."
                        
                        table.add_row(library_label, title, author, return_date_str)
                    
                    console.print(table)
                
                console.print()
        
        # Export to file or stdout if requested
        if is_exporting:
            if not export_sections:
                err_console.print("Warning: No data to export.")
                raise typer.Exit(code=0)
            
            try:
                if effective_format == OutputFormat.csv:
                    # CSV only supports single section (already validated above)
                    section_name, headers, data = export_sections[0]
                    content = format_csv(headers, data)
                else:
                    # Markdown supports multiple sections
                    content = ""
                    for i, (section_name, headers, data) in enumerate(export_sections):
                        if i > 0:
                            content += "\n\n"
                        content += format_markdown(headers, data, section_name)
                
                write_output(content, output, effective_format)
            except OSError as e:
                err_console.print(f"Error: Failed to write output: {e}")
                raise typer.Exit(code=1)


# Keep the format functions exported for tests
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
    if len(sections) > 1:
        raise ValueError("CSV export does not support multiple sections. Please export one data type at a time.")
    
    section_name, headers, data = sections[0]
    content = format_csv(headers, data)
    # Remove BOM since we're using utf-8-sig encoding
    if content.startswith("\ufeff"):
        content = content[1:]
    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        f.write(content)


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
            f.write(format_markdown(headers, data, section_name))


if __name__ == "__main__":
    app()
