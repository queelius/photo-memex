# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

**photo-memex** (Python package `photo_memex`; the `ptk` name is retained as a CLI alias for backward compatibility). Personal photo library manager and photo-domain archive of the `*-memex` family. See `~/github/memex/CLAUDE.md` for ecosystem conventions and the 7-item archive contract.

SQLAlchemy + SQLite backend with FTS5, SHA256 content hash as Photo primary key, multi-source import (filesystem, Google Takeout, Apple Photos), MCP server with 21 tools, CLI, arkiv/HTML export. AI annotation delegated to Claude Code via MCP (no built-in AI providers).

## Development commands

```bash
# Setup (mcp extra needed for MCP server code and tests)
pip install -e ".[dev,mcp]"

# Testing
pytest                          # All tests
pytest tests/unit/              # Fast unit tests only
pytest tests/integration/       # Integration tests only
pytest -v -k "test_query"       # Run specific tests by name
pytest --cov=photo_memex                # With coverage

# Linting
ruff check photo_memex tests
ruff format photo_memex tests
```

## Architecture

- **SQLite-backed** metadata storage (`photo-memex.db`), no migration system. `Base.metadata.create_all()` on `ptk init`.
- **CLI-first** using Typer sub-apps + Rich. Entry points: `photo-memex` and `ptk` (backward-compat alias), both map to `photo_memex.cli:app`.
- **SHA256 deduplication**: content hash is the Photo primary key.
- **MCP server**: stdio-based, dual-connection architecture (raw sqlite3 for read-only SQL, SQLAlchemy `session_scope()` for writes). 21 tools for querying, annotating, tagging, and organizing photos.
- **Global singletons**: `db/session.py` (engine, sessionmaker), `core/config.py` (PtkConfig). Tests must call `close_db()` in teardown to reset module-level state between test cases.

### Key layers

- `cli.py`: All commands in one file. Typer sub-apps for `export`. Every DB command calls `_require_library()` first (finds `photo-memex.db` by walking up from cwd, inits engine).
- `db/models.py`: `SoftDeleteMixin` provides `archived_at` to all record models. Photo (SHA256 PK), Tag, Album (M2M), Face, Person, Event, Marginalia. Photo has JSON columns (`objects`, `source_metadata`). Three M2M association tables: `photo_tags`, `photo_albums`, `photo_events`. Marginalia uses `ON DELETE SET NULL` for orphan survival.
- `db/session.py`: Module-level singletons (`_engine`, `_SessionLocal`). `session_scope()` context manager for all transactions (auto-commit on exit, rollback on exception). SQLite pragmas set via SQLAlchemy event listener: `foreign_keys=ON`, `journal_mode=WAL`. `_setup_fts()` creates the `photos_fts` FTS5 virtual table with sync triggers and backfills existing photos.
- `importers/`: `BaseImporter` ABC with filesystem, google_takeout, apple_photos implementations. `ImportService` (in `services/import_service.py`) orchestrates: hash, deduplicate, EXIF, thumbnail, Photo. Source metadata (e.g., Google Takeout JSON) used as fallback for date_taken and GPS.
- `query/builder.py`: `QueryBuilder` dataclass with fluent API, generates raw SQL. Tag filters use one JOIN pair per tag (AND semantics). Album filters use the same pattern.
- `query/executor.py`: Two-step execution: raw SQL for ordered IDs, then ORM `.in_()` fetch + reorder. This preserves SQL ordering while loading full ORM objects with relationships.
- `mcp/server.py`: `PtkServer` class with dual connections: raw sqlite3 for read-only SQL, SQLAlchemy `session_scope()` for writes. `run_mcp_server()` wraps it in FastMCP with stdio transport. All photo-specific tools accept SHA256 prefix lookup via `_resolve_photo()` (min 4 chars, must be unambiguous, excludes archived). All default queries filter `archived_at IS NULL`.
- `exports/arkiv.py`: Exports to arkiv format (JSONL + README.md + schema.yaml). Each record has `kind: "photo"`, `id: "photo-memex://photo/<sha256>"`, `source_path` (file URI). Denormalizes tags/albums. Excludes archived photos.
- `exports/html.py`: Single-file HTML export. Uses SQLite `backup()` API (WAL-safe), strips heavy BLOBs, base64-encodes DB, embeds in sql.js-powered gallery template.

### MCP tool inventory

Three `ToolAnnotations` presets control LLM tool-selection behavior:
- `_read`: `readOnlyHint=True`. Safe to call speculatively.
- `_write`: `idempotentHint=True`, `destructiveHint=False`. Additive operations (set caption, add tags, add to album).
- `_destructive`: `destructiveHint=True`, `idempotentHint=True`. Removal operations that delete data.

Read tools (8, raw sqlite3):
- `get_schema`, `get_stats`, `run_sql`, `get_thumbnail`, `get_photo`, `list_tags`, `list_albums`, `list_people`

Write tools (11, SQLAlchemy `session_scope()`, return `{"status": "ok", ...current_state}`):
- `set_caption`, `add_tags`, `set_favorite`, `add_to_album`, `set_scene`, `tag_person`, `create_event`, `add_to_event`, `batch_add_tags`, `batch_set_caption`

Destructive tools (3, also uses `session_scope()`):
- `remove_tags`, `remove_from_album`, `untag_person` (tagged `_destructive`, these actually delete junction/face rows)

## Testing patterns

- **Root `tests/conftest.py`** provides all fixtures: `temp_dir`, `sample_image` (100x100 red JPEG via Pillow), `sample_png`, `test_library` (inits DB + teardown via `close_db()`), `db_session`, `populated_library` (imports `sample_image` via `FilesystemImporter`).
- **Integration tests** use `CliRunner` from typer.testing + `os.chdir()` into a temp library dir (since `find_library()` walks from cwd). Always chdir back in teardown.
- **QueryBuilder unit tests** assert on generated SQL strings directly (e.g., checking for `"JOIN photo_tags pt0"`).
- **MCP server tests** use `populated_library` fixture + direct `PtkServer` class instantiation (no MCP transport). Tests organized as one class per MCP tool (e.g., `TestSetCaption`, `TestAddTags`, `TestBatchAddTags`).
- **Export tests** use `populated_library` and verify file contents (JSONL records, HTML structure, embedded DB validity).
- No per-directory conftest files; everything lives in root `tests/conftest.py`.

## Things to know

- `Photo.objects` is a JSON column that stores AI-detected objects if any were added via MCP.
- HTML export uses `sqlite3.Connection.backup()` instead of `shutil.copy2` because WAL mode means the DB file alone is incomplete.
- HTML export VACUUMs with a separate `isolation_level=None` connection since VACUUM can't run inside an implicit transaction.
- Person tagging creates Face records with `bbox=(0,0,1,1)` and `confidence=0.0` as manual-identification placeholders. No face detection, just identity tracking.
- `run_sql` enforces read-only: strips leading SQL comments, rejects anything that doesn't start with `SELECT`, executes the cleaned query. Multi-statement protection is provided by sqlite3's single-statement enforcement.
- `_batch_apply` collects per-photo errors and returns status `"ok"`, `"partial"`, or `"error"`. Callers don't need try/except.
- Library discovery (`find_library()`) walks from cwd upward looking for `photo-memex.db`. The MCP server can also accept a library path via `PTK_LIBRARY` env var or `--library` flag.
- `set_caption` and `set_scene` accept an optional `model` param for AI provenance tracking (`ai_model`, `ai_analyzed_at` columns on Photo).

## MCP server configuration

```json
{
  "mcpServers": {
    "photo-memex": {
      "command": "ptk",
      "args": ["mcp"],
      "env": {"PTK_LIBRARY": "/path/to/library"}
    }
  }
}
```
