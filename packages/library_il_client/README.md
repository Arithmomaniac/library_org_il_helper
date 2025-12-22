# Library IL Client

A Python utility library for interacting with library.org.il Israeli public library websites.

## Features

- **Session Management**: Maintains authenticated HTTP sessions for interacting with library websites
- **Get Checked Out Books**: Retrieve the list of currently borrowed books with due dates
- **Renew Books**: Renew checked out books to extend their due dates
- **Checkout History**: Get the complete history of previously borrowed books

## Installation

```bash
uv add library-il-client
```

Or with pip:

```bash
pip install library-il-client
```

## Usage

### Basic Usage

```python
from library_il_client import LibraryClient

# Create a client for a specific library (e.g., shemesh.library.org.il)
with LibraryClient("shemesh") as client:
    # Login with your Teudat Zehut (often used as both username and password)
    client.login("your_teudat_zehut", "your_password")
    
    # Get currently checked out books
    books = client.get_checked_out_books()
    for book in books:
        print(f"{book.title} - due: {book.due_date}")
    
    # Get checkout history
    history = client.get_checkout_history()
    for item in history.items:
        print(f"{item.title} by {item.author}")
```

### Using Environment Variables

```python
import os
from library_il_client import LibraryClient

# Set TEUDAT_ZEHUT environment variable (used as both username and password)
os.environ["TEUDAT_ZEHUT"] = "your_teudat_zehut"

with LibraryClient("betshemesh") as client:
    client.login()  # Uses TEUDAT_ZEHUT automatically
    books = client.get_checked_out_books()
```

### Renewing Books

```python
from library_il_client import LibraryClient

with LibraryClient("shemesh") as client:
    client.login("your_teudat_zehut", "your_password")
    
    # Renew all books
    results = client.renew_all_books()
    for result in results:
        if result.success:
            print(f"✓ {result.book.title} - new due date: {result.new_due_date}")
        else:
            print(f"✗ {result.book.title} - {result.message}")
    
    # Or renew specific books
    books = client.get_checked_out_books()
    if books:
        result = client.renew_book(books[0])
        print(f"Renewal {'succeeded' if result.success else 'failed'}")
```

## Supported Libraries

This library works with any library using the library.org.il platform, including:

- `shemesh.library.org.il` (Benjamin Children's Library)
- `betshemesh.library.org.il` (Beit Shemesh Municipal Library)
- And many other Israeli public libraries on the same platform

## Data Models

### CheckedOutBook

```python
@dataclass
class CheckedOutBook:
    title: str
    author: Optional[str]
    barcode: Optional[str]
    media_type: Optional[str]  # e.g., "ספרים" (books)
    checkout_date: Optional[date]
    due_date: Optional[date]
    library_slug: Optional[str]
    can_renew: bool
```

### HistoryItem

```python
@dataclass
class HistoryItem:
    title: str
    author: Optional[str]
    barcode: Optional[str]
    media_type: Optional[str]
    checkout_date: Optional[date]
    return_date: Optional[date]
    library_slug: Optional[str]
```

### RenewalResult

```python
@dataclass
class RenewalResult:
    book: CheckedOutBook
    success: bool
    message: str
    new_due_date: Optional[date]
```

## Error Handling

```python
from library_il_client import LibraryClient, LoginError, SessionExpiredError

try:
    with LibraryClient("shemesh") as client:
        client.login("invalid", "credentials")
except LoginError as e:
    print(f"Login failed: {e}")

try:
    with LibraryClient("shemesh") as client:
        client.login("your_teudat_zehut", "your_password")
        # ... later, if session expires ...
        books = client.get_checked_out_books()
except SessionExpiredError:
    print("Session expired, please login again")
```

## License

Apache-2.0
