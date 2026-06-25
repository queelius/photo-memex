"""Export photo-memex library as a single-file HTML photo browser.

Workspace C6 contract: one self-contained ``.html`` with

  - inlined sql-wasm.js (vendored; no CDN)
  - base64-encoded sql-wasm.wasm (loaded via ``initSqlJs({wasmBinary:...})``)
  - gzipped + base64-encoded SQLite database, decompressed in-browser via
    ``DecompressionStream('gzip')``

The shipped DB is deny-by-default (R2 security contract): the embedded
SQLite image is fully readable by anyone who downloads the bundle, so it
ships only what the gallery actually renders. Sensitive photo columns
(raw ``source_metadata``, precise GPS, filesystem ``original_path``,
``import_source`` provenance) are dropped, and the ``marginalia`` table is
dropped unless the caller passes ``include_notes=True``. Heavy blobs
(legacy embeddings, face thumbnail_data) are stripped too, to keep the
bundle small. SQLite WAL-sidecars are never written because the backup API
produces a consistent snapshot and VACUUM runs in autocommit mode.
"""

from __future__ import annotations

import base64
import contextlib
import gzip
import sqlite3
import tempfile
from html import escape as _html_escape
from pathlib import Path

from photo_memex.core.config import get_config


_VENDORED_DIR = Path(__file__).parent / "vendored"
_TEMPLATE_PATH = Path(__file__).parent / "templates" / "gallery.html"
# gzip level 6 is the sweet spot: near-maximum ratio, modest CPU.
_DB_GZIP_LEVEL = 6

# Deny-by-default: photo columns that must never ship in a published bundle.
# The embedded DB is fully readable, so anything sensitive the gallery does
# not strictly need is dropped. Precise GPS (latitude/longitude/altitude)
# would leak home/work locations; original_path leaks the author's
# filesystem; import_source leaks provenance; source_metadata embeds the
# full raw provider JSON. The gallery still renders: it shows location_name
# (kept) and simply omits the file-link / precise-coordinate fallback.
_SENSITIVE_PHOTO_COLUMNS = (
    "source_metadata",
    "latitude",
    "longitude",
    "altitude",
    "original_path",
    "import_source",
)

# Tables holding private free-form notes; dropped unless include_notes=True.
_NOTES_TABLES = ("marginalia",)


def _read_vendor(name: str) -> bytes:
    return (_VENDORED_DIR / name).read_bytes()


def _drop_sensitive_columns(conn: sqlite3.Connection, table: str, columns) -> None:
    """Drop the given columns from ``table`` (deny-by-default export).

    SQLite refuses to DROP COLUMN while an index references it, so any index
    touching a target column is dropped first. Indexes are discovered from
    the schema (not hardcoded) so this stays correct as the schema evolves.
    Columns absent from the table (older/newer DBs) are skipped.
    """
    present = {
        row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    targets = [c for c in columns if c in present]
    if not targets:
        return

    target_set = set(targets)
    # Drop every (non-autoindex) index that references a target column.
    index_rows = conn.execute(f"PRAGMA index_list({table})").fetchall()
    for idx_row in index_rows:
        idx_name = idx_row[1]
        if idx_name.startswith("sqlite_autoindex"):
            continue  # implicit PK/unique index, cannot be dropped directly
        idx_cols = {
            col_row[2]
            for col_row in conn.execute(f"PRAGMA index_info({idx_name})").fetchall()
        }
        if idx_cols & target_set:
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute(f"DROP INDEX IF EXISTS {idx_name}")

    for col in targets:
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute(f'ALTER TABLE {table} DROP COLUMN "{col}"')


def export_html(
    output_path: Path,
    title: str = "photo-memex Photo Library",
    include_notes: bool = False,
) -> int:
    """Export the library as a self-contained HTML file.

    The export is deny-by-default (R2): sensitive photo columns (raw
    source_metadata, precise GPS, filesystem original_path, import_source)
    are dropped from the embedded DB, and private marginalia is dropped
    unless ``include_notes`` is True.

    Args:
        output_path: Where to write the HTML file.
        title: Title for the gallery page.
        include_notes: If True, ship the marginalia (private notes) table in
            the embedded DB. Off by default so notes never leak into a
            published bundle unless explicitly requested.

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

        # Deny-by-default: physically drop sensitive photo columns so they
        # cannot be extracted from the embedded DB. location_name is kept so
        # the gallery still shows a human-readable place; precise coordinates
        # and filesystem/provenance fields are removed.
        _drop_sensitive_columns(dst_conn, "photos", _SENSITIVE_PHOTO_COLUMNS)

        # Drop private notes unless the caller explicitly opts in. The
        # gallery does not query marginalia, so dropping it is render-safe.
        if not include_notes:
            for notes_table in _NOTES_TABLES:
                with contextlib.suppress(sqlite3.OperationalError):
                    dst_conn.execute(f"DROP TABLE IF EXISTS {notes_table}")

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

    # Escape the caller-supplied title: it lands in <title> and <h1>, so an
    # unescaped value (e.g. from --title) could inject markup into the
    # published gallery. Treat any exported HTML as potentially public.
    safe_title = _html_escape(title)

    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    html = (
        template
        .replace("{{TITLE}}", safe_title)
        .replace("{{SQLJS_INLINE}}", sqljs_safe)
        .replace("{{WASM_BASE64}}", wasm_b64)
        .replace("{{DB_BASE64_GZ}}", db_b64)
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    return photo_count
