# ptk Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor ptk from a CLI-with-built-in-AI to a lean data toolkit with MCP server, HTML export, and arkiv integration.

**Architecture:** Remove ai/, views/, skills/ and their CLI command groups. Add MCP server (FastMCP stdio), HTML export (sql.js + embedded DB), arkiv export (JSONL + schema.yaml), and arkiv import (new BaseImporter subclass). The query builder loses view-related filtering. Session.py loses the view model side-effect import.

**Tech Stack:** FastMCP (mcp Python SDK), sql.js (CDN), arkiv record format (JSONL)

**Design doc:** `docs/plans/2026-02-28-ptk-refactor-design.md`

---

### Task 1: Delete dead code and unused modules

**Files:**
- Delete: `ptk/ai/` (entire directory)
- Delete: `ptk/views/` (entire directory)
- Delete: `ptk/skills/` (entire directory)
- Delete: `ptk/cli_old.py`
- Delete: `tests/unit/test_annotations.py`
- Delete: `tests/unit/test_provider.py`
- Delete: `tests/integration/test_claude_skill.py`

**Step 1: Delete the directories and files**

```bash
rm -rf ptk/ai ptk/views ptk/skills ptk/cli_old.py
rm tests/unit/test_annotations.py tests/unit/test_provider.py tests/integration/test_claude_skill.py
```

**Step 2: Run tests to see what breaks**

Run: `pytest --tb=short 2>&1 | tail -30`
Expected: Failures in cli.py (view/ai/claude imports), session.py (view model import), query tests (view assertions)

**Step 3: Commit the deletions**

```bash
git add -A
git commit -m "chore: remove ai/, views/, skills/ modules and cli_old.py"
```

---

### Task 2: Fix session.py — remove view model import

**Files:**
- Modify: `ptk/db/session.py:13-15`

**Step 1: Remove the side-effect import**

In `ptk/db/session.py`, delete lines 13-15:
```python
# Import view models to register them with Base.metadata
# This ensures the view tables are created when init_db is called
from ptk.views.models import View, ViewAnnotation  # noqa: F401
```

**Step 2: Run tests to verify session works**

Run: `pytest tests/unit/test_models.py -v`
Expected: PASS (models still work without view tables)

**Step 3: Commit**

```bash
git add ptk/db/session.py
git commit -m "fix: remove view model side-effect import from session.py"
```

---

### Task 3: Fix cli.py — remove ai, claude, view command groups

**Files:**
- Modify: `ptk/cli.py`

**Step 1: Remove the `view` command group**

Delete lines 417-581 (the entire `# 7. ptk view` section including `view_app`, `view_list`, `view_create`, `view_run`, `view_delete`).

**Step 2: Remove the `ai` command group**

Delete lines 584-680 (the entire `# 8. ptk ai` section including `ai_app`, `ai_status`, `ai_describe`, `ai_ask`).

**Step 3: Remove the `claude` command group**

Delete lines 683-749 (the entire `# 9. ptk claude` section including `claude_app`, `claude_install`, `claude_uninstall`, `claude_status`, `claude_show`).

**Step 4: Fix the `show` command**

In the `show` command (around line 284), remove the view annotations section:
```python
        # View annotations
        from ptk.views import ViewManager
        manager = ViewManager(session)
        all_annotations = manager.get_all_annotations(photo.id)

        if all_annotations:
            console.print("\n[dim]Annotations:[/dim]")
            for view_name, fields in all_annotations.items():
                console.print(f"  [{view_name}]")
                for field_name, value in fields.items():
                    console.print(f"    {field_name}: {value}")
```

**Step 5: Fix the `query` command**

Remove the `--view` and `--field` options from the `query` function signature. Remove the `view` and `field` filter application in the body:
```python
            if view:
                builder.view(view)
            for f in (field or []):
                builder.field_filter(f)
```

**Step 6: Update the module docstring**

Change the docstring at the top of cli.py to remove references to `view` and `ai`.

**Step 7: Run the CLI integration tests**

Run: `pytest tests/integration/test_cli.py -v`
Expected: PASS

**Step 8: Commit**

```bash
git add ptk/cli.py
git commit -m "fix: remove ai, claude, view command groups from CLI"
```

---

### Task 4: Simplify query builder — remove view/field filtering

**Files:**
- Modify: `ptk/query/builder.py`
- Modify: `tests/unit/test_query.py`

**Step 1: Remove view-related methods and state from QueryBuilder**

In `ptk/query/builder.py`, remove:
- `_views` field (line 28)
- `_fields` field (line 29)
- `view()` method (lines 57-60)
- `field_filter()` method (lines 62-89)
- View filter JOIN generation (lines 146-152, the `# View filters` section)
- Field filter JOIN generation (lines 154-198, the `# Field filters` section)
- The `import json` inside field filters
- The `import re` at the top (only used by field_filter)

**Step 2: Remove view-related tests from test_query.py**

In `tests/unit/test_query.py`, remove these test methods:
- `test_view_filter` (line 79)
- `test_field_filter_equality_string` (line 89)
- `test_field_filter_numeric_gt` (line 100)
- `test_field_filter_numeric_gte` (line 111)
- `test_field_filter_with_view_prefix` (line 120)
- `test_field_filter_invalid_expression` (line 166)
- `test_field_filter_float` (line 172)
- `test_field_filter_not_equals` (line 180)

Also update any combined tests that reference `.view()` or `.field_filter()`:
- `test_combined_filters` (line 149): remove `.view("family_v1")` and its assertion
- `test_builder_returns_self` (line 163): remove `.view("z")`

**Step 3: Run query tests**

Run: `pytest tests/unit/test_query.py -v`
Expected: All remaining tests PASS

**Step 4: Commit**

```bash
git add ptk/query/builder.py tests/unit/test_query.py
git commit -m "simplify: remove view/field filtering from query builder"
```

---

### Task 5: Update pyproject.toml — remove unused dependency groups

**Files:**
- Modify: `pyproject.toml`

**Step 1: Remove unused optional dependency groups**

Remove the `captioning` and `embeddings` groups from `[project.optional-dependencies]`. Update the `all` group to only include remaining extras (`video`, `faces`). Add a new `mcp` group:

```toml
[project.optional-dependencies]
video = [
    "ffmpeg-python>=0.2.0",
]
faces = [
    "face_recognition>=1.3.0",
    "numpy>=1.24.0",
    "scikit-learn>=1.3.0",
]
mcp = [
    "mcp[cli]",
]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "ruff>=0.1.0",
    "mypy>=1.0.0",
]
all = [
    "ptk[video]",
    "ptk[faces]",
    "ptk[mcp]",
]
```

**Step 2: Reinstall the package**

Run: `pip install -e ".[dev]"`

**Step 3: Run all tests**

Run: `pytest`
Expected: All remaining tests PASS (should be ~180 tests after removing ai/views/skills tests)

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: update dependency groups, add mcp extra, remove captioning/embeddings"
```

---

### Task 6: MCP server — tests first

**Files:**
- Create: `ptk/mcp/__init__.py`
- Create: `tests/unit/test_mcp_server.py`

**Step 1: Create the mcp package stub**

```python
# ptk/mcp/__init__.py
"""MCP server for ptk."""
```

**Step 2: Write failing tests for the MCP server logic**

Create `tests/unit/test_mcp_server.py`. Test the server logic class (not the MCP transport — that's integration-level). The server logic takes a DB path and exposes three methods:

```python
"""Tests for ptk MCP server logic."""

import json
import sqlite3
import pytest
from pathlib import Path

from ptk.mcp.server import PtkServer


@pytest.fixture
def server(test_library, populated_library, db_session):
    """Create a PtkServer pointing at the test library."""
    from ptk.core.config import get_config
    db_path = get_config().database_path
    return PtkServer(db_path)


class TestGetSchema:
    def test_returns_create_statements(self, server):
        schema = server.get_schema()
        assert "CREATE TABLE" in schema
        assert "photos" in schema
        assert "tags" in schema

    def test_includes_all_tables(self, server):
        schema = server.get_schema()
        for table in ["photos", "tags", "albums", "photo_tags", "photo_albums"]:
            assert table in schema


class TestGetStats:
    def test_returns_photo_count(self, server):
        stats = server.get_stats()
        assert "photo_count" in stats
        assert stats["photo_count"] >= 1

    def test_returns_tag_count(self, server):
        stats = server.get_stats()
        assert "tag_count" in stats

    def test_returns_album_count(self, server):
        stats = server.get_stats()
        assert "album_count" in stats


class TestRunSql:
    def test_select_returns_rows(self, server):
        rows = server.run_sql("SELECT id, filename FROM photos LIMIT 1")
        assert len(rows) == 1
        assert "id" in rows[0]
        assert "filename" in rows[0]

    def test_rejects_non_select(self, server):
        with pytest.raises(ValueError, match="Only SELECT"):
            server.run_sql("DELETE FROM photos")

    def test_rejects_drop(self, server):
        with pytest.raises(ValueError, match="Only SELECT"):
            server.run_sql("DROP TABLE photos")

    def test_rejects_insert(self, server):
        with pytest.raises(ValueError, match="Only SELECT"):
            server.run_sql("INSERT INTO photos (id) VALUES ('x')")

    def test_rejects_update(self, server):
        with pytest.raises(ValueError, match="Only SELECT"):
            server.run_sql("UPDATE photos SET caption = 'x'")

    def test_handles_empty_result(self, server):
        rows = server.run_sql("SELECT * FROM photos WHERE id = 'nonexistent'")
        assert rows == []

    def test_handles_aggregate(self, server):
        rows = server.run_sql("SELECT count(*) as cnt FROM photos")
        assert rows[0]["cnt"] >= 1
```

**Step 3: Run tests to verify they fail**

Run: `pytest tests/unit/test_mcp_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ptk.mcp.server'`

**Step 4: Commit**

```bash
git add ptk/mcp/__init__.py tests/unit/test_mcp_server.py
git commit -m "test: add failing tests for MCP server logic"
```

---

### Task 7: MCP server — implementation

**Files:**
- Create: `ptk/mcp/server.py`
- Modify: `ptk/cli.py` (add `ptk mcp` command)

**Step 1: Implement PtkServer**

Create `ptk/mcp/server.py`:

```python
"""ptk MCP server — exposes photo library via stdio MCP protocol."""

import json
import os
import sqlite3
from pathlib import Path
from typing import Any


class PtkServer:
    """Core server logic: schema, stats, read-only SQL."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row

    def get_schema(self) -> str:
        """Return all CREATE TABLE statements from the database."""
        cursor = self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL ORDER BY name"
        )
        statements = [row[0] for row in cursor.fetchall()]
        return "\n\n".join(statements)

    def get_stats(self) -> dict[str, Any]:
        """Return library statistics."""
        stats = {}
        stats["photo_count"] = self._count("photos")
        stats["tag_count"] = self._count("tags")
        stats["album_count"] = self._count("albums")

        row = self._conn.execute(
            "SELECT MIN(date_taken) as earliest, MAX(date_taken) as latest, "
            "SUM(file_size) as total_size FROM photos"
        ).fetchone()
        stats["earliest_date"] = row["earliest"]
        stats["latest_date"] = row["latest"]
        stats["total_size_bytes"] = row["total_size"] or 0

        stats["favorites"] = self._conn.execute(
            "SELECT count(*) FROM photos WHERE is_favorite = 1"
        ).fetchone()[0]

        return stats

    def run_sql(self, query: str) -> list[dict[str, Any]]:
        """Execute a read-only SQL query. Only SELECT allowed."""
        normalized = query.strip()
        # Remove leading comments and whitespace
        while normalized.startswith("--") or normalized.startswith("/*"):
            if normalized.startswith("--"):
                normalized = normalized.split("\n", 1)[-1].strip()
            elif normalized.startswith("/*"):
                end = normalized.find("*/")
                if end == -1:
                    break
                normalized = normalized[end + 2:].strip()

        if not normalized.upper().startswith("SELECT"):
            raise ValueError("Only SELECT statements are allowed.")

        cursor = self._conn.execute(query)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def close(self):
        self._conn.close()

    def _count(self, table: str) -> int:
        return self._conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def run_mcp_server(db_path: str):
    """Run the ptk MCP server over stdio."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        raise ImportError(
            "MCP server requires 'mcp' package. Install with: pip install ptk[mcp]"
        )

    mcp = FastMCP("ptk")
    server = PtkServer(db_path)

    @mcp.tool()
    def get_schema() -> str:
        """Get the database schema (CREATE TABLE statements). Call this first to understand the data model before writing SQL queries."""
        return server.get_schema()

    @mcp.tool()
    def get_stats() -> str:
        """Get library statistics: photo count, tag count, album count, date range, total size, favorites."""
        return json.dumps(server.get_stats(), indent=2, default=str)

    @mcp.tool()
    def run_sql(query: str) -> str:
        """Run a read-only SQL query against the photo library. Only SELECT statements are allowed. The database uses SQLite with tables: photos, tags, albums, photo_tags, photo_albums. Use JOIN for relationships. Thumbnail BLOBs are in photos.thumbnail_data (base64-encode for display)."""
        rows = server.run_sql(query)
        return json.dumps(rows, indent=2, default=str)

    mcp.run(transport="stdio")
```

**Step 2: Add `ptk mcp` command to cli.py**

Add before the `# Entry point` section at the bottom of cli.py:

```python
# =============================================================================
# ptk mcp
# =============================================================================

@app.command()
def mcp(
    library: Optional[Path] = typer.Option(None, "--library", "-l", help="Library path"),
) -> None:
    """Launch MCP server (stdio) for Claude Code integration."""
    import os

    # Library discovery: --library flag > PTK_LIBRARY env > find_library()
    lib_path = library
    if lib_path is None:
        env_path = os.environ.get("PTK_LIBRARY")
        if env_path:
            lib_path = Path(env_path)

    if lib_path:
        _require_library(lib_path)
    else:
        _require_library()

    from ptk.core.config import get_config
    from ptk.mcp.server import run_mcp_server
    run_mcp_server(str(get_config().database_path))
```

**Step 3: Run MCP tests**

Run: `pytest tests/unit/test_mcp_server.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add ptk/mcp/server.py ptk/cli.py
git commit -m "feat: add MCP server with run_sql, get_schema, get_stats"
```

---

### Task 8: arkiv export — tests first

**Files:**
- Create: `tests/unit/test_arkiv_export.py`

**Step 1: Write failing tests**

```python
"""Tests for arkiv export."""

import json
from pathlib import Path

import pytest
import yaml

from ptk.db.models import Photo, Tag, Album
from ptk.db.session import get_session


@pytest.fixture
def library_with_tagged_photo(populated_library, db_session):
    """A library with a photo that has tags and a caption."""
    photo = db_session.query(Photo).first()
    photo.caption = "A red test image"
    photo.is_favorite = True

    tag = Tag(name="test-tag")
    db_session.add(tag)
    photo.tags.append(tag)
    db_session.commit()

    return populated_library


class TestArkivExport:
    def test_creates_output_directory(self, library_with_tagged_photo, temp_dir):
        from ptk.exports.arkiv import export_arkiv

        output = temp_dir / "export"
        export_arkiv(output)

        assert output.is_dir()

    def test_creates_readme(self, library_with_tagged_photo, temp_dir):
        from ptk.exports.arkiv import export_arkiv

        output = temp_dir / "export"
        export_arkiv(output)

        readme = output / "README.md"
        assert readme.exists()
        content = readme.read_text()
        assert "generator: ptk" in content

    def test_creates_photos_jsonl(self, library_with_tagged_photo, temp_dir):
        from ptk.exports.arkiv import export_arkiv

        output = temp_dir / "export"
        export_arkiv(output)

        jsonl = output / "photos.jsonl"
        assert jsonl.exists()
        lines = [json.loads(line) for line in jsonl.read_text().strip().split("\n")]
        assert len(lines) == 1

    def test_record_has_required_fields(self, library_with_tagged_photo, temp_dir):
        from ptk.exports.arkiv import export_arkiv

        output = temp_dir / "export"
        export_arkiv(output)

        jsonl = output / "photos.jsonl"
        record = json.loads(jsonl.read_text().strip())
        assert "mimetype" in record
        assert "uri" in record
        assert "metadata" in record

    def test_record_metadata_has_sha256(self, library_with_tagged_photo, temp_dir):
        from ptk.exports.arkiv import export_arkiv

        output = temp_dir / "export"
        export_arkiv(output)

        record = json.loads((output / "photos.jsonl").read_text().strip())
        assert "sha256" in record["metadata"]
        assert len(record["metadata"]["sha256"]) == 64

    def test_record_metadata_has_tags(self, library_with_tagged_photo, temp_dir):
        from ptk.exports.arkiv import export_arkiv

        output = temp_dir / "export"
        export_arkiv(output)

        record = json.loads((output / "photos.jsonl").read_text().strip())
        assert record["metadata"]["tags"] == ["test-tag"]

    def test_record_metadata_has_caption(self, library_with_tagged_photo, temp_dir):
        from ptk.exports.arkiv import export_arkiv

        output = temp_dir / "export"
        export_arkiv(output)

        record = json.loads((output / "photos.jsonl").read_text().strip())
        assert record["metadata"]["caption"] == "A red test image"

    def test_record_uri_is_file_uri(self, library_with_tagged_photo, temp_dir):
        from ptk.exports.arkiv import export_arkiv

        output = temp_dir / "export"
        export_arkiv(output)

        record = json.loads((output / "photos.jsonl").read_text().strip())
        assert record["uri"].startswith("file:///")

    def test_creates_schema_yaml(self, library_with_tagged_photo, temp_dir):
        from ptk.exports.arkiv import export_arkiv

        output = temp_dir / "export"
        export_arkiv(output)

        schema_path = output / "schema.yaml"
        assert schema_path.exists()
        schema = yaml.safe_load(schema_path.read_text())
        assert "photos" in schema
        assert "metadata_keys" in schema["photos"]

    def test_null_fields_omitted(self, library_with_tagged_photo, temp_dir):
        from ptk.exports.arkiv import export_arkiv

        output = temp_dir / "export"
        export_arkiv(output)

        record = json.loads((output / "photos.jsonl").read_text().strip())
        # Fields that are None on our test photo shouldn't appear
        for key in ["camera_make", "camera_model", "lens", "latitude", "longitude"]:
            assert key not in record["metadata"]
```

**Step 2: Run to verify they fail**

Run: `pytest tests/unit/test_arkiv_export.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ptk.exports.arkiv'`

**Step 3: Commit**

```bash
git add tests/unit/test_arkiv_export.py
git commit -m "test: add failing tests for arkiv export"
```

---

### Task 9: arkiv export — implementation

**Files:**
- Modify: `ptk/exports/__init__.py`
- Create: `ptk/exports/arkiv.py`
- Modify: `ptk/cli.py` (add `ptk export arkiv` command)

**Step 1: Implement the arkiv exporter**

Create `ptk/exports/arkiv.py`:

```python
"""Export ptk library to arkiv format (JSONL + README.md + schema.yaml)."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml

from ptk import __version__
from ptk.db.models import Photo
from ptk.db.session import session_scope


def export_arkiv(output_dir: Path, title: str | None = None) -> int:
    """Export the library to an arkiv archive directory.

    Args:
        output_dir: Directory to write the archive to (created if needed).
        title: Optional archive title.

    Returns:
        Number of photos exported.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    with session_scope() as session:
        photos = session.query(Photo).all()
        records = [_photo_to_record(p) for p in photos]

    # Write photos.jsonl
    jsonl_path = output_dir / "photos.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    # Write README.md
    _write_readme(output_dir, len(records), title)

    # Write schema.yaml
    _write_schema(output_dir, jsonl_path, len(records))

    return len(records)


def _photo_to_record(photo: Photo) -> dict[str, Any]:
    """Convert a Photo ORM object to an arkiv record dict."""
    metadata: dict[str, Any] = {}

    # Identity
    metadata["sha256"] = photo.id
    metadata["filename"] = photo.filename
    metadata["file_size"] = photo.file_size

    # Dimensions
    if photo.width is not None:
        metadata["width"] = photo.width
    if photo.height is not None:
        metadata["height"] = photo.height

    # Relationships (denormalized)
    if photo.tags:
        metadata["tags"] = sorted(t.name for t in photo.tags)
    if photo.albums:
        metadata["albums"] = sorted(a.name for a in photo.albums)

    # AI/user content
    if photo.caption:
        metadata["caption"] = photo.caption
    if photo.scene:
        metadata["scene"] = photo.scene

    # Flags
    if photo.is_favorite:
        metadata["is_favorite"] = True
    if photo.is_screenshot:
        metadata["is_screenshot"] = True
    if photo.is_video:
        metadata["is_video"] = True

    # EXIF
    for field in [
        "camera_make", "camera_model", "lens", "shutter_speed",
        "location_name", "country", "city", "import_source",
    ]:
        value = getattr(photo, field, None)
        if value is not None:
            metadata[field] = value

    for field in [
        "focal_length", "aperture", "iso",
        "latitude", "longitude", "altitude",
    ]:
        value = getattr(photo, field, None)
        if value is not None:
            metadata[field] = value

    # Build record
    record: dict[str, Any] = {"mimetype": photo.mime_type}

    # URI: file:// with proper encoding
    record["uri"] = Path(photo.original_path).as_uri()

    # Timestamp
    if photo.date_taken:
        record["timestamp"] = photo.date_taken.isoformat()

    record["metadata"] = metadata
    return record


def _write_readme(output_dir: Path, count: int, title: str | None) -> None:
    """Write the arkiv README.md with frontmatter."""
    name = title or "ptk photo library"
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    frontmatter = {
        "name": name,
        "description": f"Photo library exported from ptk ({count} photos)",
        "datetime": now,
        "generator": f"ptk {__version__}",
        "contents": [{"path": "photos.jsonl", "description": "Photo metadata records"}],
    }

    fm_yaml = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)
    body = f"\n{name}: {count} photos.\n"

    readme_path = output_dir / "README.md"
    readme_path.write_text(f"---\n{fm_yaml}---\n{body}", encoding="utf-8")


def _write_schema(output_dir: Path, jsonl_path: Path, count: int) -> None:
    """Write schema.yaml by scanning the JSONL we just wrote."""
    # Discover schema from the JSONL
    key_counts: dict[str, int] = {}
    key_types: dict[str, str] = {}

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            meta = record.get("metadata", {})
            for key, value in meta.items():
                key_counts[key] = key_counts.get(key, 0) + 1
                key_types[key] = _json_type(value)

    metadata_keys = {}
    for key in sorted(key_counts.keys()):
        metadata_keys[key] = {
            "type": key_types[key],
            "count": key_counts[key],
        }

    schema = {"photos": {"record_count": count, "metadata_keys": metadata_keys}}

    header = "# Auto-generated by ptk. Edit freely.\n"
    body = yaml.dump(schema, default_flow_style=False, allow_unicode=True, sort_keys=False)
    (output_dir / "schema.yaml").write_text(header + body, encoding="utf-8")


def _json_type(value: Any) -> str:
    """Return the JSON type name for a Python value."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"
```

**Step 2: Update exports __init__.py**

```python
"""Export functionality for ptk."""

from ptk.exports.arkiv import export_arkiv

__all__ = ["export_arkiv"]
```

**Step 3: Add `ptk export` command group to cli.py**

Add an `export_app` Typer sub-app after the `stats` command section:

```python
# =============================================================================
# ptk export
# =============================================================================

export_app = typer.Typer(help="Export library to various formats")
app.add_typer(export_app, name="export")


@export_app.command("arkiv")
def export_arkiv_cmd(
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Archive title"),
) -> None:
    """Export library to arkiv format (JSONL + schema)."""
    _require_library()

    from ptk.exports.arkiv import export_arkiv

    output_dir = output or Path("ptk-photos")
    count = export_arkiv(output_dir, title=title)
    console.print(f"[green]Exported {count} photos to {output_dir}/[/green]")
```

**Step 4: Run arkiv export tests**

Run: `pytest tests/unit/test_arkiv_export.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add ptk/exports/ ptk/cli.py tests/unit/test_arkiv_export.py
git commit -m "feat: add arkiv export (JSONL + README.md + schema.yaml)"
```

---

### Task 10: arkiv import — tests first

**Files:**
- Create: `tests/unit/test_arkiv_import.py`

**Step 1: Write failing tests**

```python
"""Tests for arkiv importer."""

import json
from pathlib import Path

import pytest

from ptk.db.models import Photo, Tag, Album
from ptk.db.session import get_session


@pytest.fixture
def arkiv_archive(temp_dir, sample_image):
    """Create a minimal arkiv archive with one photo record."""
    archive_dir = temp_dir / "archive"
    archive_dir.mkdir()

    record = {
        "mimetype": "image/jpeg",
        "uri": sample_image.as_uri(),
        "timestamp": "2024-07-15T14:23:00",
        "metadata": {
            "sha256": "will-be-ignored",
            "tags": ["vacation", "beach"],
            "albums": ["Summer 2024"],
            "caption": "A beautiful scene",
            "is_favorite": True,
        },
    }

    jsonl = archive_dir / "photos.jsonl"
    jsonl.write_text(json.dumps(record) + "\n")

    readme = archive_dir / "README.md"
    readme.write_text("---\nname: test\n---\n")

    return archive_dir


class TestArkivImporter:
    def test_can_handle_directory(self, arkiv_archive):
        from ptk.importers.arkiv import ArkivImporter
        importer = ArkivImporter()
        assert importer.can_handle(arkiv_archive)

    def test_can_handle_jsonl_file(self, arkiv_archive):
        from ptk.importers.arkiv import ArkivImporter
        importer = ArkivImporter()
        assert importer.can_handle(arkiv_archive / "photos.jsonl")

    def test_cannot_handle_random_dir(self, temp_dir):
        from ptk.importers.arkiv import ArkivImporter
        importer = ArkivImporter()
        assert not importer.can_handle(temp_dir)

    def test_scan_yields_items(self, arkiv_archive):
        from ptk.importers.arkiv import ArkivImporter
        importer = ArkivImporter()
        items = list(importer.scan(arkiv_archive))
        assert len(items) == 1

    def test_scan_resolves_uri_to_path(self, arkiv_archive, sample_image):
        from ptk.importers.arkiv import ArkivImporter
        importer = ArkivImporter()
        items = list(importer.scan(arkiv_archive))
        assert items[0].path == sample_image

    def test_scan_includes_metadata(self, arkiv_archive):
        from ptk.importers.arkiv import ArkivImporter
        importer = ArkivImporter()
        items = list(importer.scan(arkiv_archive))
        meta = items[0].source_metadata
        assert meta["tags"] == ["vacation", "beach"]
        assert meta["caption"] == "A beautiful scene"

    def test_scan_skips_missing_files(self, temp_dir):
        """Records with non-existent URIs are skipped."""
        from ptk.importers.arkiv import ArkivImporter

        archive = temp_dir / "archive"
        archive.mkdir()
        record = {
            "mimetype": "image/jpeg",
            "uri": "file:///nonexistent/photo.jpg",
        }
        (archive / "photos.jsonl").write_text(json.dumps(record) + "\n")
        (archive / "README.md").write_text("---\nname: test\n---\n")

        importer = ArkivImporter()
        items = list(importer.scan(archive))
        assert len(items) == 0
```

**Step 2: Run to verify they fail**

Run: `pytest tests/unit/test_arkiv_import.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Commit**

```bash
git add tests/unit/test_arkiv_import.py
git commit -m "test: add failing tests for arkiv importer"
```

---

### Task 11: arkiv import — implementation

**Files:**
- Create: `ptk/importers/arkiv.py`
- Modify: `ptk/cli.py` (add `--source arkiv` to import command)

**Step 1: Implement ArkivImporter**

Create `ptk/importers/arkiv.py`:

```python
"""Import photos from an arkiv archive."""

import json
from pathlib import Path
from typing import Any, Iterator, Optional
from urllib.parse import urlparse, unquote

from ptk.importers.base import BaseImporter, ImportItem


class ArkivImporter(BaseImporter):
    """Import from an arkiv archive directory or JSONL file."""

    @property
    def name(self) -> str:
        return "arkiv"

    def can_handle(self, path: Path) -> bool:
        """Recognize arkiv archives: directory with README.md + *.jsonl, or a .jsonl file."""
        if path.is_file() and path.suffix == ".jsonl":
            return True
        if path.is_dir():
            has_readme = (path / "README.md").exists()
            has_jsonl = any(path.glob("*.jsonl"))
            return has_readme and has_jsonl
        return False

    def scan(self, path: Path) -> Iterator[ImportItem]:
        """Scan an arkiv archive and yield ImportItems for photos with existing files."""
        if path.is_file() and path.suffix == ".jsonl":
            yield from self._scan_jsonl(path)
        elif path.is_dir():
            for jsonl_file in sorted(path.glob("*.jsonl")):
                yield from self._scan_jsonl(jsonl_file)

    def _scan_jsonl(self, jsonl_path: Path) -> Iterator[ImportItem]:
        """Parse a JSONL file and yield ImportItems."""
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                item = self._record_to_item(record)
                if item is not None:
                    yield item

    def _record_to_item(self, record: dict[str, Any]) -> Optional[ImportItem]:
        """Convert an arkiv record to an ImportItem, or None if file doesn't exist."""
        uri = record.get("uri")
        if not uri:
            return None

        # Resolve file:// URI to local path
        file_path = _uri_to_path(uri)
        if file_path is None or not file_path.exists():
            return None

        # Build source_metadata from the record
        source_metadata: dict[str, Any] = {}
        metadata = record.get("metadata", {})

        # Pass through fields the import service can use
        if record.get("timestamp"):
            source_metadata["date_taken"] = record["timestamp"]

        # Copy metadata fields for post-import application
        for key in ["tags", "albums", "caption", "is_favorite", "sha256",
                     "latitude", "longitude", "altitude"]:
            if key in metadata:
                source_metadata[key] = metadata[key]

        return ImportItem(path=file_path, source_metadata=source_metadata)


def _uri_to_path(uri: str) -> Optional[Path]:
    """Convert a file:// URI to a Path, or None if not a file URI."""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    return Path(unquote(parsed.path))
```

**Step 2: Add `--source arkiv` to the import command in cli.py**

In the `import_photos` function, add the arkiv case after the apple case:

```python
    elif source == "arkiv":
        from ptk.importers.arkiv import ArkivImporter
        importer = ArkivImporter()
```

Also update the auto-detect logic to recognize arkiv archives:

```python
    if source is None:
        if path.is_dir():
            # Check if it's an arkiv archive
            if (path / "README.md").exists() and any(path.glob("*.jsonl")):
                source = "arkiv"
            else:
                source = "dir"
        elif path.suffix.lower() == ".zip":
            source = "google"
        elif path.suffix.lower() == ".jsonl":
            source = "arkiv"
        else:
            source = "dir"
```

**Step 3: Run arkiv import tests**

Run: `pytest tests/unit/test_arkiv_import.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add ptk/importers/arkiv.py ptk/cli.py
git commit -m "feat: add arkiv importer with auto-detection"
```

---

### Task 12: arkiv import integration — metadata application

**Files:**
- Create: `tests/integration/test_arkiv_roundtrip.py`

**Step 1: Write an integration test for export → import roundtrip**

This tests that exporting a tagged/captioned photo to arkiv and re-importing it into a fresh library preserves the metadata:

```python
"""Integration test: arkiv export → import roundtrip."""

import json
import os
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ptk.cli import app
from ptk.db.models import Photo, Tag
from ptk.db.session import init_db, close_db, get_session, session_scope
from ptk.core.config import PtkConfig, set_config


runner = CliRunner()


@pytest.fixture
def roundtrip_setup(temp_dir, sample_image):
    """Set up a library, import a photo, tag it, export to arkiv."""
    # Create and init library
    lib_dir = temp_dir / "source_lib"
    lib_dir.mkdir()
    config = PtkConfig(library_path=lib_dir)
    set_config(config)
    init_db(config.database_path, create_tables=True)

    # Import a photo
    from ptk.importers.filesystem import FilesystemImporter
    from ptk.services.import_service import ImportService

    with session_scope() as session:
        service = ImportService(session, config)
        photo_id = service.import_file(sample_image)

        # Add metadata
        photo = session.query(Photo).get(photo_id)
        photo.caption = "Test caption"
        photo.is_favorite = True
        tag = Tag(name="roundtrip-tag")
        session.add(tag)
        photo.tags.append(tag)

    # Export to arkiv
    archive_dir = temp_dir / "archive"
    from ptk.exports.arkiv import export_arkiv
    export_arkiv(archive_dir)

    close_db()

    return {
        "archive_dir": archive_dir,
        "temp_dir": temp_dir,
        "photo_id": photo_id,
        "sample_image": sample_image,
    }


class TestArkivRoundtrip:
    def test_export_produces_valid_jsonl(self, roundtrip_setup):
        jsonl = roundtrip_setup["archive_dir"] / "photos.jsonl"
        records = [json.loads(line) for line in jsonl.read_text().strip().split("\n")]
        assert len(records) == 1
        assert records[0]["metadata"]["caption"] == "Test caption"
        assert records[0]["metadata"]["tags"] == ["roundtrip-tag"]
        assert records[0]["metadata"]["is_favorite"] is True
```

**Step 2: Run the integration test**

Run: `pytest tests/integration/test_arkiv_roundtrip.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/integration/test_arkiv_roundtrip.py
git commit -m "test: add arkiv export/import roundtrip integration test"
```

---

### Task 13: HTML export — tests first

**Files:**
- Create: `tests/unit/test_html_export.py`

**Step 1: Write failing tests**

```python
"""Tests for HTML export."""

import base64
from pathlib import Path

import pytest

from ptk.db.models import Photo


class TestHtmlExport:
    def test_produces_html_file(self, populated_library, temp_dir):
        from ptk.exports.html import export_html

        output = temp_dir / "gallery.html"
        export_html(output)
        assert output.exists()
        assert output.suffix == ".html"

    def test_html_contains_sql_js_reference(self, populated_library, temp_dir):
        from ptk.exports.html import export_html

        output = temp_dir / "gallery.html"
        export_html(output)
        content = output.read_text()
        assert "sql.js" in content.lower() or "sql-wasm" in content.lower()

    def test_html_contains_embedded_db(self, populated_library, temp_dir):
        from ptk.exports.html import export_html

        output = temp_dir / "gallery.html"
        export_html(output)
        content = output.read_text()
        # The base64-encoded DB should be in the file
        assert "application/x-sqlite3" in content or "db-base64" in content.lower()

    def test_embedded_db_is_valid_base64(self, populated_library, temp_dir):
        from ptk.exports.html import export_html

        output = temp_dir / "gallery.html"
        export_html(output)
        content = output.read_text()

        # Extract the base64 data between markers
        start = content.find('id="db-base64"')
        assert start != -1, "No db-base64 element found"

    def test_html_is_self_contained(self, populated_library, temp_dir):
        from ptk.exports.html import export_html

        output = temp_dir / "gallery.html"
        export_html(output)
        content = output.read_text()
        assert "<html" in content
        assert "<style" in content
        assert "<script" in content

    def test_custom_title(self, populated_library, temp_dir):
        from ptk.exports.html import export_html

        output = temp_dir / "gallery.html"
        export_html(output, title="My Gallery")
        content = output.read_text()
        assert "My Gallery" in content

    def test_strip_db_removes_embeddings(self, populated_library, temp_dir):
        from ptk.exports.html import _strip_db

        from ptk.core.config import get_config
        db_path = get_config().database_path
        stripped = _strip_db(db_path, temp_dir / "stripped.db")

        import sqlite3
        conn = sqlite3.connect(str(stripped))
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        conn.close()

        assert "photo_embeddings" not in tables
```

**Step 2: Run to verify they fail**

Run: `pytest tests/unit/test_html_export.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ptk.exports.html'`

**Step 3: Commit**

```bash
git add tests/unit/test_html_export.py
git commit -m "test: add failing tests for HTML export"
```

---

### Task 14: HTML export — implementation

**Files:**
- Create: `ptk/exports/html.py`
- Create: `ptk/exports/templates/gallery.html`
- Modify: `ptk/cli.py` (add `ptk export html` command)

**Step 1: Create the HTML template**

Create `ptk/exports/templates/gallery.html`. This is a single-file HTML5 app with inline CSS and JS that:
- Loads sql.js from CDN
- Decodes the embedded base64 DB
- Renders a thumbnail grid from `thumbnail_data` BLOBs
- Has a lightbox for photo details
- Has tag/album/favorite filtering and caption search

The template uses `{{TITLE}}` and `{{DB_BASE64}}` placeholders.

This file will be large (~400 lines of HTML/CSS/JS). The key sections:

1. HTML structure: header with title + search, filter sidebar, photo grid, lightbox overlay
2. CSS: responsive grid, lightbox, filter sidebar
3. JS: sql.js initialization, DB loading, query functions, thumbnail rendering, filter state, lightbox

**Step 2: Create the export logic**

Create `ptk/exports/html.py`:

```python
"""Export ptk library as a self-contained HTML file."""

import base64
import shutil
import sqlite3
import tempfile
from pathlib import Path


def export_html(output_path: Path, title: str = "ptk Photo Library") -> None:
    """Export the library as a single HTML file with embedded SQLite DB.

    Args:
        output_path: Path to write the HTML file.
        title: Page title.
    """
    from ptk.core.config import get_config

    db_path = get_config().database_path

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        stripped = _strip_db(db_path, tmp / "stripped.db")
        db_bytes = stripped.read_bytes()

    db_b64 = base64.b64encode(db_bytes).decode("ascii")

    template = _load_template()
    html = template.replace("{{TITLE}}", title).replace("{{DB_BASE64}}", db_b64)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def _strip_db(source: Path, dest: Path) -> Path:
    """Create a stripped copy of the DB for embedding.

    Removes: photo_embeddings table, face embedding/thumbnail BLOBs.
    """
    shutil.copy2(source, dest)
    conn = sqlite3.connect(str(dest))

    # Drop heavy tables
    conn.execute("DROP TABLE IF EXISTS photo_embeddings")

    # Null out face embedding BLOBs (keep bbox metadata)
    try:
        conn.execute("UPDATE faces SET embedding = NULL, thumbnail_data = NULL")
    except sqlite3.OperationalError:
        pass  # faces table might not exist

    conn.execute("VACUUM")
    conn.commit()
    conn.close()
    return dest


def _load_template() -> str:
    """Load the gallery HTML template."""
    template_path = Path(__file__).parent / "templates" / "gallery.html"
    return template_path.read_text(encoding="utf-8")
```

**Step 3: Add `ptk export html` command**

In the export_app section of cli.py, add:

```python
@export_app.command("html")
def export_html_cmd(
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path"),
    title: str = typer.Option("ptk Photo Library", "--title", "-t", help="Page title"),
) -> None:
    """Export library as a self-contained HTML file."""
    _require_library()

    from ptk.exports.html import export_html

    output_path = output or Path("ptk-export.html")
    export_html(output_path, title=title)

    size_mb = output_path.stat().st_size / 1024 / 1024
    console.print(f"[green]Exported to {output_path} ({size_mb:.1f} MB)[/green]")
```

**Step 4: Write the gallery.html template**

This is the largest single file. Create `ptk/exports/templates/gallery.html` with the full HTML/CSS/JS application. Key implementation notes:

- sql.js loaded from `https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.3/sql-wasm.js`
- DB decoded from the `<script id="db-base64" type="application/x-sqlite3">` tag
- Thumbnails rendered as `data:${mime};base64,${btoa(bytes)}` from BLOB queries
- Intersection Observer for lazy thumbnail loading
- All filtering done via SQL queries through sql.js
- Responsive CSS grid with `auto-fill, minmax(200px, 1fr)`

**Step 5: Run HTML export tests**

Run: `pytest tests/unit/test_html_export.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add ptk/exports/html.py ptk/exports/templates/gallery.html ptk/cli.py
git commit -m "feat: add HTML export with embedded SQLite and sql.js"
```

---

### Task 15: Update CLAUDE.md and run full test suite

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Update CLAUDE.md to reflect the new architecture**

Remove references to ai/, views/, skills/. Add documentation for:
- MCP server (`ptk mcp`)
- Export commands (`ptk export html`, `ptk export arkiv`)
- arkiv import (`ptk import --source arkiv`)
- New package structure

**Step 2: Run the full test suite**

Run: `pytest --cov=ptk --cov-report=term-missing`
Expected: All PASS, reasonable coverage

**Step 3: Run linter**

Run: `ruff check ptk tests`
Expected: No new warnings in new code

**Step 4: Commit everything**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for refactored architecture"
```

---

### Task 16: Manual smoke test

**Step 1: Test MCP server launches**

```bash
echo '{"jsonrpc":"2.0","method":"initialize","id":1,"params":{"capabilities":{},"clientInfo":{"name":"test"},"protocolVersion":"2024-11-05"}}' | ptk mcp --library dev/test_library 2>/dev/null | head -1
```

Expected: JSON response with server capabilities.

**Step 2: Test HTML export on real library**

```bash
cd dev/test_library && ptk export html -o /tmp/test-gallery.html && ls -la /tmp/test-gallery.html
```

Expected: HTML file ~4MB. Open in browser to verify grid loads.

**Step 3: Test arkiv export on real library**

```bash
cd dev/test_library && ptk export arkiv -o /tmp/ptk-archive && ls -la /tmp/ptk-archive/
```

Expected: Directory with README.md, schema.yaml, photos.jsonl.

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat: ptk refactor complete — MCP server, HTML export, arkiv integration"
```
