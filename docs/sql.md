# photo-memex SQL Schema Reference

SQL reference for querying the photo library directly via `ptk q --sql` or the MCP `run_sql` tool.

## Quick examples

```sql
-- Photos by year
SELECT strftime('%Y', date_taken) as year, COUNT(*) as count
FROM photos WHERE date_taken IS NOT NULL
GROUP BY year ORDER BY year;

-- Photos with specific tag
SELECT p.* FROM photos p
JOIN photo_tags pt ON p.id = pt.photo_id
JOIN tags t ON pt.tag_id = t.id
WHERE t.name = 'beach';

-- Search captions
SELECT id, filename, caption FROM photos
WHERE caption LIKE '%sunset%';

-- Photos of a specific person
SELECT p.* FROM photos p
JOIN faces f ON p.id = f.photo_id
JOIN people pe ON f.person_id = pe.id
WHERE pe.name = 'Mom';
```

## Core tables

### photos

The central entity. Photos are identified by SHA256 content hash.

| Column | Type | Notes |
|--------|------|-------|
| `id` | STRING(64) | SHA256 hash (primary key) |
| `original_path` | STRING(4096) | Full file path |
| `filename` | STRING(512) | Filename only |
| `file_size` | INTEGER | Size in bytes |
| `mime_type` | STRING(64) | e.g., "image/jpeg" |
| `width` | INTEGER | Nullable |
| `height` | INTEGER | Nullable |
| `date_taken` | DATETIME | From EXIF (indexed) |
| `date_imported` | DATETIME | Import timestamp |
| `date_modified` | DATETIME | Nullable |
| `camera_make` | STRING(128) | EXIF |
| `camera_model` | STRING(128) | EXIF |
| `lens` | STRING(128) | EXIF |
| `focal_length` | FLOAT | mm |
| `aperture` | FLOAT | f-stop |
| `shutter_speed` | STRING(32) | e.g., "1/250" |
| `iso` | INTEGER | |
| `latitude` | FLOAT | GPS (indexed) |
| `longitude` | FLOAT | GPS (indexed) |
| `altitude` | FLOAT | GPS |
| `location_name` | STRING(512) | Reverse geocoded |
| `country` | STRING(128) | |
| `city` | STRING(256) | |
| `caption` | TEXT | AI-generated or manual |
| `objects` | JSON | Detected objects |
| `scene` | STRING(128) | Scene classification |
| `ai_analyzed_at` | DATETIME | When AI last annotated |
| `ai_model` | STRING(128) | Which model annotated |
| `is_favorite` | BOOLEAN | (indexed) |
| `is_hidden` | BOOLEAN | |
| `is_screenshot` | BOOLEAN | |
| `is_video` | BOOLEAN | |
| `duration_seconds` | FLOAT | Video duration |
| `thumbnail_data` | BLOB | Stored thumbnail |
| `thumbnail_mime` | STRING(32) | |
| `import_source` | STRING(64) | e.g., "filesystem", "google_takeout" |
| `source_metadata` | JSON | Source-specific data |
| `archived_at` | DATETIME | Soft delete timestamp (NULL = active) |

Composite indexes: `(date_taken, latitude, longitude)`, `(camera_make, camera_model)`.

Default queries filter `WHERE archived_at IS NULL`.

### tags

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER | Primary key |
| `name` | STRING(256) | Unique, indexed |
| `color` | STRING(7) | Optional hex color |
| `archived_at` | DATETIME | Soft delete |

### albums

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER | Primary key |
| `name` | STRING(256) | Unique, indexed |
| `description` | TEXT | |
| `cover_photo_id` | STRING(64) | FK to photos.id |
| `created_at` | DATETIME | |
| `updated_at` | DATETIME | |
| `archived_at` | DATETIME | Soft delete |

### people

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER | Primary key |
| `name` | STRING(256) | Unique, indexed |
| `notes` | TEXT | |
| `created_at` | DATETIME | |
| `archived_at` | DATETIME | Soft delete |

### faces

Links a person to a photo. Manual identification uses `bbox=(0,0,1,1)` and `confidence=0.0`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER | Primary key |
| `photo_id` | STRING(64) | FK to photos.id |
| `person_id` | INTEGER | FK to people.id (nullable) |
| `bbox_x` | FLOAT | Normalized 0-1 |
| `bbox_y` | FLOAT | Normalized 0-1 |
| `bbox_width` | FLOAT | Normalized 0-1 |
| `bbox_height` | FLOAT | Normalized 0-1 |
| `confidence` | FLOAT | 0.0 = manual identification |
| `archived_at` | DATETIME | Soft delete |

### events

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER | Primary key |
| `name` | STRING(256) | Unique, indexed |
| `description` | TEXT | |
| `start_date` | DATETIME | Auto-set from photos |
| `end_date` | DATETIME | Auto-set from photos |
| `latitude` | FLOAT | Location centroid |
| `longitude` | FLOAT | Location centroid |
| `location_name` | STRING(512) | |
| `is_auto_detected` | BOOLEAN | |
| `archived_at` | DATETIME | Soft delete |

### marginalia

Free-form notes attachable to any photo. Survives photo deletion (`ON DELETE SET NULL`).

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER | Primary key |
| `photo_id` | STRING(64) | FK to photos.id (nullable, orphans survive) |
| `body` | TEXT | Note content |
| `created_at` | DATETIME | |
| `updated_at` | DATETIME | |
| `archived_at` | DATETIME | Soft delete |

### photos_fts (FTS5)

Full-text search over captions and location names. Synced by triggers on `photos`.

```sql
SELECT id FROM photos_fts WHERE photos_fts MATCH 'sunset';
```

### Junction tables

- `photo_tags` (`photo_id`, `tag_id`)
- `photo_albums` (`photo_id`, `album_id`, `sort_order`)
- `photo_events` (`photo_id`, `event_id`)

All have indexes on both foreign key columns. All use `ON DELETE CASCADE`.

## Common query patterns

### Tags

```sql
-- Photos with tag "beach"
SELECT p.* FROM photos p
JOIN photo_tags pt ON p.id = pt.photo_id
JOIN tags t ON pt.tag_id = t.id
WHERE t.name = 'beach';

-- Photos tagged BOTH "beach" AND "sunset" (one JOIN pair per tag)
SELECT p.* FROM photos p
JOIN photo_tags pt1 ON p.id = pt1.photo_id
JOIN tags t1 ON pt1.tag_id = t1.id AND t1.name = 'beach'
JOIN photo_tags pt2 ON p.id = pt2.photo_id
JOIN tags t2 ON pt2.tag_id = t2.id AND t2.name = 'sunset';

-- Photos tagged "beach" OR "sunset"
SELECT DISTINCT p.* FROM photos p
JOIN photo_tags pt ON p.id = pt.photo_id
JOIN tags t ON pt.tag_id = t.id
WHERE t.name IN ('beach', 'sunset');
```

### Timeline

```sql
-- Photos by year
SELECT strftime('%Y', date_taken) as year, COUNT(*) as count
FROM photos WHERE date_taken IS NOT NULL
GROUP BY year ORDER BY year;

-- Photos from a specific month
SELECT * FROM photos
WHERE strftime('%Y-%m', date_taken) = '2023-07'
ORDER BY date_taken;
```

### Location

```sql
-- Photos with GPS data
SELECT * FROM photos
WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

-- Photos near a location (Manhattan distance approximation)
SELECT *, ABS(latitude - 40.7128) + ABS(longitude - (-74.0060)) as dist
FROM photos WHERE latitude IS NOT NULL
ORDER BY dist LIMIT 20;
```

### People

```sql
-- Photos of a specific person
SELECT p.* FROM photos p
JOIN faces f ON p.id = f.photo_id
JOIN people pe ON f.person_id = pe.id
WHERE pe.name = 'Mom';

-- Photos with multiple people tagged
SELECT p.id, p.filename, COUNT(f.id) as face_count
FROM photos p
JOIN faces f ON p.id = f.photo_id
WHERE f.person_id IS NOT NULL
GROUP BY p.id HAVING face_count > 1;
```

### Events

```sql
-- Photos in an event
SELECT p.* FROM photos p
JOIN photo_events pe ON p.id = pe.photo_id
JOIN events e ON pe.event_id = e.id
WHERE e.name = 'Beach vacation 2024';
```

## Using via CLI or MCP

```bash
# CLI
ptk q --sql "SELECT * FROM photos WHERE is_favorite = 1"
ptk q --sql "SELECT id, filename FROM photos LIMIT 10" --format json
```

Via MCP `run_sql` tool: same SQL, returned as JSON array of dicts. Only SELECT statements allowed.
