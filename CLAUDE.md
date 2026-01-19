# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ptk (Photo Toolkit) is a CLI tool for managing personal photo libraries with AI-powered organization and semantic search. Part of the longecho personal archive ecosystem.

**Current Status:** Core features complete — import, organization, AI annotation, multi-provider support, path management.

## Architecture

- **SQLite-backed** metadata storage (ptk.db)
- **CLI-first** using Typer + Rich
- **SHA256 deduplication** — photos identified by content hash
- **Multi-provider AI** — Ollama (local), OpenAI, Anthropic, Claude Code skill

### Package Structure

```
ptk/
├── cli.py              # Main CLI entry point (all commands)
├── core/               # Utilities: config, hasher, exif, thumbnails, constants
├── db/                 # SQLAlchemy models and session management
├── importers/          # Import sources (filesystem, google_takeout, apple_photos)
├── services/           # Business logic (import_service)
├── ai/                 # AI providers and annotations
│   ├── provider.py     # VisionProvider ABC and factory
│   ├── ollama.py       # Ollama provider
│   ├── openai_provider.py
│   ├── anthropic_provider.py
│   └── annotations.py  # Annotation profiles
├── skills/             # Claude Code skill installer
│   ├── installer.py
│   └── templates/      # SKILL.md, reference.md
├── query/              # Query builder and executor
└── views/              # View management for structured annotations
```

### Core Data Model

- `Photo` — Central entity: id (SHA256), original_path, EXIF metadata, caption, annotations
- `Tag`, `Album` — Organization (many-to-many with Photo)
- `Face`, `Person`, `Event` — Future face clustering support

## Development Commands

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run CLI
ptk --help
ptk init                    # Initialize library in current directory
ptk import ~/Pictures       # Import photos
ptk query                   # Query photos (alias: ptk q)
ptk show <id>               # Show photo details
ptk stats                   # Library statistics

# Organization
ptk set <id> --tag beach --favorite --caption "..."
ptk set <id> --album "Summer 2024"

# Query with filters
ptk q --favorite
ptk q --tag beach --tag sunset
ptk q --uncaptioned --limit 10
ptk q --format paths        # For scripting: id|path pairs
ptk q --offset 20 --limit 10

# AI (requires Ollama or API keys)
ptk ai status               # Check provider
ptk ai describe <id>        # Describe photo
ptk ai ask <id> "question"  # Ask about photo
ptk ai profiles             # List annotation profiles
ptk ai annotate <id> --profile family
ptk ai batch --profile quick -n 10

# Claude Code skill
ptk claude install          # Install as Claude Code skill
ptk claude status
ptk claude uninstall

# Path management
ptk verify                  # Check which photos are missing
ptk relocate /old /new      # Bulk update path prefixes
ptk rescan ~/new/location   # Find moved photos by hash

# Testing
pytest                      # Run all tests
pytest -v -k "test_query"   # Run specific tests
pytest --cov=ptk            # With coverage

# Linting
ruff check ptk tests
ruff format ptk tests
```

## Key Patterns

1. **Session Scope**: Always use `with session_scope() as session:` for transactions
2. **Photo Identity**: SHA256 hash is the primary key — content-based deduplication
3. **Provider ABC**: `VisionProvider` defines interface for AI providers
4. **Lazy Loading**: AI models only loaded when needed
5. **Path Resilience**: Photos can be found by hash even if moved

## AI Provider System

```python
from ptk.ai import get_provider

# Factory returns appropriate provider
provider = get_provider("ollama")  # or "openai", "anthropic"
provider.describe(image_path)
provider.ask(image_path, "How many people?")
```

Providers implement `VisionProvider` ABC with methods:
- `is_available()` — Check if provider is ready
- `describe(path)` — Generate caption
- `ask(path, question)` — Answer question about image
- `annotate(path, profile)` — Structured annotation

## Claude Code Skill

When `ptk claude install` is run, skill files are copied to `~/.claude/skills/ptk/`:
- `SKILL.md` — Teaches Claude how to use ptk
- `reference.md` — Command documentation

Claude can then directly read images and use ptk commands.

## Dependencies

### Core
- typer, rich (CLI)
- sqlalchemy (database)
- pillow (images)
- exifread (EXIF metadata)

### Optional
- `pip install ptk[ai]` — openai, anthropic SDKs
- `pip install ptk[faces]` — face_recognition, scikit-learn
- `pip install ptk[all]` — all optional features

## Testing

222 tests covering:
- Unit tests for hasher, models, importers, query builder, providers
- Integration tests for CLI commands, import flows, AI annotation

```bash
pytest tests/unit/          # Fast unit tests
pytest tests/integration/   # Integration tests
```

## longecho Ecosystem

ptk exports to the unified artifact format consumed by longecho. Related tools:
- ctk (conversations)
- btk (bookmarks)
- ebk (ebooks)
- stk (static sites)
- mtk (mail)
