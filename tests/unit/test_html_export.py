"""Tests for ptk.exports.html module."""

import base64
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def html_export(populated_library, temp_dir):
    """Export HTML and return the path."""
    from ptk.exports.html import export_html

    output = temp_dir / "gallery.html"
    export_html(output)
    return output


class TestExportHtml:
    """Tests for the export_html function."""

    def test_creates_output_file(self, html_export):
        """export_html creates the output file."""
        assert html_export.exists()
        assert html_export.stat().st_size > 0

    def test_output_is_html(self, html_export):
        """Output file is a valid HTML document."""
        content = html_export.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "<html" in content
        assert "</html>" in content

    def test_contains_embedded_database(self, html_export):
        """Output contains embedded base64 SQLite database."""
        content = html_export.read_text(encoding="utf-8")
        assert 'id="db-data"' in content
        assert "application/x-sqlite3" in content

    def test_contains_sql_js_cdn_reference(self, html_export):
        """Output references sql.js CDN for loading the database."""
        content = html_export.read_text(encoding="utf-8")
        assert "sql.js" in content or "sql-wasm" in content

    def test_default_title(self, html_export):
        """Default title appears in the output."""
        content = html_export.read_text(encoding="utf-8")
        assert "photo-memex Photo Library" in content

    def test_custom_title(self, populated_library, temp_dir):
        """Custom title appears in the output."""
        from ptk.exports.html import export_html

        output = temp_dir / "custom_title.html"
        export_html(output, title="My Custom Gallery")
        content = output.read_text(encoding="utf-8")
        assert "My Custom Gallery" in content

    def test_custom_output_path(self, populated_library, temp_dir):
        """Custom output path works."""
        from ptk.exports.html import export_html

        subdir = temp_dir / "subdir" / "nested"
        output = subdir / "export.html"
        export_html(output)
        assert output.exists()

    def test_output_is_single_file(self, html_export):
        """Output is a single self-contained file."""
        parent = html_export.parent
        html_files = list(parent.glob("gallery*"))
        # Should only be the one HTML file — no sidecar files
        assert len(html_files) == 1

    def test_embedded_base64_is_valid(self, html_export):
        """The embedded base64 data can be decoded to a valid SQLite database."""
        content = html_export.read_text(encoding="utf-8")
        # Extract base64 data from the script tag
        start_marker = 'id="db-data">'
        end_marker = "</script>"
        start = content.index(start_marker) + len(start_marker)
        end = content.index(end_marker, start)
        b64_data = content[start:end].strip()

        # Must be valid base64
        db_bytes = base64.b64decode(b64_data)

        # Must start with SQLite magic header
        assert db_bytes[:16].startswith(b"SQLite format 3\x00")

    def test_embedded_db_has_photos_table(self, html_export):
        """The embedded database contains the photos table with data."""
        content = html_export.read_text(encoding="utf-8")
        start_marker = 'id="db-data">'
        end_marker = "</script>"
        start = content.index(start_marker) + len(start_marker)
        end = content.index(end_marker, start)
        b64_data = content[start:end].strip()

        db_bytes = base64.b64decode(b64_data)

        # Write to temp file and open with sqlite3
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp.write(db_bytes)
            tmp_path = Path(tmp.name)

        try:
            conn = sqlite3.connect(str(tmp_path))
            count = conn.execute("SELECT count(*) FROM photos").fetchone()[0]
            assert count >= 1
            conn.close()
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_embedded_db_has_no_embeddings(self, html_export):
        """The embedded database has no photo_embeddings data (table may not exist in new DBs)."""
        content = html_export.read_text(encoding="utf-8")
        start_marker = 'id="db-data">'
        end_marker = "</script>"
        start = content.index(start_marker) + len(start_marker)
        end = content.index(end_marker, start)
        b64_data = content[start:end].strip()

        db_bytes = base64.b64decode(b64_data)

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp.write(db_bytes)
            tmp_path = Path(tmp.name)

        try:
            conn = sqlite3.connect(str(tmp_path))
            # Table may not exist in databases created after the model was removed
            tables = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
            if "photo_embeddings" in tables:
                count = conn.execute("SELECT count(*) FROM photo_embeddings").fetchone()[0]
                assert count == 0
            conn.close()
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_returns_photo_count(self, populated_library, temp_dir):
        """export_html returns the number of photos."""
        from ptk.exports.html import export_html

        output = temp_dir / "count_test.html"
        count = export_html(output)
        assert count >= 1

    def test_output_contains_photos_query(self, html_export):
        """Output contains JavaScript that queries the photos table."""
        content = html_export.read_text(encoding="utf-8")
        assert "photos" in content

    def test_output_contains_search_ui(self, html_export):
        """Output contains search/filter UI elements."""
        content = html_export.read_text(encoding="utf-8")
        assert "search" in content.lower()
        assert "filter" in content.lower() or "sidebar" in content.lower()

    def test_output_contains_lightbox(self, html_export):
        """Output contains lightbox/detail view functionality."""
        content = html_export.read_text(encoding="utf-8")
        assert "lightbox" in content.lower()
