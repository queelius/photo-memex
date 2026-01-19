# ptk — Photo Toolkit

A CLI tool for managing personal photo libraries with AI-powered organization and semantic search. Your photos identified by content hash, never duplicated, always findable.

## Features

- **SHA256 deduplication** — Photos identified by content, import the same photo twice and it's deduplicated
- **Multi-source import** — Local directories, Google Takeout, Apple Photos exports
- **Flexible organization** — Tags, albums, favorites, timeline browsing
- **AI annotation** — Describe photos, ask questions, batch annotate with multiple providers
- **Claude Code integration** — Install as a skill for direct photo analysis
- **Path resilience** — Move your photos, then rescan to find them by content hash
- **SQLite-backed** — Portable, queryable, no server needed

## Installation

```bash
pip install ptk-photo

# Or with optional features
pip install ptk-photo[ai]        # AI providers (OpenAI, Anthropic)
pip install ptk-photo[faces]     # Face detection/clustering
pip install ptk-photo[all]       # Everything
```

## Quick Start

```bash
# Initialize a library
cd ~/Pictures
ptk init

# Import photos
ptk import .                      # Current directory
ptk import ~/Photos --recursive   # Recursive import
ptk import takeout.zip --source google  # Google Takeout

# Query photos
ptk query                         # All photos
ptk query --favorite              # Favorites
ptk query --tag vacation          # By tag
ptk query --uncaptioned -n 10     # Photos without captions
ptk query --format paths          # Output id|path pairs

# Organize
ptk set abc123 --tag beach --favorite
ptk set abc123 --album "Summer 2024"
ptk set abc123 --caption "Sunset at the pier"

# AI annotation (requires Ollama or API keys)
ptk ai status                     # Check provider
ptk ai describe abc123            # Describe a photo
ptk ai ask abc123 "How many people are in this photo?"

# Path management (if you move your photos)
ptk verify                        # Check which photos are missing
ptk relocate /old/path /new/path  # Bulk update paths
ptk rescan ~/new/location         # Find moved photos by hash
```

## CLI Reference

ptk has a minimal CLI with essential commands:

| Command | Purpose |
|---------|---------|
| `ptk init` | Initialize library in current directory |
| `ptk import` | Import photos from directory or archive |
| `ptk query` | Query photos with filters (alias: `ptk q`) |
| `ptk show` | Show photo details and annotations |
| `ptk set` | Modify photo metadata (tags, albums, caption) |
| `ptk stats` | Library statistics |
| `ptk ai` | AI commands (status, describe, ask, annotate, batch) |
| `ptk view` | Manage annotation views |
| `ptk claude` | Claude Code skill management |
| `ptk verify` | Check photo paths exist |
| `ptk relocate` | Bulk update path prefixes |
| `ptk rescan` | Find moved photos by content hash |

### Query Examples

```bash
# Filters
ptk q --favorite                  # Favorites only
ptk q --tag beach --tag sunset    # Multiple tags (AND)
ptk q --album "Vacation 2024"     # By album
ptk q --uncaptioned               # Photos without captions

# Output formats
ptk q --format table              # Default table view
ptk q --format json               # JSON output
ptk q --format ids                # Just photo IDs
ptk q --format paths              # id|path pairs (for scripting)
ptk q --format count              # Just the count

# Pagination
ptk q --limit 20 --offset 40      # Page 3 of results

# Raw SQL
ptk q --sql "SELECT * FROM photos WHERE caption LIKE '%beach%'"
```

## AI Providers

ptk supports multiple AI vision providers:

| Provider | Setup | Best for |
|----------|-------|----------|
| **Ollama** | `ollama pull llava` | Local, private, free |
| **Claude Code** | `ptk claude install` | Direct integration with Claude |
| **OpenAI** | Set `OPENAI_API_KEY` | GPT-4o vision |
| **Anthropic** | Set `ANTHROPIC_API_KEY` | Claude vision API |

### Claude Code Integration

Install ptk as a Claude Code skill for direct photo analysis:

```bash
ptk claude install    # Install skill
ptk claude status     # Check installation
ptk claude uninstall  # Remove skill
```

Once installed, Claude Code can directly read and analyze your photos.

### Configuration

Create `ptk.yaml` in your library directory:

```yaml
ai:
  provider: ollama  # or openai, anthropic
  ollama:
    host: localhost
    port: 11434
    model: llava
  openai:
    api_key: ${OPENAI_API_KEY}
    model: gpt-4o
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
    model: claude-sonnet-4-20250514
```

## Path Resilience

Photos are identified by SHA256 content hash, not path. If you move your photos:

```bash
# 1. Check what's missing
ptk verify

# 2a. If you renamed a parent directory:
ptk relocate /old/path /new/path --verify

# 2b. If photos are scattered:
ptk rescan ~/Pictures --missing-only
```

## Data Model

```
Photo (identified by SHA256)
├── Metadata (EXIF, dimensions, dates)
├── Tags (many-to-many)
├── Albums (many-to-many)
├── Caption (AI-generated or manual)
└── View Annotations (structured AI analysis)
```

Original files are **never modified**. ptk stores only metadata in SQLite.

## Development

```bash
git clone https://github.com/YourUsername/ptk
cd ptk
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest

# With coverage
pytest --cov=ptk --cov-report=term-missing
```

## Part of longecho

ptk is a domain toolkit in the [longecho](https://github.com/YourUsername/longecho) personal archive ecosystem:

| Tool | Domain |
|------|--------|
| ctk | Conversations |
| btk | Bookmarks |
| ebk | Ebooks |
| stk | Static sites |
| **ptk** | **Photos** |
| mtk | Mail |

## License

MIT
