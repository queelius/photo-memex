"""Tests for photo_memex.exports.html module (C6 workspace contract).

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
    from photo_memex.exports.html import export_html

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
        from photo_memex.exports.html import export_html

        output = temp_dir / "custom_title.html"
        export_html(output, title="My Custom Gallery")
        assert "My Custom Gallery" in output.read_text(encoding="utf-8")

    def test_title_is_html_escaped(self, populated_library, temp_dir):
        """F12: the caller-supplied --title lands in <title>/<h1> and must be
        escaped so it cannot inject markup into a published gallery."""
        from photo_memex.exports.html import export_html

        output = temp_dir / "evil_title.html"
        export_html(output, title="<script>alert(1)</script>")
        content = output.read_text(encoding="utf-8")
        assert "<script>alert(1)</script>" not in content
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in content

    def test_lightbox_img_built_via_dom(self, html_export):
        """F12: the lightbox <img> is built via the DOM with a validated mime,
        not string-concatenated from the unescaped thumbnail_mime column."""
        content = html_export.read_text(encoding="utf-8")
        assert "'<img src=\"data:' + mime" not in content
        assert "safeMime" in content
        assert 'createElement("img")' in content

    def test_custom_output_path(self, populated_library, temp_dir):
        from photo_memex.exports.html import export_html

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
        from photo_memex.exports.html import export_html

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


def _exported_db_conn(content: str):
    """Materialise the embedded DB to a temp file and open a connection."""
    db_bytes = _db_bytes(content)
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp.write(db_bytes)
        tmp_path = Path(tmp.name)
    conn = sqlite3.connect(str(tmp_path))
    return conn, tmp_path


class TestExportHtmlPrivacy:
    """A published bundle must not leak soft-deleted photos or FTS internals.

    The gallery template filters ``archived_at IS NULL`` in its queries, but
    the embedded SQLite file is fully readable by anyone who downloads the
    HTML, so archived rows have to be physically removed from the export copy
    (workspace 'treat exported HTML as public' contract). FTS5 shadow tables
    must also be dropped: sql.js cannot query them and they bloat the bundle
    (C6b).
    """

    @pytest.fixture
    def archived_photo_id(self, populated_library):
        """Insert a soft-deleted photo carrying a recognisable PII marker."""
        from datetime import datetime, timezone

        from photo_memex.db.models import Photo
        from photo_memex.db.session import get_session

        marker_id = "dead" + "0" * 60  # 64-char hex-shaped SHA256
        session = get_session()
        try:
            session.add(
                Photo(
                    id=marker_id,
                    original_path="/secret/diary.jpg",
                    filename="diary.jpg",
                    file_size=123,
                    mime_type="image/jpeg",
                    date_imported=datetime.now(timezone.utc),
                    caption="SECRET_CAPTION_DO_NOT_PUBLISH",
                    location_name="SECRET_LOCATION_DO_NOT_PUBLISH",
                    archived_at=datetime.now(timezone.utc),
                )
            )
            session.commit()
        finally:
            session.close()
        return marker_id

    def test_archived_photo_absent_from_export(self, archived_photo_id, temp_dir):
        from photo_memex.exports.html import export_html

        output = temp_dir / "privacy.html"
        export_html(output)
        content = output.read_text(encoding="utf-8")

        conn, tmp_path = _exported_db_conn(content)
        try:
            row = conn.execute(
                "SELECT count(*) FROM photos WHERE id = ?", (archived_photo_id,)
            ).fetchone()
            assert row[0] == 0, "soft-deleted photo leaked into published bundle"
            # And its PII strings must not survive anywhere in the DB image.
            assert b"SECRET_CAPTION_DO_NOT_PUBLISH" not in tmp_path.read_bytes()
            assert b"SECRET_LOCATION_DO_NOT_PUBLISH" not in tmp_path.read_bytes()
        finally:
            conn.close()
            tmp_path.unlink(missing_ok=True)

    def test_live_photo_survives_export(self, archived_photo_id, temp_dir):
        """The archived-row purge must not take live photos with it."""
        from photo_memex.exports.html import export_html

        output = temp_dir / "privacy_live.html"
        count = export_html(output)
        assert count >= 1
        content = output.read_text(encoding="utf-8")
        conn, tmp_path = _exported_db_conn(content)
        try:
            live = conn.execute(
                "SELECT count(*) FROM photos WHERE archived_at IS NULL"
            ).fetchone()[0]
            assert live >= 1
        finally:
            conn.close()
            tmp_path.unlink(missing_ok=True)

    def test_fts_tables_stripped(self, html_export):
        """photos_fts and its shadow tables must not ship (C6b)."""
        content = html_export.read_text(encoding="utf-8")
        conn, tmp_path = _exported_db_conn(content)
        try:
            names = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master"
                ).fetchall()
            }
            leaked = {n for n in names if n.startswith("photos_fts")}
            assert not leaked, f"FTS5 artifacts leaked into export: {sorted(leaked)}"
        finally:
            conn.close()
            tmp_path.unlink(missing_ok=True)
