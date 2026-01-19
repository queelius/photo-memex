# ptk SQL Schema Reference

This document describes the SQLite schema for power users and LLMs querying the ptk database directly via `ptk q --sql`.

## Quick Examples

```sql
-- All photos from the 1980s with children
SELECT p.id, p.filename, va_decade.value_json as decade
FROM photos p
JOIN view_annotations va_decade ON p.id = va_decade.photo_id
  AND va_decade.view_name = 'family_v1'
  AND va_decade.field_name = 'decade'
JOIN view_annotations va_child ON p.id = va_child.photo_id
  AND va_child.view_name = 'family_v1'
  AND va_child.field_name = 'has_children'
WHERE va_decade.value_json = '"1980s"'
  AND va_child.value_json = 'true';

-- Photos by year
SELECT strftime('%Y', date_taken) as year, COUNT(*) as count
FROM photos
WHERE date_taken IS NOT NULL
GROUP BY year ORDER BY year;

-- Photos with specific tag
SELECT p.* FROM photos p
JOIN photo_tags pt ON p.id = pt.photo_id
JOIN tags t ON pt.tag_id = t.id
WHERE t.name = 'beach';

-- Search captions
SELECT id, filename, caption FROM photos
WHERE caption LIKE '%sunset%';
```

## Core Tables

### photos

The central entity. Photos are identified by SHA256 content hash.

| Column | Type | Description |
|--------|------|-------------|
| `id` | STRING(64) | SHA256 hash (primary key) |
| `original_path` | STRING(4096) | Full file path |
| `filename` | STRING(512) | Filename only |
| `file_size` | INTEGER | Size in bytes |
| `mime_type` | STRING(64) | e.g., "image/jpeg" |
| `width` | INTEGER | Image width in pixels |
| `height` | INTEGER | Image height in pixels |
| `date_taken` | DATETIME | From EXIF (indexed) |
| `date_imported` | DATETIME | Import timestamp |
| `date_modified` | DATETIME | Last modified |
| `camera_make` | STRING(128) | e.g., "Canon" |
| `camera_model` | STRING(128) | e.g., "EOS 5D Mark IV" |
| `lens` | STRING(128) | Lens info |
| `focal_length` | FLOAT | Focal length in mm |
| `aperture` | FLOAT | f-stop |
| `shutter_speed` | STRING(32) | e.g., "1/250" |
| `iso` | INTEGER | ISO value |
| `latitude` | FLOAT | GPS latitude (indexed) |
| `longitude` | FLOAT | GPS longitude (indexed) |
| `altitude` | FLOAT | GPS altitude |
| `location_name` | STRING(512) | Reverse geocoded name |
| `country` | STRING(128) | Country |
| `city` | STRING(256) | City |
| `caption` | TEXT | AI-generated caption |
| `objects` | JSON | Detected objects |
| `scene` | STRING(128) | Scene type |
| `is_favorite` | BOOLEAN | Favorite flag (indexed) |
| `is_hidden` | BOOLEAN | Hidden flag |
| `is_screenshot` | BOOLEAN | Screenshot detection |
| `is_video` | BOOLEAN | Video file |
| `import_source` | STRING(64) | e.g., "filesystem", "google_takeout" |

### tags

User-defined tags.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `name` | STRING(256) | Tag name (unique, indexed) |
| `color` | STRING(7) | Optional hex color |

### photo_tags

Junction table: photos ↔ tags (many-to-many).

| Column | Type | Description |
|--------|------|-------------|
| `photo_id` | STRING(64) | FK → photos.id |
| `tag_id` | INTEGER | FK → tags.id |

### albums

User-created albums.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `name` | STRING(256) | Album name (indexed) |
| `description` | TEXT | Optional description |
| `cover_photo_id` | STRING(64) | FK → photos.id |
| `created_at` | DATETIME | Creation time |
| `updated_at` | DATETIME | Last modified |

### photo_albums

Junction table: photos ↔ albums (many-to-many).

| Column | Type | Description |
|--------|------|-------------|
| `photo_id` | STRING(64) | FK → photos.id |
| `album_id` | INTEGER | FK → albums.id |
| `sort_order` | INTEGER | Order within album |

## View System Tables

### views

Materialized computations over photos.

| Column | Type | Description |
|--------|------|-------------|
| `name` | STRING(128) | View name (primary key) |
| `version` | INTEGER | Version number |
| `description` | TEXT | Description |
| `definition_yaml` | TEXT | Full YAML definition |
| `profile_name` | STRING(128) | Profile used |
| `model` | STRING(128) | AI model |
| `model_host` | STRING(256) | Ollama host |
| `status` | STRING(32) | draft/computing/complete/partial/stale/error |
| `photo_count` | INTEGER | Photos processed |
| `annotation_count` | INTEGER | Total annotations |
| `created_at` | DATETIME | Creation time |
| `computed_at` | DATETIME | Last computation |

### view_annotations

Per-photo annotation values from views.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `photo_id` | STRING(64) | FK → photos.id |
| `view_name` | STRING(128) | FK → views.name |
| `field_name` | STRING(128) | Field name (e.g., "decade") |
| `field_type` | STRING(32) | Type (string/integer/boolean/enum/list) |
| `value_json` | TEXT | JSON-encoded value |
| `raw_response` | TEXT | LLM's original response |
| `confidence` | FLOAT | Optional confidence score |
| `created_at` | DATETIME | Annotation time |

**Key Index:** `(photo_id, view_name, field_name)` is unique.

## Face Recognition Tables

### faces

Detected faces in photos.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `photo_id` | STRING(64) | FK → photos.id |
| `person_id` | INTEGER | FK → people.id (nullable) |
| `bbox_x` | FLOAT | Bounding box X (0-1) |
| `bbox_y` | FLOAT | Bounding box Y (0-1) |
| `bbox_width` | FLOAT | Bounding box width (0-1) |
| `bbox_height` | FLOAT | Bounding box height (0-1) |
| `confidence` | FLOAT | Detection confidence |
| `embedding` | BLOB | Face embedding vector |
| `cluster_id` | INTEGER | Pre-naming cluster ID |

### people

Named individuals (linked to faces).

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `name` | STRING(256) | Person name (unique) |
| `relationship_type` | STRING(64) | e.g., "family", "friend" |
| `notes` | TEXT | Notes |
| `representative_embedding` | BLOB | Average face embedding |
| `created_at` | DATETIME | Creation time |

### events

Auto-detected or manual events.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `name` | STRING(256) | Event name |
| `description` | TEXT | Description |
| `start_date` | DATETIME | Start date |
| `end_date` | DATETIME | End date |
| `latitude` | FLOAT | Location centroid |
| `longitude` | FLOAT | Location centroid |
| `location_name` | STRING(512) | Location name |
| `is_auto_detected` | BOOLEAN | Auto vs manual |

### photo_events

Junction table: photos ↔ events (many-to-many).

| Column | Type | Description |
|--------|------|-------------|
| `photo_id` | STRING(64) | FK → photos.id |
| `event_id` | INTEGER | FK → events.id |

## Common Query Patterns

### Filter by view annotation

```sql
-- Photos where decade = "1980s" in family_v1 view
SELECT p.* FROM photos p
JOIN view_annotations va ON p.id = va.photo_id
WHERE va.view_name = 'family_v1'
  AND va.field_name = 'decade'
  AND va.value_json = '"1980s"';
```

**Important:** String values in `value_json` are JSON-encoded, so `"1980s"` becomes `'"1980s"'` (with quotes).

### Numeric comparisons

```sql
-- Photos with 3+ people
SELECT p.* FROM photos p
JOIN view_annotations va ON p.id = va.photo_id
WHERE va.view_name = 'family_v1'
  AND va.field_name = 'people_count'
  AND CAST(json_extract(va.value_json, '$') AS INTEGER) >= 3;
```

### Boolean fields

```sql
-- Photos with children
SELECT p.* FROM photos p
JOIN view_annotations va ON p.id = va.photo_id
WHERE va.view_name = 'family_v1'
  AND va.field_name = 'has_children'
  AND va.value_json = 'true';
```

### Multiple tags (AND)

```sql
-- Photos tagged BOTH "beach" AND "sunset"
SELECT p.* FROM photos p
JOIN photo_tags pt1 ON p.id = pt1.photo_id
JOIN tags t1 ON pt1.tag_id = t1.id AND t1.name = 'beach'
JOIN photo_tags pt2 ON p.id = pt2.photo_id
JOIN tags t2 ON pt2.tag_id = t2.id AND t2.name = 'sunset';
```

### Multiple tags (OR)

```sql
-- Photos tagged "beach" OR "sunset"
SELECT DISTINCT p.* FROM photos p
JOIN photo_tags pt ON p.id = pt.photo_id
JOIN tags t ON pt.tag_id = t.id
WHERE t.name IN ('beach', 'sunset');
```

### Timeline queries

```sql
-- Photos by year
SELECT strftime('%Y', date_taken) as year, COUNT(*) as count
FROM photos
WHERE date_taken IS NOT NULL
GROUP BY year ORDER BY year;

-- Photos from specific month
SELECT * FROM photos
WHERE strftime('%Y-%m', date_taken) = '2023-07'
ORDER BY date_taken;
```

### Location queries

```sql
-- Photos with GPS data
SELECT * FROM photos
WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

-- Photos near a location (approximate)
SELECT *,
  ABS(latitude - 40.7128) + ABS(longitude - -74.0060) as dist
FROM photos
WHERE latitude IS NOT NULL
ORDER BY dist
LIMIT 20;
```

### View statistics

```sql
-- Annotation coverage by field
SELECT field_name, COUNT(*) as count
FROM view_annotations
WHERE view_name = 'family_v1'
GROUP BY field_name;

-- Most common decade values
SELECT value_json, COUNT(*) as count
FROM view_annotations
WHERE view_name = 'family_v1' AND field_name = 'decade'
GROUP BY value_json ORDER BY count DESC;
```

### Face queries

```sql
-- Photos of a specific person
SELECT p.* FROM photos p
JOIN faces f ON p.id = f.photo_id
JOIN people pe ON f.person_id = pe.id
WHERE pe.name = 'Mom';

-- Photos with multiple faces
SELECT p.id, p.filename, COUNT(f.id) as face_count
FROM photos p
JOIN faces f ON p.id = f.photo_id
GROUP BY p.id
HAVING face_count > 1;
```

## Using with ptk

```bash
# Run any SQL query
ptk q --sql "SELECT * FROM photos WHERE is_favorite = 1"

# Output as JSON for scripting
ptk q --sql "SELECT id, filename FROM photos LIMIT 10" --format json

# Just get IDs for piping
ptk q --sql "SELECT id FROM photos WHERE caption LIKE '%beach%'" --format ids

# Count results
ptk q --sql "SELECT id FROM photos WHERE date_taken > '2020-01-01'" --format count
```
