#!/usr/bin/env python3
"""
Example script demonstrating how to download HTML pages from library.org.il websites.

This script shows how to use the download_page_html() method to save authenticated
pages for offline viewing or archiving.
"""

import asyncio
import os
from pathlib import Path

from library_il_client import LibraryClient


async def main():
    """Download HTML pages from library.org.il."""
    
    # Get credentials from environment variables
    username = os.environ.get("TEUDAT_ZEHUT")
    password = os.environ.get("LIBRARY_PASSWORD", username)
    
    if not username:
        print("Error: TEUDAT_ZEHUT environment variable not set")
        print("Usage: export TEUDAT_ZEHUT=your_id && python example_download_html.py")
        return
    
    # Create output directory for saved HTML files
    output_dir = Path("downloaded_html")
    output_dir.mkdir(exist_ok=True)
    
    # Connect to the library
    library = "shemesh"  # Change to your library's slug
    print(f"Connecting to {library}.library.org.il...")
    
    async with LibraryClient(library, username, password) as client:
        # Login
        print("Logging in...")
        await client.login()
        print("✓ Logged in successfully")
        
        # Download the user loans page
        print("\nDownloading user loans page...")
        loans_html = await client.download_page_html("/user-loans")
        loans_file = output_dir / "user_loans.html"
        loans_file.write_text(loans_html, encoding="utf-8")
        print(f"✓ Saved to {loans_file}")
        
        # Download the checkout history page
        print("\nDownloading checkout history page...")
        history_html = await client.download_page_html("/loans-history")
        history_file = output_dir / "checkout_history.html"
        history_file.write_text(history_html, encoding="utf-8")
        print(f"✓ Saved to {history_file}")
        
        print(f"\n✓ All pages downloaded successfully to {output_dir}/")
        print("\nYou can now open these HTML files in your browser for offline viewing.")


if __name__ == "__main__":
    asyncio.run(main())
