"""Export photo-memex library as a single-file HTML photo browser.

Workspace C6 contract: one self-contained ``.html`` with

  - inlined sql-wasm.js (vendored; no CDN)
  - base64-encoded sql-wasm.wasm (loaded via ``initSqlJs({wasmBinary:...})``)
  - gzipped + base64-encoded SQLite database, decompressed in-browser via
    ``DecompressionStream('gzip')``

The shipped DB preserves the library schema (photos, tags, albums, etc.)
minus heavy blobs (legacy embeddings, face thumbnail_data) to keep
bundle size reasonable. SQLite WAL-sidecars are never written because
the backup API produces a consistent snapshot and VACUUM runs in
autocommit mode.
"""

from __future__ import annotations

import base64
import contextlib
import gzip
import sqlite3
import tempfile
from pathlib import Path

from photo_memex.core.config import get_config


_VENDORED_DIR = Path(__file__).parent / "vendored"
_TEMPLATE_PATH = Path(__file__).parent / "templates" / "gallery.html"
# gzip level 6 is the sweet spot: near-maximum ratio, modest CPU.
_DB_GZIP_LEVEL = 6


def _read_vendor(name: str) -> bytes:
    return (_VENDORED_DIR / name).read_bytes()


def export_html(output_path: Path, title: str = "photo-memex Photo Library") -> int:
    """Export the library as a self-contained HTML file.

    Args:
        output_path: Where to write the HTML file.
        title: Title for the gallery page.

    Returns:
        Number of photos in the exported library.
    """
    config = get_config()
    db_path = config.database_path

    # Copy DB to temp file using SQLite backup API (handles WAL mode correctly).
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        src_conn = sqlite3.connect(str(db_path))
        dst_conn = sqlite3.connect(str(tmp_path))
        src_conn.backup(dst_conn)
        src_conn.close()

        # Enable cascade deletes so removing an archived photo also removes
        # its tag/album/event junctions and faces (all ON DELETE CASCADE).
        # PRAGMA foreign_keys is a no-op inside a transaction, so issue it
        # before any DML (sqlite3 does not open a transaction for PRAGMA).
        dst_conn.execute("PRAGMA foreign_keys=ON")

        # Soft-deleted photos must NOT ship in a published bundle: the
        # gallery filters archived_at IS NULL in its queries, but the rows
        # (caption, location_name, GPS) are trivially extractable from the
        # embedded sqlite file. Hard-delete them from the export copy.
        with contextlib.suppress(sqlite3.OperationalError):
            dst_conn.execute("DELETE FROM photos WHERE archived_at IS NOT NULL")

        photo_count = dst_conn.execute(
            "SELECT count(*) FROM photos WHERE archived_at IS NULL"
        ).fetchone()[0]

        # Strip heavy tables/columns (may not exist in newer databases).
        for stmt in [
            "DELETE FROM photo_embeddings",
            "UPDATE faces SET embedding = NULL, thumbnail_data = NULL",
        ]:
            with contextlib.suppress(sqlite3.OperationalError):
                dst_conn.execute(stmt)

        # Strip the FTS5 search table (C6b): sql.js cannot query FTS5, and
        # its shadow tables (_data/_idx/_docsize/_config) are ~half the DB.
        # Drop the sync triggers first so they cannot reference the table
        # after it is gone (the archived-photo DELETE above already fired
        # photos_fts_delete while the table still existed).
        for trig in (
            "photos_fts_insert", "photos_fts_update",
            "photos_fts_archive", "photos_fts_delete",
        ):
            with contextlib.suppress(sqlite3.OperationalError):
                dst_conn.execute(f"DROP TRIGGER IF EXISTS {trig}")
        with contextlib.suppress(sqlite3.OperationalError):
            dst_conn.execute("DROP TABLE IF EXISTS photos_fts")

        dst_conn.commit()
        dst_conn.close()

        # VACUUM requires no active transaction; run with autocommit.
        vacuum_conn = sqlite3.connect(str(tmp_path), isolation_level=None)
        vacuum_conn.execute("PRAGMA journal_mode=DELETE")
        vacuum_conn.execute("VACUUM")
        vacuum_conn.close()

        db_bytes = tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)

    # Gzip + base64 the DB for transport inside the HTML.
    db_gz = gzip.compress(db_bytes, compresslevel=_DB_GZIP_LEVEL)
    db_b64 = base64.b64encode(db_gz).decode("ascii")

    # Inline sql-wasm.js verbatim and base64-inline the wasm.
    sqljs_js = _read_vendor("sql-wasm.js").decode("utf-8")
    wasm_b64 = base64.b64encode(_read_vendor("sql-wasm.wasm")).decode("ascii")

    # Defensive: neutralise any literal "</script>" in the sql.js body so
    # it cannot terminate the wrapping <script> element. Current vendored
    # build contains no such sequence but the cost of defensiveness is
    # one str.replace().
    sqljs_safe = sqljs_js.replace("</script>", "<\\/script>")

    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    html = (
        template
        .replace("{{TITLE}}", title)
        .replace("{{SQLJS_INLINE}}", sqljs_safe)
        .replace("{{WASM_BASE64}}", wasm_b64)
        .replace("{{DB_BASE64_GZ}}", db_b64)
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    return photo_count
