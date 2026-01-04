"""Shared utilities for exporting data to CSV and Markdown formats."""

from __future__ import annotations

import csv
import io
import sys
from enum import Enum
from typing import Optional

from rich.console import Console
from tabulate import tabulate


class OutputFormat(str, Enum):
    """Output format for export."""
    csv = "csv"
    markdown = "markdown"


console = Console()


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
