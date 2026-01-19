# ptk Command Reference

## Core Commands

### `ptk init [PATH]`
Initialize a new photo library in the specified directory (default: current directory).

```bash
ptk init                 # Initialize in current directory
ptk init ~/Photos        # Initialize in specific directory
ptk init --force         # Overwrite existing library
```

### `ptk stats`
Show library statistics.

```bash
ptk stats
# Output:
# Total photos: 1234
# Favorites: 56
# Tagged: 789
# ...
```

### `ptk import <PATH> [OPTIONS]`
Import photos from a directory or export archive.

```bash
ptk import ~/Pictures                     # Auto-detect source type
ptk import ~/Takeout --source google      # Google Takeout export
ptk import ~/Export --source apple        # Apple Photos export
ptk import ~/Pictures --dry-run           # Preview without importing
```

## Query Commands

### `ptk q [OPTIONS]`
Query photos with various filters. Alias for `ptk query`.

**Filter Options:**
```bash
ptk q                              # All photos
ptk q --favorite                   # Favorites only
ptk q --tag beach                  # Photos with tag
ptk q --tag beach --tag sunset     # Photos with ALL tags (AND)
ptk q --album "Summer 2020"        # Photos in album
ptk q --view family_v1             # Photos with view annotations
ptk q --field decade=1980s         # Filter by annotation field
ptk q --field people_count>2       # Numeric comparison
```

**Output Formats:**
```bash
ptk q --format table    # Human-readable table (default)
ptk q --format json     # JSON array
ptk q --format ids      # One ID per line
ptk q --format count    # Just the count
```

**SQL Mode:**
```bash
ptk q --sql "SELECT * FROM photos WHERE filename LIKE '%vacation%'"
ptk q --sql "SELECT p.*, t.name as tag FROM photos p JOIN photo_tags pt ON p.id = pt.photo_id JOIN tags t ON pt.tag_id = t.id"
```

**Pagination:**
```bash
ptk q --limit 10          # First 10 results
ptk q --limit 10 --offset 20   # Skip first 20, return next 10
```

### `ptk show <PHOTO_ID>`
Show detailed information about a photo.

```bash
ptk show abc123def456
ptk show abc123         # Partial ID works if unique
ptk show abc123 --format json   # JSON output
```

**Output includes:**
- Photo ID and filename
- Original path and file size
- Date taken and imported
- EXIF metadata (camera, dimensions, etc.)
- Tags, albums, and annotations
- Favorite status

## Modification Commands

### `ptk set <PHOTO_IDS> [OPTIONS]`
Modify photo metadata. Accepts one or more photo IDs.

**Tags:**
```bash
ptk set abc123 --tag beach --tag sunset   # Add tags
ptk set abc123 --untag vacation           # Remove tag
```

**Favorites:**
```bash
ptk set abc123 --favorite                 # Mark as favorite
ptk set abc123 --no-favorite              # Remove favorite
```

**Albums:**
```bash
ptk set abc123 --album "Summer 2020"      # Add to album
```

**Captions:**
```bash
ptk set abc123 --caption "Beach at sunset with friends"
```

**Bulk operations (pipe IDs):**
```bash
ptk q --tag beach --format ids | xargs ptk set --tag vacation
```

## AI Commands

### `ptk ai status`
Check AI provider availability.

### `ptk ai describe <PHOTO_ID>`
Generate AI description for a photo using configured provider.

### `ptk ai ask <PHOTO_ID> "<QUESTION>"`
Ask a question about a photo.

```bash
ptk ai ask abc123 "How many people are in this photo?"
```

## Claude Code Skill Commands

### `ptk claude install`
Install the ptk skill for Claude Code.

### `ptk claude uninstall`
Remove the ptk skill.

### `ptk claude status`
Check if skill is installed.

### `ptk claude show`
Display the installed skill content.

## Database Schema

The SQLite database (`ptk.db`) contains these main tables:

- `photos` - Core photo metadata
- `tags` - Tag definitions
- `photo_tags` - Photo-tag relationships
- `albums` - Album definitions
- `photo_albums` - Photo-album relationships
- `view_annotations` - AI-generated annotations

**Key photo columns:**
- `id` - SHA256 hash (primary key)
- `original_path` - Path to image file
- `filename` - Original filename
- `date_taken` - EXIF date taken
- `is_favorite` - Boolean favorite flag
- `caption` - User/AI description
- `latitude`, `longitude` - GPS coordinates
