"""Tests for ptk.exports.html module (C6 workspace contract).

Shape: single self-contained .html file with

- inlined sql-wasm.js (vendored; no CDN)
- base64-encoded sql-wasm.wasm (decoded via ``initSqlJs({wasmBinary:...})``)
- gzipped + base64-encoded SQLite database, decompressed in-browser via
  ``DecompressionStream('gzip')``
"""

import base64
import gzip
import re
import sqlite3
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def html_export(populated_library, temp_dir):
    """Export HTML and return the path."""
    from ptk.exports.html import export_html

    output = temp_dir / "gallery.html"
    export_html(output)
    return output


def _extract_base64_from_script(content: str, script_id: str) -> bytes:
    match = re.search(
        rf'<script id="{re.escape(script_id)}" type="application/base64">\s*'
        r'([A-Za-z0-9+/=\s]+?)\s*</script>',
        content,
    )
    assert match is not None, f"script id={script_id!r} not found"
    return base64.b64decode("".join(match.group(1).split()))


def _db_bytes(content: str) -> bytes:
    gz = _extract_base64_from_script(content, "pm-db-b64")
    assert gz[:2] == b"\x1f\x8b", "expected gzip magic header"
    return gzip.decompress(gz)


class TestExportHtml:
    """Tests for the export_html function."""

    def test_creates_output_file(self, html_export):
        assert html_export.exists()
        assert html_export.stat().st_size > 0

    def test_output_is_html(self, html_export):
        content = html_export.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "<html" in content
        assert "</html>" in content

    def test_inlines_vendored_sqljs(self, html_export):
        content = html_export.read_text(encoding="utf-8")
        assert "initSqlJs" in content
        # No CDN references allowed in the single-file bundle.
        for smell in ("cdnjs.cloudflare.com", "cdn.jsdelivr.net", "unpkg.com"):
            assert smell not in content, f"unexpected CDN ref {smell!r}"

    def test_embeds_wasm_base64(self, html_export):
        content = html_export.read_text(encoding="utf-8")
        blob = _extract_base64_from_script(content, "pm-wasm-b64")
        assert blob[:4] == b"\x00asm"
        assert len(blob) > 100_000  # full sql.js wasm is ~650 KB

    def test_embeds_gzipped_db(self, html_export):
        content = html_export.read_text(encoding="utf-8")
        raw = _db_bytes(content)
        assert raw[:16].startswith(b"SQLite format 3\x00")

    def test_default_title(self, html_export):
        content = html_export.read_text(encoding="utf-8")
        assert "photo-memex Photo Library" in content

    def test_custom_title(self, populated_library, temp_dir):
        from ptk.exports.html import export_html

        output = temp_dir / "custom_title.html"
        export_html(output, title="My Custom Gallery")
        assert "My Custom Gallery" in output.read_text(encoding="utf-8")

    def test_custom_output_path(self, populated_library, temp_dir):
        from ptk.exports.html import export_html

        subdir = temp_dir / "subdir" / "nested"
        output = subdir / "export.html"
        export_html(output)
        assert output.exists()

    def test_output_is_single_file(self, html_export):
        parent = html_export.parent
        html_files = list(parent.glob("gallery*"))
        assert len(html_files) == 1

    def test_embedded_db_has_photos_table(self, html_export):
        content = html_export.read_text(encoding="utf-8")
        db_bytes = _db_bytes(content)
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

    def test_embedded_db_has_no_heavy_blobs(self, html_export):
        """Legacy heavy columns (embeddings, face thumbnail_data) are stripped."""
        content = html_export.read_text(encoding="utf-8")
        db_bytes = _db_bytes(content)
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp.write(db_bytes)
            tmp_path = Path(tmp.name)
        try:
            conn = sqlite3.connect(str(tmp_path))
            tables = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
            # If the legacy table still exists (older DBs), it must be empty.
            if "photo_embeddings" in tables:
                count = conn.execute(
                    "SELECT count(*) FROM photo_embeddings"
                ).fetchone()[0]
                assert count == 0
            conn.close()
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_returns_photo_count(self, populated_library, temp_dir):
        from ptk.exports.html import export_html

        output = temp_dir / "count_test.html"
        count = export_html(output)
        assert count >= 1

    def test_output_contains_photos_query(self, html_export):
        content = html_export.read_text(encoding="utf-8")
        assert "photos" in content

    def test_output_contains_search_ui(self, html_export):
        content = html_export.read_text(encoding="utf-8")
        assert "search" in content.lower()
        assert "filter" in content.lower() or "sidebar" in content.lower()

    def test_output_contains_lightbox(self, html_export):
        content = html_export.read_text(encoding="utf-8")
        assert "lightbox" in content.lower()

    def test_decompression_stream_used(self, html_export):
        """Client must use DecompressionStream('gzip') to load the DB."""
        content = html_export.read_text(encoding="utf-8")
        assert "DecompressionStream" in content
        assert "gzip" in content
