---
name: ptk-photo-toolkit
description: Manage and annotate photo libraries with ptk. Use when working with photos, describing images, categorizing pictures, analyzing family photos, or when the user mentions ptk, photo library, image annotation, or photo organization.
allowed-tools: Read, Bash(ptk:*), Bash(python:*)
---

# ptk Photo Toolkit

You can help users manage their photo library with ptk (Photo Toolkit).

## Quick Start

```bash
# Check library status
ptk stats

# Query photos
ptk q                          # list all photos
ptk q --favorite               # favorites only
ptk q --tag beach              # photos tagged "beach"
ptk q --format json            # JSON output for scripting

# Show photo details
ptk show <photo-id>
```

## Viewing Photo Contents

To see what an image contains, you need to:

1. **Get the photo path** from ptk:
```bash
ptk show <photo-id> --format json
```

2. **Use the Read tool** on the image path - you can see images directly since you're multimodal.

3. **Describe or analyze** what you see in the image.

## Common Workflows

### Describe a single photo

1. Get the photo info:
   ```bash
   ptk show abc123 --format json
   ```
2. Read the image file at the `original_path`
3. Describe what you observe
4. Optionally save your description:
   ```bash
   ptk set abc123 --caption "Your description here"
   ```

### Bulk describe photos

1. Query photos that need descriptions:
   ```bash
   ptk q --format json --limit 10
   ```
2. For each photo:
   - Read the image at its `original_path`
   - Generate a description
   - Save with `ptk set <id> --caption "..."`

### Tag photos by content

1. Query untagged photos:
   ```bash
   ptk q --format json
   ```
2. For each photo:
   - Read the image
   - Identify appropriate tags (beach, family, landscape, etc.)
   - Apply tags:
     ```bash
     ptk set abc123 --tag beach --tag sunset --tag vacation
     ```

### Find photos by criteria

```bash
# Photos from 2023
ptk q --sql "SELECT * FROM photos WHERE strftime('%Y', date_taken) = '2023'"

# Photos with location data
ptk q --sql "SELECT * FROM photos WHERE latitude IS NOT NULL"

# Favorites with specific tag
ptk q --favorite --tag family
```

## Command Reference

See [reference.md](reference.md) for full command documentation.

## Important Notes

- Photo IDs are SHA256 hashes - use partial IDs (first 8+ chars) for convenience
- Always use `--format json` when you need to process output programmatically
- The library must be initialized (`ptk init`) in the working directory
- Changes are saved to the SQLite database automatically
