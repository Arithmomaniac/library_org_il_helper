# Library.org.il Helper

A Python workspace for interacting with library.org.il Israeli public library websites.

## Overview

This project provides tools for managing your library accounts across multiple Israeli public libraries that use the library.org.il platform.

## Packages

### library-il-client

The core utility library for interacting with individual library.org.il websites.

**Features:**
- Async/await API for efficient concurrent operations
- Login and session management
- Get currently checked out books
- Renew checked out books
- Get checkout history
- Download HTML pages for archiving or offline viewing

```python
import asyncio
from library_il_client import LibraryClient

async def main():
    async with LibraryClient("shemesh") as client:
        await client.login("your_teudat_zehut", "your_password")
        
        books = await client.get_checked_out_books()
        for book in books:
            print(f"{book.title} - due: {book.due_date}")

asyncio.run(main())
```

### library-il-aggregator

Aggregates data from multiple library.org.il websites into a unified view.

**Features:**
- Parallel fetching from multiple libraries for improved performance
- Combine books and history from multiple libraries
- CLI tool for quick access
- Sort by due date or return date

```bash
# Using the CLI
export TEUDAT_ZEHUT=your_teudat_zehut
library-il-aggregate --libraries shemesh betshemesh --all
```

## Installation

Using uv (recommended):

```bash
# Install the aggregator (includes client as dependency)
uv add library-il-aggregator

# Or install just the client
uv add library-il-client
```

Using pip:

```bash
pip install library-il-aggregator
# or
pip install library-il-client
```

## Development

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

```bash
# Clone the repository
git clone https://github.com/Arithmomaniac/library_org_il_helper.git
cd library_org_il_helper

# Install dependencies
uv sync

# Run tests
uv run pytest
```

## Supported Libraries

This project works with any library using the library.org.il platform, including:

- **shemesh.library.org.il** - Benjamin Children's Library (ספריית בנימין לילדים)
- **betshemesh.library.org.il** - Beit Shemesh Municipal Library (הספרייה העירונית בית שמש)
- And many other Israeli public libraries

## Environment Variables

| Variable | Description |
|----------|-------------|
| `TEUDAT_ZEHUT` | Israeli ID number, used as username and default password |
| `LIBRARY_PASSWORD` | Optional: password if different from TEUDAT_ZEHUT |

## Project Structure

```
library_org_il_helper/
├── pyproject.toml          # Workspace root configuration
├── packages/
│   ├── library_il_client/  # Core client library
│   │   ├── pyproject.toml
│   │   ├── README.md
│   │   └── src/
│   │       └── library_il_client/
│   │           ├── __init__.py
│   │           ├── client.py
│   │           └── models.py
│   └── library_il_aggregator/  # Aggregator for multiple libraries
│       ├── pyproject.toml
│       ├── README.md
│       └── src/
│           └── library_il_aggregator/
│               ├── __init__.py
│               ├── aggregator.py
│               ├── cli.py
│               └── models.py
└── README.md
```

## License

Apache-2.0
