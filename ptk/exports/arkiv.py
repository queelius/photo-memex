"""Export library to arkiv format (JSONL + README.md + schema.yaml)."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import joinedload

from ptk import __version__
from ptk.db.models import Photo
from ptk.db.session import session_scope


# Metadata fields to extract from Photo, with their attribute names.
# Optional fields are only included when non-None and non-empty.
_OPTIONAL_METADATA_FIELDS = [
    "filename",
    "file_size",
    "width",
    "height",
    "caption",
    "scene",
    "is_favorite",
    "is_screenshot",
    "is_video",
    "camera_make",
    "camera_model",
    "lens",
    "shutter_speed",
    "location_name",
    "country",
    "city",
    "import_source",
    "focal_length",
    "aperture",
    "iso",
    "latitude",
    "longitude",
    "altitude",
]


def _photo_to_record(photo: Photo) -> dict[str, Any]:
    """Convert a Photo model instance to an arkiv record dict."""
    metadata: dict[str, Any] = {"sha256": photo.id}

    # Add optional scalar fields, omitting None and False booleans
    for field in _OPTIONAL_METADATA_FIELDS:
        value = getattr(photo, field)
        if value is None:
            continue
        # Omit False for boolean flags (only include when True)
        if isinstance(value, bool) and not value:
            continue
        metadata[field] = value

    # Tags (sorted, omit if empty)
    if photo.tags:
        metadata["tags"] = sorted(t.name for t in photo.tags)

    # Albums (sorted, omit if empty)
    if photo.albums:
        metadata["albums"] = sorted(a.name for a in photo.albums)

    record: dict[str, Any] = {
        "mimetype": photo.mime_type,
        "uri": Path(photo.original_path).as_uri(),
        "metadata": metadata,
    }

    if photo.date_taken is not None:
        record["timestamp"] = photo.date_taken.isoformat()

    return record


def _infer_type(value: Any) -> str:
    """Infer a simple type string for a metadata value."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    return "string"


def _build_schema(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a schema.yaml structure by scanning all records."""
    metadata_keys: dict[str, str] = {}

    for record in records:
        for key, value in record.get("metadata", {}).items():
            if key not in metadata_keys:
                metadata_keys[key] = _infer_type(value)

    return {
        "photos": {
            "format": "jsonl",
            "file": "photos.jsonl",
            "metadata_keys": dict(sorted(metadata_keys.items())),
        }
    }


def export_arkiv(output_dir: Path, title: str | None = None) -> int:
    """Export the entire photo library to arkiv format.

    Creates:
        - photos.jsonl: One JSON record per photo
        - README.md: YAML frontmatter with metadata
        - schema.yaml: Describes the structure and metadata keys

    Args:
        output_dir: Directory to write output files to (created if needed).
        title: Optional archive title for README.

    Returns:
        Number of photos exported.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Query all photos with eager-loaded relationships
    with session_scope() as session:
        photos = (
            session.query(Photo)
            .options(joinedload(Photo.tags), joinedload(Photo.albums))
            .all()
        )

        records = [_photo_to_record(photo) for photo in photos]

    count = len(records)

    # Write photos.jsonl
    jsonl_path = output_dir / "photos.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    # Write README.md
    now = datetime.now(timezone.utc)
    archive_name = title or "ptk photo library"
    frontmatter = {
        "name": archive_name,
        "description": f"Photo library exported from ptk ({count} photos)",
        "datetime": now.isoformat(),
        "generator": f"ptk {__version__}",
        "contents": [
            {
                "path": "photos.jsonl",
                "description": "Photo metadata records",
            }
        ],
    }

    readme_path = output_dir / "README.md"
    with readme_path.open("w", encoding="utf-8") as f:
        f.write("---\n")
        f.write(yaml.dump(frontmatter, default_flow_style=False, sort_keys=False))
        f.write("---\n")

    # Write schema.yaml
    schema = _build_schema(records)
    schema_path = output_dir / "schema.yaml"
    with schema_path.open("w", encoding="utf-8") as f:
        yaml.dump(schema, f, default_flow_style=False, sort_keys=False)

    return count
