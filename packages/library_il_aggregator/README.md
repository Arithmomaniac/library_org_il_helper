# Library IL Aggregator

Aggregates library data from multiple library.org.il Israeli public library websites.

## Features

- **Async/Await API**: Modern async implementation with parallel operations for improved performance
- **Multi-Library Support**: Combine data from multiple libraries into a single view
- **Multi-Account Support**: Use different accounts at the same library (e.g., family members)
- **Per-Library Credentials**: Each library/account can have different credentials
- **Parallel Fetching**: Fetch data from all libraries simultaneously for faster results
- **Unified Checked Out Books**: See all currently borrowed books across all accounts
- **Combined History**: View checkout history from all accounts sorted by date
- **File Export**: Export data to CSV or Markdown files with full UTF-8 support
- **CLI Tool**: Command-line interface for quick access
- **Config File Support**: Store account credentials in a JSON config file

## Installation

```bash
uv add library-il-aggregator
```

Or with pip:

```bash
pip install library-il-aggregator
```

## Usage

### Command Line

```bash
# Set credentials via environment variables
export TEUDAT_ZEHUT=your_teudat_zehut
export LIBRARY_PASSWORD=your_password

# Get checked out books from both libraries (same credentials)
library-il-aggregate --libraries shemesh betshemesh --books

# Get checkout history
library-il-aggregate --libraries shemesh betshemesh --history

# Get everything
library-il-aggregate --all

# Use a config file for multiple accounts
library-il-aggregate --config accounts.json --all

# Export to CSV file (default format)
library-il-aggregate --books --output books.csv

# Export to Markdown file
library-il-aggregate --all --output results.md --format markdown

# Limit results
library-il-aggregate --history --limit 20
```

### Config File Format

Create a JSON file (e.g., `accounts.json`) for multiple accounts:

```json
[
  {"slug": "shemesh", "username": "parent_tz", "password": "parent_pass", "label": "parent"},
  {"slug": "shemesh", "username": "child_tz", "password": "child_pass", "label": "child"},
  {"slug": "betshemesh", "username": "parent_tz", "password": "parent_pass"}
]
```

The `label` field is optional and helps distinguish multiple accounts at the same library.

### Python API

#### Multiple Accounts at Same Library

```python
import asyncio
from library_il_aggregator import LibraryAccount, LibraryAggregator

async def main():
    # Define accounts - can have multiple accounts per library
    accounts = [
        LibraryAccount("shemesh", "parent_tz", "parent_pass", label="parent"),
        LibraryAccount("shemesh", "child_tz", "child_pass", label="child"),
        LibraryAccount("betshemesh", "parent_tz", "parent_pass"),
    ]
    
    async with LibraryAggregator(accounts) as aggregator:
        # Login to all accounts (runs in parallel)
        results = await aggregator.login_all()
        
        # Get all checked out books from all accounts (fetched in parallel)
        all_books = await aggregator.get_all_checked_out_books()
        
        for book in all_books.sorted_by_due_date():
            print(f"[{book.library_slug}] {book.title} - due {book.due_date}")

asyncio.run(main())
```

#### Same Credentials Across Libraries

```python
import asyncio
from library_il_aggregator import LibraryAggregator

async def main():
    # Convenience method when using same credentials
    async with LibraryAggregator.from_slugs(
        ["shemesh", "betshemesh"],
        username="your_tz",
        password="your_password"
    ) as aggregator:
        await aggregator.login_all()
        
        books = await aggregator.get_all_checked_out_books()
        print(f"Total books: {books.total_count}")
        
        history = await aggregator.get_all_checkout_history()
        for item in history.sorted_by_return_date()[:10]:
            print(f"[{item.library_slug}] {item.title}")

asyncio.run(main())
```

## Data Models

### LibraryAccount

```python
@dataclass
class LibraryAccount:
    slug: str           # Library identifier (e.g., "shemesh")
    username: str       # Teudat Zehut
    password: str       # Password
    label: str = None   # Optional label for multiple accounts
```

### AggregatedBooks

```python
@dataclass
class AggregatedBooks:
    books: list[CheckedOutBook]
    libraries: list[str]    # Account IDs that were queried
    errors: dict[str, str]  # Any errors that occurred
    
    @property
    def total_count(self) -> int: ...
    
    @property
    def by_library(self) -> dict[str, list[CheckedOutBook]]: ...
    
    def sorted_by_due_date(self) -> list[CheckedOutBook]: ...
```

### AggregatedHistory

```python
@dataclass
class AggregatedHistory:
    items: list[HistoryItem]
    libraries: list[str]
    errors: dict[str, str]
    
    @property
    def total_count(self) -> int: ...
    
    @property
    def by_library(self) -> dict[str, list[HistoryItem]]: ...
    
    def sorted_by_return_date(self, descending: bool = True) -> list[HistoryItem]: ...
```

## Example Output

```
Logging in to 3 account(s)...
  ✓ shemesh:parent
  ✓ shemesh:child
  ✓ betshemesh:parent_tz

============================================================
CURRENTLY CHECKED OUT BOOKS
============================================================
  Total: 9 books

  [shemesh] רוני ותום 4 החקירה הרביעית (due: 2026-01-16, 25 days)
  [shemesh] אגודת בנדיקט הסודית (due: 2026-01-16, 25 days)
  [betshemesh] אני, רובוט (1) (due: 2026-01-16, 25 days)

============================================================
CHECKOUT HISTORY
============================================================
  Total: 200 items

  [shemesh] כסח 17 טיול ג'יפים למכתשים by רון-פדר, גלילה (returned: 2025-12-17)
  [betshemesh] סיפורי ממלכת נרניה by לואיס, ק"ס (returned: 2025-12-17)
```

## License

Apache-2.0
