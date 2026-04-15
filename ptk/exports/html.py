"""Export ptk library as a single-file HTML photo browser."""

import base64
import contextlib
import sqlite3
import tempfile
from pathlib import Path

from ptk.core.config import get_config


def export_html(output_path: Path, title: str = "ptk Photo Library") -> int:
    """Export the library as a self-contained HTML file.

    Uses SQLite's backup API to create a consistent copy of the database
    (properly handling WAL mode), strips heavy data (embeddings, face blobs
    from legacy databases), base64-encodes it, and embeds it in an HTML
    template that uses sql.js to provide an interactive photo browser.

    Args:
        output_path: Where to write the HTML file.
        title: Title for the gallery page.

    Returns:
        Number of photos in the exported library.
    """
    config = get_config()
    db_path = config.database_path

    # Copy DB to temp file using SQLite backup API (handles WAL mode correctly)
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    src_conn = sqlite3.connect(str(db_path))
    dst_conn = sqlite3.connect(str(tmp_path))
    src_conn.backup(dst_conn)
    src_conn.close()

    try:
        # Get photo count before stripping
        photo_count = dst_conn.execute("SELECT count(*) FROM photos").fetchone()[0]

        # Strip heavy tables/columns (may not exist in newer databases)
        for stmt in [
            "DELETE FROM photo_embeddings",
            "UPDATE faces SET embedding = NULL, thumbnail_data = NULL",
        ]:
            with contextlib.suppress(sqlite3.OperationalError):
                dst_conn.execute(stmt)

        dst_conn.commit()
        dst_conn.close()

        # VACUUM requires no active transaction, so use a fresh autocommit connection
        vacuum_conn = sqlite3.connect(str(tmp_path), isolation_level=None)
        vacuum_conn.execute("VACUUM")
        vacuum_conn.close()

        # Read and encode
        db_bytes = tmp_path.read_bytes()
        db_base64 = base64.b64encode(db_bytes).decode("ascii")

    finally:
        tmp_path.unlink(missing_ok=True)

    # Load template and render
    template_path = Path(__file__).parent / "templates" / "gallery.html"
    template = template_path.read_text(encoding="utf-8")

    html = template.replace("{{DB_BASE64}}", db_base64).replace("{{TITLE}}", title)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    return photo_count
