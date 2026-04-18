# photo-memex Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename ptk's public identity to photo-memex and close the ecosystem contract gaps (soft delete, FTS5, arkiv `kind`/`uri` fields, marginalia).

**Architecture:** Two buckets executed sequentially. Bucket 1 updates user-facing strings, pyproject.toml, constants, and tests (no directory rename). Bucket 2 adds ecosystem contract features one at a time: `archived_at` soft delete, FTS5 over captions, arkiv export schema alignment, and a marginalia table. Each feature is independently testable and committable.

**Tech Stack:** Python 3.11+, SQLAlchemy 2.x, SQLite, FastMCP, Typer, pytest

---

## Bucket 1: Identity Rename

### Task 1: Update pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Update project metadata**

```toml
[project]
name = "photo-memex"
version = "0.1.0"
description = "Personal photo library archive with MCP server for AI annotation"
```

- [ ] **Step 2: Add photo-memex CLI entry point alongside ptk**

```toml
[project.scripts]
photo-memex = "ptk.cli:app"
ptk = "ptk.cli:app"
```

Keep `ptk` as an alias so existing users and MCP configs don't break.

- [ ] **Step 3: Update URLs**

```toml
[project.urls]
Homepage = "https://github.com/queelius/photo-memex"
Repository = "https://github.com/queelius/photo-memex"
```

- [ ] **Step 4: Reinstall and verify both entry points work**

Run: `pip install -e ".[dev,mcp]" && photo-memex --version && ptk --version`
Expected: Both print `photo-memex version 0.1.0`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "feat: rename package to photo-memex, keep ptk as CLI alias"
```

### Task 2: Update constants and __init__.py

**Files:**
- Modify: `ptk/core/constants.py`
- Modify: `ptk/__init__.py`

- [ ] **Step 1: Update APP_NAME constant**

In `ptk/core/constants.py`, change:

```python
APP_NAME: Final[str] = "photo-memex"
```

Keep `DEFAULT_DATABASE_NAME` as `"ptk.db"` for backward compatibility. Existing libraries have `ptk.db` on disk and `find_library()` walks up looking for it. Changing this would break all existing libraries.

- [ ] **Step 2: Update module docstring**

In `ptk/__init__.py`, change line 1:

```python
"""photo-memex - Personal photo library archive."""
```

- [ ] **Step 3: Update test that checks APP_NAME in XDG path**

In `tests/unit/test_config.py`, change the last test:

```python
def test_default_library_path():
    """Test that default_library_path returns a valid path."""
    default_lib = PtkConfig.default_library_path()
    assert isinstance(default_lib, Path)
    assert "photo-memex" in str(default_lib)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_config.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add ptk/core/constants.py ptk/__init__.py tests/unit/test_config.py
git commit -m "feat: update APP_NAME to photo-memex, keep ptk.db for backcompat"
```

### Task 3: Update CLI user-facing strings

**Files:**
- Modify: `ptk/cli.py`
- Modify: `tests/integration/test_cli.py`

- [ ] **Step 1: Update Typer app name and help text**

In `ptk/cli.py`:

```python
app = typer.Typer(
    name="photo-memex",
    help="photo-memex - Personal photo library archive",
    no_args_is_help=True,
)
```

- [ ] **Step 2: Update version callback**

```python
def version_callback(value: bool) -> None:
    if value:
        console.print(f"photo-memex version {__version__}")
        raise typer.Exit()
```

- [ ] **Step 3: Update library-not-found error message**

In `_require_library()`:

```python
    if library_path is None:
        console.print("[red]No photo-memex library found.[/red]")
        console.print("Run 'photo-memex init' to create one, or 'ptk init'.")
        raise typer.Exit(1)
```

- [ ] **Step 4: Update init success message**

```python
    console.print(f"[green]Initialized photo-memex library at {target}[/green]")
```

- [ ] **Step 5: Update default export paths and titles**

In `export_arkiv_cmd`:
```python
    output_dir = output or Path("photo-memex-export")
```

In `export_html_cmd`:
```python
    title: str = typer.Option("photo-memex Photo Library", "--title", "-t", help="Gallery title"),
```
```python
    output_path = output or Path("photo-memex-export.html")
```

- [ ] **Step 6: Update CLI test assertions**

In `tests/integration/test_cli.py`:

```python
def test_version():
    """Test --version flag."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "photo-memex version" in result.output


def test_help():
    """Test --help flag."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "photo-memex" in result.output
```

- [ ] **Step 7: Run CLI tests**

Run: `pytest tests/integration/test_cli.py -v`
Expected: All pass

- [ ] **Step 8: Commit**

```bash
git add ptk/cli.py tests/integration/test_cli.py
git commit -m "feat: update CLI strings to photo-memex identity"
```

### Task 4: Update MCP server name

**Files:**
- Modify: `ptk/mcp/server.py`

- [ ] **Step 1: Update FastMCP name and install message**

In `ptk/mcp/server.py`, change line 491:

```python
    mcp = FastMCP("photo-memex")
```

And update the ImportError message (line 483):

```python
        raise ImportError(
            "MCP server requires 'mcp' package. Install with: pip install photo-memex[mcp]"
        ) from exc
```

- [ ] **Step 2: Run MCP tests**

Run: `pytest tests/unit/test_mcp_server.py -v`
Expected: All pass (tests don't assert on the FastMCP name string)

- [ ] **Step 3: Commit**

```bash
git add ptk/mcp/server.py
git commit -m "feat: update MCP server name to photo-memex"
```

### Task 5: Update export strings

**Files:**
- Modify: `ptk/exports/arkiv.py`
- Modify: `ptk/exports/html.py`
- Modify: `tests/unit/test_arkiv_export.py`
- Modify: `tests/unit/test_html_export.py`

- [ ] **Step 1: Update arkiv export defaults**

In `ptk/exports/arkiv.py`, change the `export_arkiv` function:

```python
    archive_name = title or "photo-memex library"
    frontmatter = {
        "name": archive_name,
        "description": f"Photo library exported from photo-memex ({count} photos)",
        "datetime": now.isoformat(),
        "generator": f"photo-memex {__version__}",
```

- [ ] **Step 2: Update HTML export default title**

In `ptk/exports/html.py`, change the function signature:

```python
def export_html(output_path: Path, title: str = "photo-memex Photo Library") -> int:
```

- [ ] **Step 3: Update arkiv test assertions**

In `tests/unit/test_arkiv_export.py`, change line 52:

```python
        assert frontmatter["generator"].startswith("photo-memex")
```

- [ ] **Step 4: Update HTML test assertions**

In `tests/unit/test_html_export.py`, change line 49:

```python
        assert "photo-memex Photo Library" in content
```

- [ ] **Step 5: Run export tests**

Run: `pytest tests/unit/test_arkiv_export.py tests/unit/test_html_export.py -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add ptk/exports/arkiv.py ptk/exports/html.py tests/unit/test_arkiv_export.py tests/unit/test_html_export.py
git commit -m "feat: update export defaults to photo-memex identity"
```

### Task 6: Full test suite verification

- [ ] **Step 1: Run full test suite**

Run: `pytest --tb=short`
Expected: All ~260 tests pass

- [ ] **Step 2: Run linter**

Run: `ruff check ptk tests`
Expected: No errors

---

## Bucket 2: Ecosystem Contract Gaps

### Task 7: Add `archived_at` soft delete to all record tables

**Files:**
- Modify: `ptk/db/models.py`
- Modify: `ptk/query/builder.py`
- Modify: `ptk/mcp/server.py`
- Create: `tests/unit/test_soft_delete.py`

- [ ] **Step 1: Write failing tests for soft delete**

Create `tests/unit/test_soft_delete.py`:

```python
"""Tests for soft delete (archived_at) on all record tables."""

from datetime import datetime, timezone

import pytest

from ptk.db.models import Album, Event, Photo, Tag
from ptk.db.session import get_session


class TestSoftDelete:
    """Verify archived_at column exists and defaults to None."""

    def test_photo_has_archived_at(self, populated_library, db_session):
        photo = db_session.query(Photo).first()
        assert photo.archived_at is None

    def test_photo_can_be_archived(self, populated_library, db_session):
        photo = db_session.query(Photo).first()
        photo.archived_at = datetime.now(timezone.utc)
        db_session.commit()

        reloaded = db_session.query(Photo).filter_by(id=photo.id).first()
        assert reloaded.archived_at is not None

    def test_tag_has_archived_at(self, populated_library, db_session):
        tag = Tag(name="test-archive")
        db_session.add(tag)
        db_session.commit()
        assert tag.archived_at is None

    def test_album_has_archived_at(self, populated_library, db_session):
        now = datetime.now(timezone.utc)
        album = Album(name="test-archive", created_at=now, updated_at=now)
        db_session.add(album)
        db_session.commit()
        assert album.archived_at is None

    def test_event_has_archived_at(self, populated_library, db_session):
        event = Event(name="test-archive", is_auto_detected=False)
        db_session.add(event)
        db_session.commit()
        assert event.archived_at is None


class TestQueryBuilderFiltersArchived:
    """QueryBuilder should exclude archived photos by default."""

    def test_excludes_archived_photos(self, populated_library, db_session):
        from ptk.query import QueryBuilder

        photo = db_session.query(Photo).first()
        photo.archived_at = datetime.now(timezone.utc)
        db_session.commit()

        builder = QueryBuilder()
        sql, params = builder.build()
        assert "archived_at IS NULL" in sql

    def test_no_results_when_all_archived(self, populated_library, db_session):
        from ptk.query import QueryBuilder, execute_query

        photo = db_session.query(Photo).first()
        photo.archived_at = datetime.now(timezone.utc)
        db_session.commit()

        builder = QueryBuilder()
        result = execute_query(db_session, builder)
        assert result.count == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_soft_delete.py -v`
Expected: FAIL (no `archived_at` attribute)

- [ ] **Step 3: Add `archived_at` column to Photo model**

In `ptk/db/models.py`, add to the Photo class after the `source_metadata` field:

```python
    # Soft delete (ecosystem contract)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
```

- [ ] **Step 4: Add `archived_at` to Tag, Album, Event, Person, Face**

Add the same column to each model class:

```python
    # Soft delete (ecosystem contract)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
```

For Tag, add after the `color` field.
For Album, add after `updated_at`.
For Event, add after `is_auto_detected`.
For Person, add after `created_at`.
For Face, add after `confidence`.

- [ ] **Step 5: Add `archived_at IS NULL` filter to QueryBuilder**

In `ptk/query/builder.py`, in the `build()` method, add after `where = []`:

```python
        # Soft delete: exclude archived photos by default
        where.append("p.archived_at IS NULL")
```

- [ ] **Step 6: Run soft delete tests**

Run: `pytest tests/unit/test_soft_delete.py -v`
Expected: All pass

- [ ] **Step 7: Run full test suite**

Run: `pytest --tb=short`
Expected: All pass

- [ ] **Step 8: Commit**

```bash
git add ptk/db/models.py ptk/query/builder.py tests/unit/test_soft_delete.py
git commit -m "feat: add archived_at soft delete to all record tables"
```

### Task 8: Add FTS5 full-text search over captions

**Files:**
- Modify: `ptk/db/session.py`
- Create: `tests/unit/test_fts.py`

- [ ] **Step 1: Write failing tests for FTS5**

Create `tests/unit/test_fts.py`:

```python
"""Tests for FTS5 full-text search over photo captions."""

import sqlite3

import pytest

from ptk.db.models import Photo
from ptk.db.session import get_engine


class TestFts5Setup:
    """Verify FTS5 virtual table is created and synced."""

    def test_fts_table_exists(self, test_library):
        engine = get_engine()
        url = str(engine.url).replace("sqlite:///", "")
        conn = sqlite3.connect(url)
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        conn.close()
        assert "photos_fts" in tables

    def test_fts_search_finds_captioned_photo(self, populated_library, db_session):
        photo = db_session.query(Photo).first()
        photo.caption = "beautiful sunset over the ocean"
        db_session.commit()

        engine = get_engine()
        url = str(engine.url).replace("sqlite:///", "")
        conn = sqlite3.connect(url)
        results = conn.execute(
            "SELECT id FROM photos_fts WHERE photos_fts MATCH 'sunset'"
        ).fetchall()
        conn.close()
        assert len(results) == 1
        assert results[0][0] == photo.id

    def test_fts_no_match(self, populated_library, db_session):
        photo = db_session.query(Photo).first()
        photo.caption = "a red test image"
        db_session.commit()

        engine = get_engine()
        url = str(engine.url).replace("sqlite:///", "")
        conn = sqlite3.connect(url)
        results = conn.execute(
            "SELECT id FROM photos_fts WHERE photos_fts MATCH 'sunset'"
        ).fetchall()
        conn.close()
        assert len(results) == 0

    def test_fts_updates_on_caption_change(self, populated_library, db_session):
        photo = db_session.query(Photo).first()
        photo.caption = "old caption"
        db_session.commit()

        photo.caption = "new sunset caption"
        db_session.commit()

        engine = get_engine()
        url = str(engine.url).replace("sqlite:///", "")
        conn = sqlite3.connect(url)
        results = conn.execute(
            "SELECT id FROM photos_fts WHERE photos_fts MATCH 'sunset'"
        ).fetchall()
        conn.close()
        assert len(results) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_fts.py -v`
Expected: FAIL (no `photos_fts` table)

- [ ] **Step 3: Add FTS5 setup to init_db**

In `ptk/db/session.py`, add a helper function and call it from `init_db`:

```python
def _setup_fts(engine: Engine) -> None:
    """Create FTS5 virtual table and sync triggers for photo captions."""
    with engine.connect() as conn:
        raw = conn.connection.dbapi_connection
        raw.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS photos_fts
            USING fts5(id UNINDEXED, caption, location_name, content='photos', content_rowid='rowid');

            CREATE TRIGGER IF NOT EXISTS photos_fts_insert AFTER INSERT ON photos BEGIN
                INSERT INTO photos_fts(id, caption, location_name)
                VALUES (new.id, new.caption, new.location_name);
            END;

            CREATE TRIGGER IF NOT EXISTS photos_fts_update AFTER UPDATE OF caption, location_name ON photos BEGIN
                DELETE FROM photos_fts WHERE id = old.id;
                INSERT INTO photos_fts(id, caption, location_name)
                VALUES (new.id, new.caption, new.location_name);
            END;

            CREATE TRIGGER IF NOT EXISTS photos_fts_delete AFTER DELETE ON photos BEGIN
                DELETE FROM photos_fts WHERE id = old.id;
            END;
        """)
```

Then in `init_db`, after `Base.metadata.create_all(bind=_engine)`, add:

```python
    if create_tables:
        Base.metadata.create_all(bind=_engine)
        _setup_fts(_engine)
```

- [ ] **Step 4: Run FTS tests**

Run: `pytest tests/unit/test_fts.py -v`
Expected: All pass

- [ ] **Step 5: Run full test suite**

Run: `pytest --tb=short`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add ptk/db/session.py tests/unit/test_fts.py
git commit -m "feat: add FTS5 full-text search over photo captions"
```

### Task 9: Add `kind` and cross-archive `uri` to arkiv export

**Files:**
- Modify: `ptk/exports/arkiv.py`
- Modify: `tests/unit/test_arkiv_export.py`

- [ ] **Step 1: Write failing tests for new arkiv fields**

Add to `tests/unit/test_arkiv_export.py`:

```python
    def test_jsonl_record_has_kind(self, library_with_tagged_photo, tmp_path):
        """Each JSONL record has a kind field."""
        from ptk.exports.arkiv import export_arkiv

        output_dir = tmp_path / "arkiv-out"
        export_arkiv(output_dir)

        jsonl_path = output_dir / "photos.jsonl"
        record = json.loads(jsonl_path.read_text().strip().split("\n")[0])
        assert record["kind"] == "photo"

    def test_jsonl_record_has_archive_uri(self, library_with_tagged_photo, tmp_path, db_session):
        """Each JSONL record has a photo-memex:// URI."""
        from ptk.exports.arkiv import export_arkiv

        output_dir = tmp_path / "arkiv-out"
        export_arkiv(output_dir)

        jsonl_path = output_dir / "photos.jsonl"
        record = json.loads(jsonl_path.read_text().strip().split("\n")[0])

        photo = db_session.query(Photo).first()
        assert record["id"] == f"photo-memex://photo/{photo.id}"

    def test_jsonl_record_still_has_file_uri(self, library_with_tagged_photo, tmp_path):
        """Each JSONL record still has the file:// URI in source_path."""
        from ptk.exports.arkiv import export_arkiv

        output_dir = tmp_path / "arkiv-out"
        export_arkiv(output_dir)

        jsonl_path = output_dir / "photos.jsonl"
        record = json.loads(jsonl_path.read_text().strip().split("\n")[0])
        assert record["source_path"].startswith("file:///")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_arkiv_export.py::TestArkivExport::test_jsonl_record_has_kind -v`
Expected: FAIL (no `kind` key)

- [ ] **Step 3: Update `_photo_to_record` to include `kind`, `id`, and `source_path`**

In `ptk/exports/arkiv.py`, update the `_photo_to_record` function:

```python
def _photo_to_record(photo: Photo) -> dict[str, Any]:
    """Convert a Photo model instance to an arkiv record dict."""
    metadata: dict[str, Any] = {"sha256": photo.id}

    # Add optional scalar fields, omitting None and False booleans
    for field in _OPTIONAL_METADATA_FIELDS:
        value = getattr(photo, field)
        if value is None:
            continue
        if isinstance(value, bool) and not value:
            continue
        metadata[field] = value

    # Tags (sorted, omit if empty)
    if photo.tags:
        metadata["tags"] = sorted(t.name for t in photo.tags)

    # Albums (sorted, omit if empty)
    if photo.albums:
        metadata["albums"] = sorted(a.name for a in photo.albums)

    record: dict[str, Any] = {
        "kind": "photo",
        "id": f"photo-memex://photo/{photo.id}",
        "source_path": Path(photo.original_path).as_uri(),
        "mimetype": photo.mime_type,
        "metadata": metadata,
    }

    if photo.date_taken is not None:
        record["timestamp"] = photo.date_taken.isoformat()

    return record
```

- [ ] **Step 4: Update old test that checks `uri` field**

In `tests/unit/test_arkiv_export.py`, update these tests:

`test_jsonl_record_has_required_fields` (line 106): change `"uri"` to `"id"` and `"source_path"`:

```python
    def test_jsonl_record_has_required_fields(self, library_with_tagged_photo, tmp_path):
        """Each JSONL record has kind, id, source_path, mimetype, and metadata fields."""
        from ptk.exports.arkiv import export_arkiv

        output_dir = tmp_path / "arkiv-out"
        export_arkiv(output_dir)

        jsonl_path = output_dir / "photos.jsonl"
        record = json.loads(jsonl_path.read_text().strip().split("\n")[0])

        assert "kind" in record
        assert "id" in record
        assert "source_path" in record
        assert "mimetype" in record
        assert "metadata" in record
```

`test_jsonl_uri_starts_with_file` (line 159): update to check `source_path`:

```python
    def test_jsonl_source_path_starts_with_file(self, library_with_tagged_photo, tmp_path):
        """source_path starts with file:///."""
        from ptk.exports.arkiv import export_arkiv

        output_dir = tmp_path / "arkiv-out"
        export_arkiv(output_dir)

        jsonl_path = output_dir / "photos.jsonl"
        record = json.loads(jsonl_path.read_text().strip().split("\n")[0])

        assert record["source_path"].startswith("file:///")
```

- [ ] **Step 5: Run arkiv tests**

Run: `pytest tests/unit/test_arkiv_export.py -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add ptk/exports/arkiv.py tests/unit/test_arkiv_export.py
git commit -m "feat: add kind and photo-memex:// URI to arkiv export records"
```

### Task 10: Add marginalia table

**Files:**
- Modify: `ptk/db/models.py`
- Modify: `ptk/db/__init__.py`
- Create: `tests/unit/test_marginalia.py`

- [ ] **Step 1: Write failing tests for marginalia**

Create `tests/unit/test_marginalia.py`:

```python
"""Tests for marginalia (notes attachable to any photo)."""

from datetime import datetime, timezone

import pytest

from ptk.db.models import Marginalia, Photo
from ptk.db.session import get_session


class TestMarginaliaModel:
    """Verify Marginalia model and relationship to Photo."""

    def test_create_marginalia(self, populated_library, db_session):
        photo = db_session.query(Photo).first()
        note = Marginalia(
            photo_id=photo.id,
            body="This is grandma's house",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(note)
        db_session.commit()
        assert note.id is not None

    def test_marginalia_body_required(self, populated_library, db_session):
        photo = db_session.query(Photo).first()
        note = Marginalia(
            photo_id=photo.id,
            body="A note",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(note)
        db_session.commit()
        assert note.body == "A note"

    def test_marginalia_photo_relationship(self, populated_library, db_session):
        photo = db_session.query(Photo).first()
        note = Marginalia(
            photo_id=photo.id,
            body="Note text",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(note)
        db_session.commit()
        assert note.photo.id == photo.id

    def test_photo_marginalia_list(self, populated_library, db_session):
        photo = db_session.query(Photo).first()
        note1 = Marginalia(
            photo_id=photo.id,
            body="First note",
            created_at=datetime.now(timezone.utc),
        )
        note2 = Marginalia(
            photo_id=photo.id,
            body="Second note",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add_all([note1, note2])
        db_session.commit()
        assert len(photo.marginalia) == 2

    def test_marginalia_survives_photo_deletion(self, populated_library, db_session):
        """Marginalia orphans survive when their photo is deleted (SET NULL)."""
        photo = db_session.query(Photo).first()
        photo_id = photo.id
        note = Marginalia(
            photo_id=photo_id,
            body="Orphan note",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(note)
        db_session.commit()
        note_id = note.id

        db_session.delete(photo)
        db_session.commit()

        orphan = db_session.query(Marginalia).filter_by(id=note_id).first()
        assert orphan is not None
        assert orphan.photo_id is None
        assert orphan.body == "Orphan note"

    def test_marginalia_has_archived_at(self, populated_library, db_session):
        photo = db_session.query(Photo).first()
        note = Marginalia(
            photo_id=photo.id,
            body="Archivable note",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(note)
        db_session.commit()
        assert note.archived_at is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_marginalia.py -v`
Expected: FAIL (no `Marginalia` class)

- [ ] **Step 3: Add Marginalia model**

In `ptk/db/models.py`, add after the Tag class:

```python
class Marginalia(Base):
    """Free-form note attachable to a photo. Survives photo deletion (orphan survival)."""

    __tablename__ = "marginalia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    photo_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("photos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Soft delete (ecosystem contract)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # Relationships
    photo: Mapped["Photo | None"] = relationship("Photo", back_populates="marginalia")

    def __repr__(self) -> str:
        target = f"photo {self.photo_id[:8]}..." if self.photo_id else "orphan"
        return f"<Marginalia {self.id} on {target}>"
```

- [ ] **Step 4: Add relationship to Photo model**

In the Photo class, add after the `faces` relationship:

```python
    marginalia: Mapped[list["Marginalia"]] = relationship(
        "Marginalia", back_populates="photo", cascade="save-update, merge"
    )
```

Note: no `delete-orphan` cascade since marginalia survive photo deletion.

- [ ] **Step 5: Update `ptk/db/__init__.py` exports**

```python
from ptk.db.models import Album, Base, Event, Face, Marginalia, Person, Photo, Tag

__all__ = [
    "init_db",
    "get_session",
    "get_engine",
    "Base",
    "Photo",
    "Face",
    "Person",
    "Event",
    "Album",
    "Tag",
    "Marginalia",
]
```

- [ ] **Step 6: Run marginalia tests**

Run: `pytest tests/unit/test_marginalia.py -v`
Expected: All pass

- [ ] **Step 7: Run full test suite**

Run: `pytest --tb=short`
Expected: All pass

- [ ] **Step 8: Commit**

```bash
git add ptk/db/models.py ptk/db/__init__.py tests/unit/test_marginalia.py
git commit -m "feat: add marginalia table with orphan survival per ecosystem contract"
```

### Task 11: Final verification and CLAUDE.md update

- [ ] **Step 1: Run full test suite with coverage**

Run: `pytest --cov=ptk --tb=short`
Expected: All pass, coverage report shows new files covered

- [ ] **Step 2: Run linter**

Run: `ruff check ptk tests && ruff format --check ptk tests`
Expected: Clean

- [ ] **Step 3: Update CLAUDE.md ecosystem contract table**

Update the table in CLAUDE.md to reflect new status:

```markdown
| Contract item | Status | Notes |
|---|---|---|
| SQLite + FTS5 backend | Done | `photos_fts` over caption and location_name |
| MCP server | Done | `run_sql`, `get_schema`, ~18 domain tools |
| Thin admin CLI | Done | init, import, query, set, stats, verify, relocate, rescan, export |
| Import pipelines | Done | filesystem, google_takeout, apple_photos |
| Export (arkiv, HTML, markdown, JSON) | Partial | arkiv and HTML done; markdown and JSON not yet |
| Durable record IDs | Done | SHA256 of file content |
| Marginalia | Done | `marginalia` table with orphan survival |
| Soft delete (`archived_at`) | Done | All record tables: Photo, Tag, Album, Event, Person, Face, Marginalia |
| URI scheme (`photo-memex://photo/<sha256>`) | Partial | Used in arkiv export; no `core/uri.py` module yet |
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md contract status after photo-memex alignment"
```
