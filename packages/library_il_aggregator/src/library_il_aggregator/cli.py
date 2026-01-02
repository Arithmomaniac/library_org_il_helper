"""Command-line interface for the Library IL Aggregator."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import sys
from datetime import date
from enum import Enum
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table
from tabulate import tabulate

from library_il_aggregator import LibraryAccount, LibraryAggregator

app = typer.Typer(
    help="Aggregate library data from multiple library.org.il websites",
    add_completion=False,
)

console = Console()
err_console = Console(stderr=True)


class OutputFormat(str, Enum):
    """Output format for export."""
    csv = "csv"
    markdown = "markdown"


def format_csv(headers: list[str], data: list[list[str]]) -> str:
    """
    Format data as CSV with UTF-8 BOM for Excel compatibility.
    
    Args:
        headers: Column headers
        data: Table data rows
        
    Returns:
        CSV formatted string with UTF-8 BOM
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(data)
    # Prepend UTF-8 BOM for Excel compatibility
    return "\ufeff" + output.getvalue()


def format_markdown(headers: list[str], data: list[list[str]], title: str = "") -> str:
    """
    Format data as Markdown table.
    
    Args:
        headers: Column headers
        data: Table data rows
        title: Optional section title
        
    Returns:
        Markdown formatted string
    """
    result = ""
    if title:
        result += f"## {title}\n\n"
    result += tabulate(data, headers=headers, tablefmt="github")
    result += "\n"
    return result


def write_output(content: str, output_file: Optional[str], format_type: OutputFormat) -> None:
    """
    Write content to file or stdout.
    
    Args:
        content: The content to write
        output_file: Optional file path, if None writes to stdout
        format_type: The output format (csv or markdown)
    """
    if output_file:
        encoding = "utf-8-sig" if format_type == OutputFormat.csv else "utf-8"
        # For CSV, we need to strip the BOM from content since we're using utf-8-sig encoding
        if format_type == OutputFormat.csv and content.startswith("\ufeff"):
            content = content[1:]
        with open(output_file, "w", encoding=encoding, newline="") as f:
            f.write(content)
        console.print(f"Exported to {output_file}")
    else:
        # Write to stdout - use sys.stdout.buffer for guaranteed UTF-8
        sys.stdout.buffer.write(content.encode('utf-8'))
        sys.stdout.buffer.flush()


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
        
        library-il-aggregate --libraries shemesh betshemesh
        
        # Specify credentials on command line
        
        library-il-aggregate --libraries shemesh --username YOUR_TZ --password YOUR_PASS
        
        # Use a JSON config file for multiple accounts
        
        library-il-aggregate --config accounts.json
        
        # Export results to CSV file
        
        library-il-aggregate --libraries shemesh --output books.csv
        
        # Export results to stdout in CSV format
        
        library-il-aggregate --libraries shemesh --format csv
        
        # Export results to Markdown file
        
        library-il-aggregate --libraries shemesh --output results.md --format markdown
    """
    asyncio.run(async_main(
        config=config,
        libraries=libraries,
        username=username,
        password=password,
        limit=limit,
        output=output,
        output_format=output_format,
    ))


async def async_main(
    config: Optional[str],
    libraries: Optional[list[str]],
    username: Optional[str],
    password: Optional[str],
    limit: int,
    output: Optional[str],
    output_format: Optional[OutputFormat],
) -> None:
    """Async main function for the CLI."""
    
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
        
        # Fetch checked out books
        all_books = await aggregator.get_all_checked_out_books()
        
        if all_books.errors and not is_exporting:
            for account_id, error in all_books.errors.items():
                label = label_map.get(account_id, account_id)
                err_console.print(f"  Warning: {label}: {error}")
        
        books = all_books.sorted_by_due_date()
        if limit > 0:
            books = books[:limit]
        
        if is_exporting:
            # Export mode - prepare data and output
            if not books:
                err_console.print("Warning: No data to export.")
                raise typer.Exit(code=0)
            
            table_data: list[list[str]] = []
            for book in books:
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
                
                table_data.append([library_label, book.title, due_date_str, days_str])
            
            headers = ["Library", "Title", "Due Date", "Days Remaining"]
            
            try:
                if effective_format == OutputFormat.csv:
                    content = format_csv(headers, table_data)
                else:
                    content = format_markdown(headers, table_data, "Currently Checked Out Books")
                
                write_output(content, output, effective_format)
            except OSError as e:
                err_console.print(f"Error: Failed to write output: {e}")
                raise typer.Exit(code=1)
        else:
            # Display mode - show to console with rich formatting
            console.print("[bold]## Currently Checked Out Books[/bold]")
            console.print()
            
            if not books:
                console.print("No books currently checked out.")
            else:
                console.print(f"[bold]Total: {all_books.total_count} books[/bold]")
                console.print()
                
                table = Table(show_header=True, header_style="bold")
                table.add_column("Library", max_width=18)
                table.add_column("Title", max_width=58)
                table.add_column("Due Date")
                table.add_column("Days Remaining")
                
                for book in books:
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
