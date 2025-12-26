"""Client for interacting with library.org.il websites."""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from library_il_client.models import (
    CheckedOutBook,
    HistoryItem,
    PaginatedHistory,
    RenewalResult,
    SearchResult,
    SearchResults,
)


class LibraryClientError(Exception):
    """Base exception for library client errors."""
    pass


class LoginError(LibraryClientError):
    """Raised when login fails."""
    pass


class SessionExpiredError(LibraryClientError):
    """Raised when the session has expired."""
    pass


class LibraryClient:
    """
    Async client for interacting with library.org.il Israeli public library websites.
    
    This client manages HTTP sessions and provides async methods to:
    - Login to the library website
    - Get currently checked out books
    - Renew checked out books
    - Get checkout history with pagination
    
    The library.org.il websites are based on Joomla with the Agron library component.
    
    Example:
        >>> async with LibraryClient("shemesh") as client:
        ...     await client.login("your_teudat_zehut", "your_password")
        ...     books = await client.get_checked_out_books()
        ...     for book in books:
        ...         print(book)
    
    Using environment variables:
        >>> import os
        >>> os.environ["TEUDAT_ZEHUT"] = "your_teudat_zehut"
        >>> os.environ["LIBRARY_PASSWORD"] = "your_password"
        >>> async with LibraryClient("shemesh") as client:
        ...     await client.login()  # Uses environment variables
        ...     history = await client.get_checkout_history()
    """
    
    # Hebrew day names to strip from dates
    HEBREW_DAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]
    
    def __init__(
        self,
        library_slug: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """
        Initialize the library client.
        
        Args:
            library_slug: The library identifier (e.g., "shemesh" for shemesh.library.org.il)
            username: The username (Teudat Zehut). If not provided, uses TEUDAT_ZEHUT env var.
            password: The password. If not provided, uses LIBRARY_PASSWORD env var.
        """
        self.library_slug = library_slug
        self.base_url = f"https://{library_slug}.library.org.il"
        
        self._username = username or os.environ.get("TEUDAT_ZEHUT", "")
        self._password = password or os.environ.get("LIBRARY_PASSWORD", "")
        
        self._logged_in = False
        self._csrf_token: Optional[str] = None
        
        # Create async HTTP client with session management
        self._client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
    
    async def __aenter__(self) -> "LibraryClient":
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
    
    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
    
    @property
    def is_logged_in(self) -> bool:
        """Check if the client is logged in."""
        return self._logged_in
    
    def _get_csrf_token(self, html: str) -> Optional[str]:
        """Extract CSRF token from HTML form.
        
        Joomla CSRF tokens are hidden inputs with 32-character hex names.
        """
        soup = BeautifulSoup(html, "lxml")
        
        for inp in soup.find_all("input", {"type": "hidden"}):
            name = inp.get("name", "")
            if name and len(name) == 32 and all(c in "0123456789abcdef" for c in name):
                return name
        
        return None
    
    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse a date string from the library website.
        
        Handles formats like:
        - "רביעי, 17/12/2025" (Hebrew day name, DD/MM/YYYY)
        - "17/12/2025" (DD/MM/YYYY)
        - "13/11/2025" (DD/MM/YYYY without day name)
        """
        if not date_str:
            return None
        
        date_str = date_str.strip()
        
        # Remove Hebrew day names
        for day in self.HEBREW_DAYS:
            date_str = date_str.replace(day, "").strip()
        
        # Remove leading comma and whitespace
        date_str = date_str.lstrip(", ").strip()
        
        # Try common formats
        formats = [
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%Y-%m-%d",
            "%d.%m.%Y",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        
        return None
    
    async def login(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> bool:
        """
        Login to the library website.
        
        Args:
            username: The username (Teudat Zehut). Uses stored value if not provided.
            password: The password. Uses stored value if not provided.
            
        Returns:
            True if login was successful.
            
        Raises:
            LoginError: If login fails.
        """
        username = username or self._username
        password = password or self._password
        
        if not username or not password:
            raise LoginError("Username and password are required")
        
        # Get the login page to obtain CSRF token
        login_url = urljoin(self.base_url, "/mng")
        response = await self._client.get(login_url)
        response.raise_for_status()
        
        self._csrf_token = self._get_csrf_token(response.text)
        
        # Prepare login form data
        form_data = {
            "username": username,
            "password": password,
            "option": "com_users",
            "task": "user.login",
            "return": "",
        }
        
        if self._csrf_token:
            form_data[self._csrf_token] = "1"
        
        # Submit login form
        response = await self._client.post(
            urljoin(self.base_url, "/mng?task=user.login"),
            data=form_data,
        )
        response.raise_for_status()
        
        # Check if login was successful
        soup = BeautifulSoup(response.text, "lxml")
        
        # Look for user menu links that only appear when logged in
        user_loans_link = soup.find("a", href="/user-loans")
        profile_in_url = "/profile" in str(response.url)
        
        # Check for error messages
        error_msg = soup.find(class_="alert-error") or soup.find(class_="alert-danger")
        if error_msg:
            raise LoginError(f"Login failed: {error_msg.get_text(strip=True)}")
        
        if user_loans_link or profile_in_url:
            self._logged_in = True
            self._username = username
            self._password = password
            return True
        
        # Check if we're still on login page with login form
        login_form = soup.find("form", {"id": "login-form"})
        if login_form:
            msg_container = soup.find(id="system-message-container")
            if msg_container:
                msg = msg_container.get_text(strip=True)
                if msg:
                    raise LoginError(f"Login failed: {msg}")
            raise LoginError("Login failed: credentials may be incorrect")
        
        # Assume success if we got redirected and no error
        self._logged_in = True
        self._username = username
        self._password = password
        return True
    
    def _ensure_logged_in(self) -> None:
        """Ensure the client is logged in, raising an error if not."""
        if not self._logged_in:
            raise LibraryClientError("Not logged in. Call login() first.")
    
    async def get_checked_out_books(self) -> list[CheckedOutBook]:
        """
        Get the list of currently checked out books.
        
        Returns:
            List of CheckedOutBook objects representing books currently on loan.
            
        Raises:
            LibraryClientError: If not logged in.
            SessionExpiredError: If the session has expired.
        """
        self._ensure_logged_in()
        
        response = await self._client.get(urljoin(self.base_url, "/user-loans"))
        response.raise_for_status()
        
        # Check if session expired (redirected to login)
        if "/mng" in str(response.url) and "profile" not in str(response.url):
            self._logged_in = False
            raise SessionExpiredError("Session has expired. Please login again.")
        
        return self._parse_loans_page(response.text)
    
    def _parse_loans_page(self, html: str) -> list[CheckedOutBook]:
        """Parse the loans page HTML to extract checked out books.
        
        The loans table has columns:
        - Checkbox (for renewal selection)
        - מס (Number)
        - מדיה (Media type)
        - מספר עותק (Copy number/barcode)
        - כותר (Title)
        - תאריך השאלה (Checkout date)
        - תאריך החזרה (Due date)
        - ימים נותרים (Days remaining)
        """
        books = []
        soup = BeautifulSoup(html, "lxml")
        
        # Find the loans table (has header with כותר)
        for table in soup.find_all("table"):
            header = table.find("th", string=lambda x: x and "כותר" in str(x))
            if not header:
                continue
            
            # Get all data rows
            rows = table.find_all("tr")
            for row in rows[1:]:  # Skip header row
                cells = row.find_all("td")
                if len(cells) < 5:
                    continue
                
                book = self._parse_loan_row(cells, row)
                if book:
                    books.append(book)
        
        return books
    
    def _parse_loan_row(self, cells, row) -> Optional[CheckedOutBook]:
        """Parse a single row from the loans table."""
        try:
            # Expected columns: checkbox, number, media, barcode, title, checkout_date, due_date, days_remaining
            if len(cells) < 5:
                return None
            
            # Get barcode from checkbox value
            checkbox = row.find("input", {"name": "cid[]"})
            barcode = checkbox.get("value") if checkbox else None
            
            # Get cell texts
            cell_texts = [cell.get_text(strip=True) for cell in cells]
            
            # Find indices based on content
            media_type = None
            title = None
            checkout_date = None
            due_date = None
            
            for i, text in enumerate(cell_texts):
                # Barcode column might have a link
                if cells[i].find("a") and text.isdigit():
                    if not barcode:
                        barcode = text
                    continue
                
                # Media type (usually "ספרים")
                if text in ["ספרים", "סרטים", "תקליטורים", "כתבי עת"]:
                    media_type = text
                    continue
                
                # Check for dates
                parsed_date = self._parse_date(text)
                if parsed_date:
                    if checkout_date is None:
                        checkout_date = parsed_date
                    elif due_date is None:
                        due_date = parsed_date
                    continue
                
                # Skip pure numbers (row number, days remaining)
                if text.isdigit():
                    continue
                
                # The remaining text is likely the title
                if text and len(text) > 2:
                    title = text
            
            if not title:
                return None
            
            return CheckedOutBook(
                title=title,
                barcode=barcode,
                media_type=media_type,
                checkout_date=checkout_date,
                due_date=due_date,
                library_slug=self.library_slug,
                can_renew=checkbox is not None,
            )
        except Exception:
            return None
    
    async def renew_book(self, book: CheckedOutBook) -> RenewalResult:
        """
        Renew a checked out book.
        
        Args:
            book: The book to renew. Must have a barcode.
            
        Returns:
            RenewalResult indicating success or failure.
            
        Raises:
            LibraryClientError: If not logged in or renewal fails.
        """
        self._ensure_logged_in()
        
        if not book.barcode:
            return RenewalResult(
                book=book,
                success=False,
                message="Cannot renew: no barcode available",
            )
        
        results = await self._renew_books([book.barcode])
        return results[0]
    
    async def renew_books(self, books: list[CheckedOutBook]) -> list[RenewalResult]:
        """
        Renew multiple checked out books.
        
        Args:
            books: List of books to renew. Each must have a barcode.
            
        Returns:
            List of RenewalResult for each book.
        """
        self._ensure_logged_in()
        
        barcodes = [b.barcode for b in books if b.barcode]
        if not barcodes:
            return [
                RenewalResult(book=b, success=False, message="No barcode available")
                for b in books
            ]
        
        return await self._renew_books(barcodes, books)
    
    async def _renew_books(
        self,
        barcodes: list[str],
        books: Optional[list[CheckedOutBook]] = None,
    ) -> list[RenewalResult]:
        """Submit renewal request for books by barcode."""
        # The renewal form posts to /index.php/user-loans?task=length&view=loans
        # with cid[] containing the barcodes
        
        form_data = {
            "task": "length",
            "boxchecked": str(len(barcodes)),
        }
        
        # Add each barcode as cid[]
        for barcode in barcodes:
            if "cid[]" not in form_data:
                form_data["cid[]"] = []
            if isinstance(form_data["cid[]"], list):
                form_data["cid[]"].append(barcode)
        
        response = await self._client.post(
            urljoin(self.base_url, "/index.php/user-loans?task=length&view=loans"),
            data=form_data,
        )
        response.raise_for_status()
        
        # Parse the response to determine success
        return self._parse_renewal_response(response.text, barcodes, books)
    
    def _parse_renewal_response(
        self,
        html: str,
        barcodes: list[str],
        books: Optional[list[CheckedOutBook]] = None,
    ) -> list[RenewalResult]:
        """Parse the response from a renewal request."""
        soup = BeautifulSoup(html, "lxml")
        
        # Look for system messages
        msg_container = soup.find(id="system-message-container")
        message = ""
        if msg_container:
            message = msg_container.get_text(strip=True)
        
        # Check for success/error indicators
        success_keywords = ["הוארך", "הצלחה", "חודש", "הארכה בוצעה"]
        error_keywords = ["שגיאה", "נכשל", "לא ניתן", "אי אפשר"]
        
        text = soup.get_text().lower()
        is_success = any(kw in text for kw in success_keywords)
        is_error = any(kw in text for kw in error_keywords)
        
        results = []
        
        # Re-parse the loans page to get new due dates
        new_books = self._parse_loans_page(html)
        barcode_to_book = {b.barcode: b for b in new_books if b.barcode}
        
        for i, barcode in enumerate(barcodes):
            book = books[i] if books and i < len(books) else CheckedOutBook(
                title=f"Book {barcode}",
                barcode=barcode,
                library_slug=self.library_slug,
            )
            
            new_due_date = None
            if barcode in barcode_to_book:
                new_due_date = barcode_to_book[barcode].due_date
            
            results.append(RenewalResult(
                book=book,
                success=is_success and not is_error,
                message=message,
                new_due_date=new_due_date,
            ))
        
        return results
    
    async def renew_all_books(self) -> list[RenewalResult]:
        """
        Renew all currently checked out books.
        
        Returns:
            List of RenewalResult for each book.
        """
        books = await self.get_checked_out_books()
        renewables = [b for b in books if b.can_renew and b.barcode]
        
        if not renewables:
            return []
        
        return await self.renew_books(renewables)
    
    async def get_checkout_history(self, page: int = 1) -> PaginatedHistory:
        """
        Get the checkout history (previously borrowed books).
        
        Note: The library.org.il websites typically return all history items
        in a single page, so pagination parameters may not have an effect.
        
        Args:
            page: Page number (1-indexed). May not be used by the server.
            
        Returns:
            PaginatedHistory containing history items.
            
        Raises:
            LibraryClientError: If not logged in.
        """
        self._ensure_logged_in()
        
        response = await self._client.get(urljoin(self.base_url, "/loans-history"))
        response.raise_for_status()
        
        # Check if session expired
        if "/mng" in str(response.url) and "profile" not in str(response.url):
            self._logged_in = False
            raise SessionExpiredError("Session has expired. Please login again.")
        
        items = self._parse_history_page(response.text)
        
        return PaginatedHistory(
            items=items,
            page=1,
            total_pages=1,
            total_items=len(items),
            has_next=False,
            has_previous=False,
        )
    
    def _parse_history_page(self, html: str) -> list[HistoryItem]:
        """Parse the history page HTML to extract previously borrowed books.
        
        The history table has columns:
        - מדיה (Media type)
        - מספר עותק (Copy number/barcode)
        - מחבר (Author)
        - כותר (Title)
        - תאריך השאלה (Checkout date)
        - תאריך החזרה (Return date)
        - ימי השאלה (Days borrowed)
        - ימי איחור (Days late)
        """
        items = []
        soup = BeautifulSoup(html, "lxml")
        
        # Find the history table
        for table in soup.find_all("table"):
            header = table.find("th", string=lambda x: x and "מחבר" in str(x))
            if not header:
                continue
            
            # Get column indices from headers
            headers = [th.get_text(strip=True) for th in table.find_all("th")]
            
            col_indices = {
                "media": self._find_header_index(headers, ["מדיה"]),
                "barcode": self._find_header_index(headers, ["מספר עותק"]),
                "author": self._find_header_index(headers, ["מחבר"]),
                "title": self._find_header_index(headers, ["כותר"]),
                "checkout_date": self._find_header_index(headers, ["תאריך השאלה"]),
                "return_date": self._find_header_index(headers, ["תאריך החזרה"]),
            }
            
            # Parse data rows
            rows = table.find_all("tr")
            for row in rows[1:]:  # Skip header
                cells = row.find_all("td")
                if len(cells) < 4:
                    continue
                
                item = self._parse_history_row(cells, col_indices)
                if item:
                    items.append(item)
        
        return items
    
    def _find_header_index(self, headers: list[str], keywords: list[str]) -> int:
        """Find the index of a header containing any of the keywords."""
        for i, h in enumerate(headers):
            for kw in keywords:
                if kw in h:
                    return i
        return -1
    
    def _parse_history_row(self, cells, col_indices: dict) -> Optional[HistoryItem]:
        """Parse a single row from the history table."""
        try:
            cell_texts = [cell.get_text(strip=True) for cell in cells]
            
            def get_cell(key: str) -> str:
                idx = col_indices.get(key, -1)
                if 0 <= idx < len(cell_texts):
                    return cell_texts[idx]
                return ""
            
            title = get_cell("title")
            if not title:
                return None
            
            return HistoryItem(
                title=title,
                author=get_cell("author") or None,
                barcode=get_cell("barcode") or None,
                media_type=get_cell("media") or None,
                checkout_date=self._parse_date(get_cell("checkout_date")),
                return_date=self._parse_date(get_cell("return_date")),
                library_slug=self.library_slug,
            )
        except Exception:
            return None
    
    async def get_all_checkout_history(self) -> list[HistoryItem]:
        """
        Get all checkout history items.
        
        Since library.org.il typically returns all items in one page,
        this is equivalent to get_checkout_history().items.
        
        Returns:
            List of all HistoryItem objects.
        """
        history = await self.get_checkout_history()
        return history.items
    
    async def search(
        self,
        title: Optional[str] = None,
        author: Optional[str] = None,
        series: Optional[str] = None,
        max_results: int = 20,
    ) -> SearchResults:
        """
        Search the library catalog.
        
        Note: This method does NOT require login - searches are public.
        
        Args:
            title: Search by title (כותר)
            author: Search by author (מחבר)
            series: Search by series (סדרה)
            max_results: Maximum number of results to return (default 20)
            
        Returns:
            SearchResults containing matching books.
        """
        # Get the search page to obtain CSRF token
        search_url = urljoin(self.base_url, "/agron-catalog/simple-search-submenu")
        response = await self._client.get(search_url)
        response.raise_for_status()
        
        csrf_token = self._get_csrf_token(response.text)
        
        # Build search form data
        form_data = self._build_search_form(title, author, series, csrf_token)
        
        # Submit search
        results_url = urljoin(self.base_url, "/index.php?option=com_agronsearch&task=results&Itemid=72")
        response = await self._client.post(results_url, data=form_data)
        response.raise_for_status()
        
        # Parse results from first page
        results = self._parse_search_results(response.text)
        
        # If we need more results and there are more pages, fetch additional pages
        if max_results > len(results.items) and results.has_next:
            remaining = max_results - len(results.items)
            page = 2
            
            while remaining > 0 and page <= results.total_pages:
                # Fetch next page
                next_results = await self._fetch_search_page(page)
                results.items.extend(next_results.items[:remaining])
                remaining -= len(next_results.items)
                page += 1
                
                if not next_results.items:
                    break
        
        # Limit results to max_results
        results.items = results.items[:max_results]
        
        return results
    
    def _build_search_form(
        self,
        title: Optional[str],
        author: Optional[str],
        series: Optional[str],
        csrf_token: Optional[str],
    ) -> dict:
        """Build the search form data."""
        # Field values for column0 select:
        # 0 = כותר (Title)
        # 1 = מחבר (Author)
        # 8 = סדרה (Series)
        
        form_data = {
            "column0": "0",  # Title by default
            "exprStr0": "",
            "matchBy0": "0",  # Anywhere in field
            "mediatype": "0",  # All media types
            "orderBy": "0",  # Order by catalog date
            "newSearch": "1",
        }
        
        # Set primary search field
        if title:
            form_data["column0"] = "0"  # Title
            form_data["exprStr0"] = title
        elif author:
            form_data["column0"] = "1"  # Author
            form_data["exprStr0"] = author
        elif series:
            form_data["column0"] = "8"  # Series
            form_data["exprStr0"] = series
        
        # Add CSRF token if available
        if csrf_token:
            form_data[csrf_token] = "1"
        
        return form_data
    
    async def _fetch_search_page(self, page: int) -> SearchResults:
        """Fetch a specific page of search results."""
        # The library uses a different URL pattern for pagination
        page_url = urljoin(
            self.base_url,
            f"/index.php/agron-catalog/search-results-menu?start={(page - 1) * 20}"
        )
        response = await self._client.get(page_url)
        response.raise_for_status()
        
        return self._parse_search_results(response.text)
    
    def _parse_search_results(self, html: str) -> SearchResults:
        """Parse search results from HTML."""
        soup = BeautifulSoup(html, "lxml")
        items = []
        total_count = 0
        total_pages = 1
        current_page = 1
        
        # Get total count
        for text in soup.stripped_strings:
            if "סה''כ תוצאות:" in text:
                match = re.search(r"(\d+)", text)
                if match:
                    total_count = int(match.group(1))
                    # Calculate total pages (20 results per page)
                    total_pages = (total_count + 19) // 20
                break
        
        # Check for "no results" message
        if any("לא נמצאו תוצאות" in str(text) for text in soup.stripped_strings):
            return SearchResults(
                items=[],
                total_count=0,
                page=1,
                total_pages=1,
                library_slug=self.library_slug,
            )
        
        # Find result items by looking for title links
        title_links = soup.find_all(
            "a", 
            href=lambda x: x and "view=details" in str(x) and "#copies" not in str(x)
        )
        
        for link in title_links:
            item = self._parse_search_item(link)
            if item:
                items.append(item)
        
        return SearchResults(
            items=items,
            total_count=total_count,
            page=current_page,
            total_pages=total_pages,
            library_slug=self.library_slug,
        )
    
    def _parse_search_item(self, title_link) -> Optional[SearchResult]:
        """Parse a single search result item."""
        try:
            title = title_link.get_text(strip=True)
            href = title_link.get("href", "")
            
            # Extract title_id from href
            match = re.search(r"titleId=([A-Za-z0-9]+)", href)
            title_id = match.group(1) if match else None
            
            # Find the parent container
            parent = title_link.find_parent("div", class_="title-details")
            if not parent:
                parent = title_link.find_parent("div")
            
            if not parent:
                return SearchResult(
                    title=title,
                    title_id=title_id,
                    library_slug=self.library_slug,
                )
            
            # Get the containing row for metadata
            row = parent.find_parent("div", class_="spost") or parent
            
            # Extract metadata
            author = None
            classification = None
            shelf_sign = None
            series = None
            series_number = None
            
            for text in row.stripped_strings:
                if text.startswith("מחברים:"):
                    author = text.replace("מחברים:", "").strip()
                elif text.startswith("מס' מיון:"):
                    classification = text.replace("מס' מיון:", "").strip()
                elif text.startswith("סימן מדף:"):
                    shelf_sign = text.replace("סימן מדף:", "").strip()
                elif text.startswith("סדרה:"):
                    series = text.replace("סדרה:", "").strip()
                elif text.startswith("מס' בסדרה:"):
                    series_number = text.replace("מס' בסדרה:", "").strip()
            
            return SearchResult(
                title=title,
                author=author,
                classification=classification,
                shelf_sign=shelf_sign,
                series=series,
                series_number=series_number,
                title_id=title_id,
                library_slug=self.library_slug,
            )
        except Exception:
            return None
