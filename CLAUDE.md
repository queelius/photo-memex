# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ptk (Photo Toolkit) is a CLI tool for managing personal photo libraries. Part of the longecho personal archive ecosystem (ctk, btk, ebk, stk, mtk).

**Current Status:** Lean data toolkit — import, organization, query, path management, MCP server, arkiv/HTML export. AI annotation is delegated to Claude Code via the MCP server.

## Development Commands

```bash
# Setup
pip install -e ".[dev]"

# Testing
pytest                          # All ~265 tests
pytest tests/unit/              # Fast unit tests only
pytest tests/integration/       # Integration tests only
pytest -v -k "test_query"       # Run specific tests by name
pytest --cov=ptk                # With coverage

# Linting
ruff check ptk tests
ruff format ptk tests
```

## Architecture

- **SQLite-backed** metadata storage (ptk.db), no migration system — `Base.metadata.create_all()` on `ptk init`
- **CLI-first** using Typer sub-apps + Rich
- **SHA256 deduplication** — content hash is the Photo primary key
- **MCP server** — stdio-based, dual-connection (raw sqlite3 for reads, SQLAlchemy for writes). ~20 tools for querying, annotating, tagging, and organizing photos.
- **Global singletons** — `db/session.py` (engine, sessionmaker), `core/config.py` (PtkConfig)

### Key Layers

- `cli.py` — All commands in one file. Typer sub-apps for `export`. Every DB command calls `_require_library()` first (finds ptk.db by walking up from cwd, inits engine).
- `db/models.py` — Photo (SHA256 PK), Tag, Album (M2M), Face, Person, Event, PhotoEmbedding. Photo has JSON columns (`objects`, `source_metadata`).
- `db/session.py` — Module-level singletons. `session_scope()` context manager for all transactions. SQLite pragmas: `foreign_keys=ON`, `journal_mode=WAL`.
- `importers/` — `BaseImporter` ABC → filesystem, google_takeout, apple_photos. `ImportService` orchestrates: hash → deduplicate → EXIF → thumbnail → Photo.
- `query/builder.py` — `QueryBuilder` dataclass with fluent API, generates raw SQL. Tag filters use one JOIN pair per tag (AND semantics).
- `query/executor.py` — Two-step: raw SQL for ordered IDs, then ORM `.in_()` fetch + reorder. `OutputFormat` enum: TABLE, JSON, IDS, COUNT, PATHS.
- `mcp/server.py` — `PtkServer` class with dual connections: raw sqlite3 for read-only SQL, SQLAlchemy `session_scope()` for writes. `run_mcp_server()` wraps it in FastMCP with stdio transport and `ToolAnnotations`. Read tools: `get_schema`, `get_stats`, `run_sql`, `get_thumbnail`, `get_photo`, `list_tags/albums/people`. Write tools: `set_caption`, `add/remove_tags`, `set_favorite`, `add_to/remove_from_album`, `set_scene`, `tag/untag_person`, `create_event`, `add_to_event`, `batch_add_tags`, `batch_set_caption`. All photo tools accept SHA256 prefix lookup via `_resolve_photo()`.
- `exports/arkiv.py` — Exports library to arkiv format (JSONL + README.md + schema.yaml). Denormalizes tags/albums into each record.
- `exports/html.py` — Single-file HTML export. Uses SQLite `backup()` API (WAL-safe), strips heavy BLOBs, base64-encodes DB, embeds in sql.js-powered gallery template.

### Package Structure

```
ptk/
├── cli.py              # All CLI commands + export sub-app + mcp command
├── core/               # config, hasher, exif, thumbnails, constants
├── db/                 # models (Photo, Tag, Album, Face, Person, Event), session
├── importers/          # filesystem, google_takeout, apple_photos
├── services/           # import_service
├── query/              # builder, executor
├── mcp/                # FastMCP stdio server (~20 tools: read, write, person, event, batch)
└── exports/            # arkiv (JSONL), html (single-file browser)
    └── templates/      # gallery.html template
```

## Testing Patterns

- **Root conftest.py** provides all fixtures: `temp_dir`, `sample_image` (100x100 red JPEG via Pillow), `sample_png`, `test_library` (inits DB + teardown via `close_db()`), `db_session`, `populated_library`
- **Integration tests** use `CliRunner` from typer.testing + `os.chdir()` into a temp library dir (since `find_library()` walks from cwd). Always chdir back in teardown.
- **QueryBuilder unit tests** assert on generated SQL strings directly (e.g., checking for `"JOIN photo_tags pt0"`)
- **MCP server tests** use `populated_library` fixture + direct `PtkServer` class instantiation (no MCP transport)
- **Export tests** use `populated_library` and verify file contents (JSONL records, HTML structure, embedded DB validity)
- No per-directory conftest files — everything from root

## Things to Know

- Entry point is `ptk.cli:app`. `ptk/exports/` has the html and arkiv exporters.
- `Photo.objects` is a JSON column on the Photo model — stores AI-detected objects if any were added.
- The HTML export uses `sqlite3.Connection.backup()` instead of `shutil.copy2` because WAL mode means the DB file alone is incomplete.
- The HTML export VACUUMs with a separate `isolation_level=None` connection since VACUUM can't run inside an implicit transaction.
- MCP server uses raw `sqlite3` for read-only SQL and SQLAlchemy `session_scope()` for structured writes. Write tools return `{"status": "ok", ...current_state}`.
- Person tagging creates Face records with `bbox=(0,0,1,1)` and `confidence=0.0` as manual-identification placeholders.

## MCP Server Configuration

```json
{
  "mcpServers": {
    "ptk": {
      "command": "ptk",
      "args": ["mcp"],
      "env": {"PTK_LIBRARY": "/path/to/library"}
    }
  }
}
```
