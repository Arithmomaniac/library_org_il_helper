"""Command-line interface for viewing book copies across multiple libraries."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from library_il_aggregator import SearchAggregator
from library_il_aggregator.export_utils import (
    OutputFormat,
    format_csv,
    format_markdown,
    write_output,
)

app = typer.Typer(
    help="View book copies from multiple library.org.il websites",
    add_completion=False,
)

console = Console()
err_console = Console(stderr=True)

# Display truncation constants
MAX_TITLE_LEN = 40
MAX_AUTHOR_LEN = 25
MAX_ID_LEN = 15


def truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len, adding '...' suffix if needed."""
    if len(text) > max_len:
        return text[:max_len - 3] + "..."
    return text


def main() -> None:
    """Main entry point for the copies CLI."""
    app()


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


@app.command()
def copies(
    books_args: Annotated[
        list[str],
        typer.Argument(help="One or more slug:id pairs (e.g., shemesh:ABC123 betshemesh:DEF456)"),
    ],
    config: Annotated[
        Optional[str],
        typer.Option("--config", "-c", help="Path to JSON config file with account credentials"),
    ] = None,
    username: Annotated[
        Optional[str],
        typer.Option("--username", "-u", help="Username (Teudat Zehut). Uses TEUDAT_ZEHUT env var if not provided."),
    ] = None,
    password: Annotated[
        Optional[str],
        typer.Option("--password", "-p", help="Password. Uses LIBRARY_PASSWORD env var if not provided."),
    ] = None,
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
    View book copies from multiple library.org.il websites.
    
    Examples:
    
        # View copies for a single book (public data only)
        
        library-il-copies shemesh:ABC123
        
        # View copies with authentication (shows status, return dates)
        
        library-il-copies shemesh:ABC123 --username YOUR_TZ --password YOUR_PASS
        
        # Use environment variables for credentials
        
        export TEUDAT_ZEHUT=your_tz
        
        export LIBRARY_PASSWORD=your_password
        
        library-il-copies shemesh:ABC123 betshemesh:DEF456
        
        # Export to CSV file
        
        library-il-copies shemesh:ABC123 --output copies.csv
        
        # Export to stdout in CSV format
        
        library-il-copies shemesh:ABC123 --format csv
        
        # Export to Markdown file
        
        library-il-copies shemesh:ABC123 --output copies.md --format markdown
    
    Format:
    
        Each positional argument should be a slug:id pair where:
        
        - slug: Library identifier (e.g., "shemesh", "betshemesh")
        
        - id: Title ID from the library catalog (visible in URLs)
    
    Authentication:
    
        When authenticated, additional columns are available:
        
        - Status (e.g., "מושאל" = checked out, "זמין" = available)
        
        - Return Date (when a copy is checked out)
        
        - Hold count for the title
    """
    asyncio.run(async_copies(
        books_args=books_args,
        config=config,
        username=username,
        password=password,
        output=output,
        output_format=output_format,
    ))


async def async_copies(
    books_args: list[str],
    config: Optional[str],
    username: Optional[str],
    password: Optional[str],
    output: Optional[str],
    output_format: Optional[OutputFormat],
) -> None:
    """Async main function for the copies CLI."""
    
    # Parse the slug-id pairs
    slug_id_pairs: list[tuple[str, str]] = []
    for arg in books_args:
        try:
            pair = parse_slug_id(arg)
            slug_id_pairs.append(pair)
        except ValueError as e:
            err_console.print(f"Error: {e}")
            raise typer.Exit(code=1)
    
    if not slug_id_pairs:
        err_console.print("Error: At least one slug:id pair is required")
        raise typer.Exit(code=1)
    
    # Get unique library slugs for the aggregator
    unique_slugs = list(dict.fromkeys(slug for slug, _ in slug_id_pairs))
    
    # Build credentials map from arguments
    credentials: dict[str, tuple[str, str]] = {}
    
    if config:
        # Load from config file
        try:
            with open(config) as f:
                config_data = json.load(f)
            
            for item in config_data:
                slug = item["slug"]
                if slug in unique_slugs:
                    credentials[slug] = (item["username"], item["password"])
        except FileNotFoundError:
            err_console.print(f"Error: Config file not found: {config}")
            raise typer.Exit(code=1)
        except (json.JSONDecodeError, KeyError) as e:
            err_console.print(f"Error: Invalid config file: {e}")
            raise typer.Exit(code=1)
    else:
        # Use --username/--password or environment variables
        resolved_username = username or os.environ.get("TEUDAT_ZEHUT", "")
        resolved_password = password or os.environ.get("LIBRARY_PASSWORD", "")
        
        if resolved_username and resolved_password:
            # Apply same credentials to all unique slugs
            for slug in unique_slugs:
                credentials[slug] = (resolved_username, resolved_password)
    
    # Determine if we're exporting or displaying
    is_exporting = output is not None or output_format is not None
    effective_format = output_format or OutputFormat.csv
    
    async with SearchAggregator(unique_slugs) as aggregator:
        # Login if credentials were provided (in parallel)
        if credentials:
            if not is_exporting:
                console.print(f"Logging in to {len(credentials)} library(s)...")
            login_results = await aggregator.login_all(credentials)
            if not is_exporting:
                for slug, success in login_results.items():
                    status = "✓" if success else "✗"
                    console.print(f"  {status} {slug}")
                console.print()
        
        if not is_exporting:
            console.print(f"Fetching copies from {len(unique_slugs)} library(s): {', '.join(unique_slugs)}")
            console.print()
        
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
        
        # Show errors if any (only in display mode)
        if errors and not is_exporting:
            console.print("[bold red]Errors:[/bold red]")
            for error in errors:
                console.print(f"  ✗ {error}")
            console.print()
        
        if not all_copies_data:
            if is_exporting:
                err_console.print("Warning: No copies found.")
            else:
                console.print("No copies found.")
            raise typer.Exit(code=0)
        
        # Prepare table data (full data for export)
        headers = ["Library", "ID", "Title", "Author", "Barcode", "Status", "Location", "Classification", "Shelf", "Return Date"]
        table_data_full: list[list[str]] = []
        for row in all_copies_data:
            row_data = [
                row["slug"],
                row["id"],
                row["title"],
                row["author"],
                row["barcode"],
                row["status"],
                row["location"],
                row["classification"],
                row["shelf_sign"],
                row["return_date"],
            ]
            table_data_full.append(row_data)
        
        if is_exporting:
            # Export mode
            try:
                if effective_format == OutputFormat.csv:
                    content = format_csv(headers, table_data_full)
                else:
                    content = format_markdown(headers, table_data_full, "Book Copies")
                
                write_output(content, output, effective_format)
            except OSError as e:
                err_console.print(f"Error: Failed to write output: {e}")
                raise typer.Exit(code=1)
        else:
            # Display mode - show to console with rich formatting
            console.print("[bold]## Book Copies[/bold]")
            console.print()
            console.print(f"[bold]Total: {len(all_copies_data)} copies[/bold]")
            console.print()
            
            # Use rich table for display with truncation
            table = Table(show_header=True, header_style="bold")
            table.add_column("Library")
            table.add_column("ID", max_width=MAX_ID_LEN)
            table.add_column("Title", max_width=MAX_TITLE_LEN)
            table.add_column("Author", max_width=MAX_AUTHOR_LEN)
            table.add_column("Barcode")
            table.add_column("Status")
            table.add_column("Location")
            table.add_column("Classification")
            table.add_column("Shelf")
            table.add_column("Return Date")
            
            for row in all_copies_data:
                table.add_row(
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
                )
            
            console.print(table)
            
            # Show note if no authenticated data was found
            if not has_authenticated_data:
                console.print()
                console.print("[dim]Note: Status and Return Date columns require authentication.[/dim]")
                console.print("[dim]Use --username and --password, or set TEUDAT_ZEHUT and LIBRARY_PASSWORD.[/dim]")


if __name__ == "__main__":
    app()
