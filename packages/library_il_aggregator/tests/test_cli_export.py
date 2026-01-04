"""Tests for CLI export functionality.

These are unit tests that don't require network access or credentials.
"""

import csv
import os
import tempfile

import pytest

from library_il_aggregator.cli import export_to_csv, export_to_markdown
from library_il_aggregator.export_utils import format_csv, format_markdown


class TestExportFunctions:
    """Tests for the export_to_csv and export_to_markdown functions."""

    @pytest.fixture
    def sample_section(self):
        """Sample single data section for testing."""
        return [
            (
                "Currently Checked Out Books",
                ["Library", "Title", "Due Date", "Days Remaining"],
                [
                    ["shemesh:123456789", "Harry Potter", "2024-01-15", "10"],
                    ["betshemesh:123456789", "The Hobbit", "2024-01-20", "15"],
                ],
            ),
        ]

    @pytest.fixture
    def multiple_sections(self):
        """Multiple data sections for testing markdown."""
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
    def hebrew_section(self):
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

    def test_export_to_csv_creates_file(self, sample_section):
        """Test that export_to_csv creates a file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            filepath = f.name

        try:
            export_to_csv(sample_section, filepath)
            assert os.path.exists(filepath)
            assert os.path.getsize(filepath) > 0
        finally:
            os.unlink(filepath)

    def test_export_to_csv_has_utf8_bom(self, sample_section):
        """Test that CSV file starts with UTF-8 BOM for Excel compatibility."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            filepath = f.name

        try:
            export_to_csv(sample_section, filepath)
            with open(filepath, "rb") as f:
                bom = f.read(3)
                assert bom == b"\xef\xbb\xbf", "CSV file should start with UTF-8 BOM"
        finally:
            os.unlink(filepath)

    def test_export_to_csv_content(self, sample_section):
        """Test that CSV file contains the expected content."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            filepath = f.name

        try:
            export_to_csv(sample_section, filepath)
            with open(filepath, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                rows = list(reader)

            # Headers and data (no section name row in new format)
            assert rows[0] == ["Library", "Title", "Due Date", "Days Remaining"]
            assert rows[1] == ["shemesh:123456789", "Harry Potter", "2024-01-15", "10"]
            assert rows[2] == ["betshemesh:123456789", "The Hobbit", "2024-01-20", "15"]
        finally:
            os.unlink(filepath)

    def test_export_to_csv_hebrew_content(self, hebrew_section):
        """Test that CSV file correctly encodes Hebrew characters."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            filepath = f.name

        try:
            export_to_csv(hebrew_section, filepath)
            with open(filepath, "r", encoding="utf-8-sig") as f:
                content = f.read()

            assert "הרפתקאות הארי פוטר" in content
            assert "ספר מעניין מאוד" in content
        finally:
            os.unlink(filepath)

    def test_export_to_csv_rejects_multiple_sections(self, multiple_sections):
        """Test that CSV export raises an error for multiple sections."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            filepath = f.name

        try:
            with pytest.raises(ValueError, match="multiple sections"):
                export_to_csv(multiple_sections, filepath)
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_export_to_markdown_creates_file(self, sample_section):
        """Test that export_to_markdown creates a file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            filepath = f.name

        try:
            export_to_markdown(sample_section, filepath)
            assert os.path.exists(filepath)
            assert os.path.getsize(filepath) > 0
        finally:
            os.unlink(filepath)

    def test_export_to_markdown_is_utf8(self, sample_section):
        """Test that Markdown file is encoded as UTF-8."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            filepath = f.name

        try:
            export_to_markdown(sample_section, filepath)
            # Should be readable as UTF-8 without errors
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            assert len(content) > 0
        finally:
            os.unlink(filepath)

    def test_export_to_markdown_content(self, multiple_sections):
        """Test that Markdown file contains the expected content."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            filepath = f.name

        try:
            export_to_markdown(multiple_sections, filepath)
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

    def test_export_to_markdown_hebrew_content(self, hebrew_section):
        """Test that Markdown file correctly encodes Hebrew characters."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            filepath = f.name

        try:
            export_to_markdown(hebrew_section, filepath)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            assert "הרפתקאות הארי פוטר" in content
            assert "ספר מעניין מאוד" in content
        finally:
            os.unlink(filepath)

    def test_export_to_markdown_github_table_format(self, sample_section):
        """Test that Markdown file uses GitHub table format."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            filepath = f.name

        try:
            export_to_markdown(sample_section, filepath)
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

            assert len(rows) == 2  # headers + 1 data row
            assert rows[0] == ["Title", "Author"]
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

            assert len(rows) == 1  # headers only
            assert rows[0] == ["Column1", "Column2"]
        finally:
            os.unlink(filepath)


class TestFormatFunctions:
    """Tests for the format_csv and format_markdown functions."""

    def test_format_csv_has_bom(self):
        """Test that format_csv output starts with UTF-8 BOM."""
        headers = ["A", "B"]
        data = [["1", "2"]]
        result = format_csv(headers, data)
        assert result.startswith("\ufeff")

    def test_format_csv_content(self):
        """Test that format_csv produces correct CSV content."""
        headers = ["Name", "Value"]
        data = [["test", "123"]]
        result = format_csv(headers, data)
        # Remove BOM for comparison
        result = result.lstrip("\ufeff")
        assert "Name,Value" in result
        assert "test,123" in result

    def test_format_markdown_with_title(self):
        """Test that format_markdown includes the title."""
        headers = ["A", "B"]
        data = [["1", "2"]]
        result = format_markdown(headers, data, title="My Section")
        assert "## My Section" in result

    def test_format_markdown_without_title(self):
        """Test that format_markdown works without a title."""
        headers = ["A", "B"]
        data = [["1", "2"]]
        result = format_markdown(headers, data)
        assert "##" not in result
        assert "|" in result
