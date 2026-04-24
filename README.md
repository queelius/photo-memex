# photo-memex

Personal photo library archive with MCP server for AI annotation, and export to arkiv/HTML.

Part of the [`*-memex` ecosystem](../CLAUDE.md): llm-memex (conversations), mail-memex (email), bookmark-memex (bookmarks), book-memex (ebooks), photo-memex (photos), hugo-memex (site content).

## What it does

- **SHA256 deduplication**: photos identified by content hash, never duplicated, survive moves and renames.
- **Multi-source import**: local directories, Google Takeout, Apple Photos exports.
- **Organization**: tags (M2M), albums (M2M), favorites, events, person tagging.
- **MCP server**: 21 tools for querying and annotating photos. Claude Code sees your photos, writes captions, adds tags, identifies people.
- **Exports**: arkiv (JSONL + schema.yaml), single-file HTML gallery (sql.js).
- **Path resilience**: photos move on disk, `photo-memex rescan` finds them by content hash.

## Installation

```bash
pip install -e ".[dev,mcp]"
```

## Quick start

```bash
# Initialize a library
cd ~/Pictures
photo-memex init

# Import photos
photo-memex import .
photo-memex import ~/Photos --recursive
photo-memex import takeout.zip --source google

# Query
photo-memex query                         # all photos
photo-memex query --favorite              # favorites
photo-memex query --tag vacation          # by tag
photo-memex query --uncaptioned -n 10     # photos without captions
photo-memex query --format paths          # id|path pairs

# Organize
photo-memex set abc123 --tag beach --favorite
photo-memex set abc123 --album "Summer 2024"
photo-memex set abc123 --caption "Sunset at the pier"

# Path management
photo-memex verify                        # check which paths are missing
photo-memex relocate /old/path /new/path  # bulk update path prefixes
photo-memex rescan ~/new/location         # find moved photos by hash

# Export
photo-memex export arkiv -o my-photos/    # JSONL + schema.yaml
photo-memex export html -o gallery.html   # single-file browser

# MCP server (for Claude Code integration)
photo-memex mcp
```

## CLI reference

| Command | Purpose |
|---------|---------|
| `photo-memex init` | Initialize library in current directory |
| `photo-memex import PATH` | Import photos from directory or archive |
| `photo-memex query` / `photo-memex q` | Query photos with filters or SQL |
| `photo-memex show PHOTO_ID` | Show photo details |
| `photo-memex set PHOTO_ID` | Modify photo metadata (tags, albums, caption, favorite) |
| `photo-memex stats` | Library statistics |
| `photo-memex verify` | Check that photo paths exist on disk |
| `photo-memex relocate OLD NEW` | Bulk update path prefixes |
| `photo-memex rescan DIR` | Find moved photos by content hash |
| `photo-memex export arkiv` | Export to arkiv format (JSONL + schema.yaml) |
| `photo-memex export html` | Export as single-file HTML photo browser |
| `photo-memex mcp` | Launch MCP server (stdio) |

## MCP server

The MCP server exposes the photo library to Claude Code over stdio. Configure in your MCP client:

```json
{
  "mcpServers": {
    "photo-memex": {
      "command": "photo-memex",
      "args": ["mcp"],
      "env": {"PTK_LIBRARY": "/path/to/library"}
    }
  }
}
```

Claude Code can then query your library with SQL, view thumbnails, write captions, add tags, identify people, group photos into events, and batch-annotate.

## Data model

```
Photo (identified by SHA256 of file content)
+-- EXIF metadata (camera, lens, GPS, dates)
+-- Tags (many-to-many)
+-- Albums (many-to-many)
+-- Events (many-to-many)
+-- Faces / People (person tagging)
+-- Caption, scene (AI-generated or manual)
```

Original files are never modified. All metadata lives in SQLite (`photo-memex.db`).

## Development

```bash
pip install -e ".[dev,mcp]"
pytest                          # ~280 tests
pytest --cov=photo_memex                # with coverage
ruff check photo_memex tests            # lint
ruff format photo_memex tests           # format
```

## License

MIT
