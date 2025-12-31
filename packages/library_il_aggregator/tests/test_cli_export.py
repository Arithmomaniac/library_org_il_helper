"""Tests for CLI export functionality.

These are unit tests that don't require network access or credentials.
"""

import csv
import os
import tempfile

import pytest

from library_il_aggregator.cli import export_to_csv, export_to_markdown


class TestExportFunctions:
    """Tests for the export_to_csv and export_to_markdown functions."""

    @pytest.fixture
    def sample_sections(self):
        """Sample data sections for testing."""
        return [
            (
                "Currently Checked Out Books",
                ["Library", "Title", "Due Date", "Days Remaining"],
                [
                    ["shemesh:123456789", "Harry Potter", "2024-01-15", "10"],
                    ["betshemesh:123456789", "The Hobbit", "2024-01-20", "15"],
                ],
            ),
            (
                "Checkout History",
                ["Library", "Title", "Author", "Return Date"],
                [
                    ["shemesh:123456789", "Book One", "Author A", "2024-01-01"],
                    ["betshemesh:123456789", "Book Two", "Author B", "2024-01-05"],
                ],
            ),
        ]

    @pytest.fixture
    def hebrew_sections(self):
        """Sample data with Hebrew characters for UTF-8 testing."""
        return [
            (
                "Currently Checked Out Books",
                ["Library", "Title", "Due Date", "Days Remaining"],
                [
                    ["shemesh:123456789", "הרפתקאות הארי פוטר", "2024-01-15", "10"],
                    ["betshemesh:123456789", "ספר מעניין מאוד", "2024-01-20", "15"],
                ],
            ),
        ]

    def test_export_to_csv_creates_file(self, sample_sections):
        """Test that export_to_csv creates a file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            filepath = f.name

        try:
            export_to_csv(sample_sections, filepath)
            assert os.path.exists(filepath)
            assert os.path.getsize(filepath) > 0
        finally:
            os.unlink(filepath)

    def test_export_to_csv_has_utf8_bom(self, sample_sections):
        """Test that CSV file starts with UTF-8 BOM for Excel compatibility."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            filepath = f.name

        try:
            export_to_csv(sample_sections, filepath)
            with open(filepath, "rb") as f:
                bom = f.read(3)
                assert bom == b"\xef\xbb\xbf", "CSV file should start with UTF-8 BOM"
        finally:
            os.unlink(filepath)

    def test_export_to_csv_content(self, sample_sections):
        """Test that CSV file contains the expected content."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            filepath = f.name

        try:
            export_to_csv(sample_sections, filepath)
            with open(filepath, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                rows = list(reader)

            # First section
            assert rows[0] == ["Currently Checked Out Books"]
            assert rows[1] == ["Library", "Title", "Due Date", "Days Remaining"]
            assert rows[2] == ["shemesh:123456789", "Harry Potter", "2024-01-15", "10"]
            assert rows[3] == ["betshemesh:123456789", "The Hobbit", "2024-01-20", "15"]

            # Empty row between sections
            assert rows[4] == []

            # Second section
            assert rows[5] == ["Checkout History"]
            assert rows[6] == ["Library", "Title", "Author", "Return Date"]
        finally:
            os.unlink(filepath)

    def test_export_to_csv_hebrew_content(self, hebrew_sections):
        """Test that CSV file correctly encodes Hebrew characters."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            filepath = f.name

        try:
            export_to_csv(hebrew_sections, filepath)
            with open(filepath, "r", encoding="utf-8-sig") as f:
                content = f.read()

            assert "הרפתקאות הארי פוטר" in content
            assert "ספר מעניין מאוד" in content
        finally:
            os.unlink(filepath)

    def test_export_to_markdown_creates_file(self, sample_sections):
        """Test that export_to_markdown creates a file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            filepath = f.name

        try:
            export_to_markdown(sample_sections, filepath)
            assert os.path.exists(filepath)
            assert os.path.getsize(filepath) > 0
        finally:
            os.unlink(filepath)

    def test_export_to_markdown_is_utf8(self, sample_sections):
        """Test that Markdown file is encoded as UTF-8."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            filepath = f.name

        try:
            export_to_markdown(sample_sections, filepath)
            # Should be readable as UTF-8 without errors
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            assert len(content) > 0
        finally:
            os.unlink(filepath)

    def test_export_to_markdown_content(self, sample_sections):
        """Test that Markdown file contains the expected content."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            filepath = f.name

        try:
            export_to_markdown(sample_sections, filepath)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            # Check section headers
            assert "## Currently Checked Out Books" in content
            assert "## Checkout History" in content

            # Check table content (markdown table format)
            assert "Harry Potter" in content
            assert "The Hobbit" in content
            assert "Book One" in content
            assert "Author A" in content
        finally:
            os.unlink(filepath)

    def test_export_to_markdown_hebrew_content(self, hebrew_sections):
        """Test that Markdown file correctly encodes Hebrew characters."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            filepath = f.name

        try:
            export_to_markdown(hebrew_sections, filepath)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            assert "הרפתקאות הארי פוטר" in content
            assert "ספר מעניין מאוד" in content
        finally:
            os.unlink(filepath)

    def test_export_to_markdown_github_table_format(self, sample_sections):
        """Test that Markdown file uses GitHub table format."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            filepath = f.name

        try:
            export_to_markdown(sample_sections, filepath)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            # GitHub table format uses pipes
            assert "|" in content
            # Should have header separator with dashes
            assert "---" in content or "-|-" in content
        finally:
            os.unlink(filepath)

    def test_export_single_section(self):
        """Test export with a single section."""
        sections = [
            (
                "Books",
                ["Title", "Author"],
                [["Book 1", "Author 1"]],
            ),
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            filepath = f.name

        try:
            export_to_csv(sections, filepath)
            with open(filepath, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                rows = list(reader)

            assert len(rows) == 3  # section name + headers + 1 data row
            assert rows[0] == ["Books"]
        finally:
            os.unlink(filepath)

    def test_export_empty_data(self):
        """Test export with empty data."""
        sections = [
            (
                "Empty Section",
                ["Column1", "Column2"],
                [],
            ),
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            filepath = f.name

        try:
            export_to_csv(sections, filepath)
            with open(filepath, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                rows = list(reader)

            assert len(rows) == 2  # section name + headers only
            assert rows[0] == ["Empty Section"]
            assert rows[1] == ["Column1", "Column2"]
        finally:
            os.unlink(filepath)
