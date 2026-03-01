# ptk Refactor: MCP Server + HTML Export + arkiv Integration + AI Removal

**Date:** 2026-02-28
**Status:** Approved

## Summary

Refactor ptk from a CLI-with-built-in-AI tool to a lean data toolkit with three new capabilities:

1. **MCP server** (`ptk mcp`) — stdio MCP server exposing SQL + schema for Claude Code integration
2. **HTML export** (`ptk export html`) — Single-file HTML photo browser with embedded SQLite DB
3. **arkiv integration** — Export to and import from the arkiv universal interchange format

The built-in AI provider system, view annotation system, and Claude Code skill installer are removed. Claude Code itself (via the MCP server) replaces all of these.

## Removals

### Files to delete

- `ptk/ai/` — All providers (ollama, openai, anthropic), annotations, provider ABC, `__init__.py`
- `ptk/views/` — schema, loader, evaluator, manager, models
- `ptk/skills/` — Installer and templates
- `ptk/cli_old.py` — Pre-refactor CLI (70KB, unused)

### CLI commands to remove

- `ai` command group (status, describe, ask, annotate, batch, profiles)
- `claude` command group (install, uninstall, status, show)
- `view` command group (list, create, run, delete, query)

### Code to update

- `db/session.py` — Remove side-effect import of `ptk.views.models`
- `db/models.py` — Remove `View` and `ViewAnnotation` models (they live in views/)
- `query/builder.py` — Remove view field filtering (`--field` flag support)
- `query/executor.py` — Remove view-related imports
- `pyproject.toml` — Remove `captioning` and `embeddings` optional dependency groups

### What stays

- `ptk/core/` — config, hasher, exif, thumbnails, constants
- `ptk/db/` — Photo, Tag, Album, Face, Person, Event, PhotoEmbedding models; session management
- `ptk/importers/` — filesystem, google_takeout, apple_photos
- `ptk/services/` — import_service
- `ptk/query/` — QueryBuilder + executor (simplified)
- CLI commands: init, import, query/q, show, set, stats, verify, relocate, rescan

## Feature 1: MCP Server

### CLI

```
ptk mcp    # Launch stdio MCP server
```

### Tools

| Tool | Input | Output |
|------|-------|--------|
| `run_sql` | `query: str` | JSON rows. Read-only (SELECT only, enforced). |
| `get_schema` | — | All CREATE TABLE statements from the DB |
| `get_stats` | — | Photo count, tag count, album count, date range, total size |

### Implementation

- `ptk/mcp/__init__.py`
- `ptk/mcp/server.py` — Uses `mcp` Python SDK, stdio transport
- On startup: `find_library()` + `init_db()` (same as CLI commands)
- `run_sql` enforces read-only by checking `statement.strip().upper().startswith("SELECT")`
- Returns results as list of dicts with column names as keys

### Claude Code configuration

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

Library discovery: `PTK_LIBRARY` env var > `find_library()` from cwd.

## Feature 2: HTML Export

### CLI

```
ptk export html                      # → ptk-export.html
ptk export html -o gallery.html      # custom output
ptk export html --title "My Photos"  # custom title
```

### Architecture

Single self-contained HTML file containing:

1. **HTML/CSS/JS app** — inline, no external dependencies except sql.js CDN
2. **SQLite DB** — base64-encoded in a `<script type="application/x-sqlite3">` tag
3. **sql.js WASM** — loaded from CDN at runtime

### Export process

1. Copy ptk.db to a temp file
2. Strip heavy tables: `photo_embeddings`, face `embedding` and `thumbnail_data` columns
3. `VACUUM` the stripped DB
4. Base64-encode and embed in the HTML template
5. Write single output file

### HTML app features

- Thumbnail grid with lazy loading (thumbnails from `thumbnail_data` BLOB → `data:` URIs)
- Lightbox detail view: metadata, EXIF, caption, tags, albums
- Filter sidebar: tags, albums, favorites, date range
- Search over captions and filenames
- Click-through to original file path (local machine only)
- Responsive layout

### Size budget

- 260 photos: ~3MB DB → ~4MB base64 → ~4.1MB total HTML file
- sql.js WASM: ~1MB loaded from CDN (not embedded)

### Implementation

- `ptk/exports/__init__.py`
- `ptk/exports/html.py` — Export logic (strip DB, encode, render template)
- `ptk/exports/templates/gallery.html` — The HTML/CSS/JS app template with `{{DB_BASE64}}` and `{{TITLE}}` placeholders

## Feature 3: arkiv Export

### CLI

```
ptk export arkiv                     # → ptk-photos/ directory
ptk export arkiv -o my-archive/      # custom output directory
```

### Output structure

```
ptk-photos/
├── README.md       # arkiv frontmatter
├── schema.yaml     # auto-generated metadata key descriptions
└── photos.jsonl    # one record per Photo
```

### README.md

```yaml
---
name: ptk photo library
description: Personal photo library exported from ptk
datetime: "2026-02-28T12:00:00"
generator: ptk 0.1.0
contents:
  - path: photos.jsonl
    description: Photo metadata records
---

Photo library containing N photos, M tags, K albums.
```

### Record format

Each Photo → one arkiv record. Relationships denormalized, null fields omitted:

```json
{
  "mimetype": "image/jpeg",
  "uri": "file:///home/user/Photos/vacation.jpg",
  "timestamp": "2024-07-15T14:23:00",
  "metadata": {
    "sha256": "a1b2c3d4...",
    "filename": "vacation.jpg",
    "file_size": 4521389,
    "width": 4032,
    "height": 3024,
    "tags": ["beach", "sunset"],
    "albums": ["Summer 2024"],
    "caption": "Sunset at the pier",
    "is_favorite": true,
    "camera_make": "Apple",
    "camera_model": "iPhone 15 Pro",
    "lens": "iPhone 15 Pro back camera",
    "focal_length": 6.86,
    "aperture": 1.78,
    "shutter_speed": "1/1000",
    "iso": 50,
    "latitude": 37.7749,
    "longitude": -122.4194,
    "altitude": 10.5,
    "location_name": "San Francisco",
    "country": "US",
    "city": "San Francisco",
    "scene": "outdoor",
    "import_source": "filesystem"
  }
}
```

### schema.yaml

Auto-generated from the exported data. Keys like `tags` get `type: array`, `is_favorite` gets `type: boolean`, EXIF numerics get `type: number`.

### Implementation

- `ptk/exports/arkiv.py` — Iterate photos with eager-loaded tags/albums, serialize to JSONL, generate README.md and schema.yaml

## Feature 4: arkiv Import

### CLI

```
ptk import ~/archives/ptk-photos/ --source arkiv
ptk import photos.jsonl --source arkiv
```

### Import logic

New importer: `ptk/importers/arkiv.py` implementing `BaseImporter`.

For each arkiv record:

1. Parse `uri` → resolve to local file path
2. **File exists + new to ptk:** Hash file, import normally (full pipeline: EXIF, thumbnail, deduplicate by SHA256), then apply arkiv metadata (tags, albums, caption, favorite)
3. **File exists + already in ptk (SHA256 match):** Merge metadata — add new tags, add to new albums, set caption if currently empty
4. **File doesn't exist:** Skip with warning, log the URI
5. **`metadata.sha256` present but file missing:** Check if photo already exists in DB by that hash. If so, update metadata only.

### Metadata mapping (arkiv → ptk)

| arkiv field | ptk action |
|---|---|
| `metadata.tags` | Create tags if needed, add to photo |
| `metadata.albums` | Create albums if needed, add to photo |
| `metadata.caption` | Set if photo has no caption |
| `metadata.is_favorite` | Set favorite flag |
| `metadata.sha256` | Used for dedup, not stored (ptk computes its own) |
| EXIF fields | Fallback if EXIF extraction returns empty |

## Package structure (final)

```
ptk/
├── cli.py              # Slimmed CLI + export group + mcp command
├── core/               # config, hasher, exif, thumbnails, constants
├── db/                 # models (Photo, Tag, Album, Face, Person, Event), session
├── importers/          # filesystem, google_takeout, apple_photos, arkiv (NEW)
├── services/           # import_service
├── query/              # builder, executor (simplified)
├── mcp/                # NEW
│   ├── __init__.py
│   └── server.py
└── exports/            # NEW
    ├── __init__.py
    ├── html.py
    ├── arkiv.py
    └── templates/
        └── gallery.html
```

## Dependencies

### New

- `mcp` — MCP Python SDK (for stdio server)

### Removed

- `httpx` (was in `captioning` extra)
- `sentence-transformers`, `faiss-cpu` (was in `embeddings` extra)
- openai, anthropic SDKs (no longer needed)

### Unchanged

- typer, rich, sqlalchemy, pillow, exifread, python-dateutil, pydantic, pyyaml

## Testing strategy

- Unit tests for each new module (mcp/server, exports/html, exports/arkiv, importers/arkiv)
- Remove all tests for deleted modules (ai, views, skills)
- Integration tests for full export/import round-trips
- MCP server tests using mock stdio transport
