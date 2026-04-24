"""Export library to arkiv bundle (directory / .zip / .tar.gz).

Output layout (all three bundle formats contain identical contents):

- ``records.jsonl`` : one JSON record per active photo and marginalia
- ``schema.yaml``   : archive self-description + per-kind counts
- ``README.md``     : arkiv ECHO frontmatter + human-readable explanation

Record URI scheme::

    photo-memex://photo/<sha256>
    photo-memex://marginalia/<id>

Only non-archived rows (``archived_at IS NULL``) are emitted.

Compression choice prioritises longevity: ``.zip`` and ``.tar.gz`` are
both ubiquitous on every OS (30+ years of universal tooling). Modern
compressors like ``zstd`` are deliberately avoided so the bundle still
opens in 2050.
"""

from __future__ import annotations

import io
import json
import tarfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml
from sqlalchemy.orm import joinedload

from ptk import __version__
from ptk.db.models import Marginalia, Photo
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


# ---------------------------------------------------------------------------
# Bundle format detection
# ---------------------------------------------------------------------------


def _detect_compression(path: str | Path) -> str:
    """Infer output format from *path*'s extension.

    Returns one of ``"zip"``, ``"tar.gz"``, ``"dir"``.
    """
    lower = str(path).lower()
    if lower.endswith(".zip"):
        return "zip"
    if lower.endswith(".tar.gz") or lower.endswith(".tgz"):
        return "tar.gz"
    return "dir"


# ---------------------------------------------------------------------------
# Record builders
# ---------------------------------------------------------------------------


def _photo_to_record(photo: Photo) -> dict[str, Any]:
    """Convert a Photo model instance to an arkiv record dict."""
    metadata: dict[str, Any] = {"sha256": photo.id}

    for field in _OPTIONAL_METADATA_FIELDS:
        value = getattr(photo, field)
        if value is None:
            continue
        if isinstance(value, bool) and not value:
            continue
        metadata[field] = value

    if photo.tags:
        metadata["tags"] = sorted(t.name for t in photo.tags)
    if photo.albums:
        metadata["albums"] = sorted(a.name for a in photo.albums)

    record: dict[str, Any] = {
        "kind": "photo",
        "uri": f"photo-memex://photo/{photo.id}",
        "source_path": Path(photo.original_path).as_uri(),
        "mimetype": photo.mime_type,
        "metadata": metadata,
    }

    if photo.date_taken is not None:
        record["timestamp"] = photo.date_taken.isoformat()

    return record


def _marginalia_to_record(m: Marginalia) -> dict[str, Any]:
    """Convert a Marginalia row to an arkiv record.

    The photo-memex marginalia model uses an autoincrement integer id.
    That's fine for a single-archive round-trip — we echo it in the
    URI — but it does mean a bundle imported into a *different* library
    gets a fresh id (see the importer for why that's OK for this
    archive: marginalia are small and the uniqueness invariant is
    "one note at a time," not "globally durable across archives").
    """
    record: dict[str, Any] = {
        "kind": "marginalia",
        "uri": f"photo-memex://marginalia/{m.id}",
        "mimetype": "text/plain",
        "metadata": {
            "id": m.id,
            "photo_uri": (
                f"photo-memex://photo/{m.photo_id}" if m.photo_id else None
            ),
            "body": m.body,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "updated_at": m.updated_at.isoformat() if m.updated_at else None,
        },
    }
    if m.created_at is not None:
        record["timestamp"] = m.created_at.isoformat()
    if m.body:
        record["content"] = m.body
    return record


# ---------------------------------------------------------------------------
# Schema introspection
# ---------------------------------------------------------------------------


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
    if isinstance(value, dict):
        return "object"
    return "string"


def _build_schema(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a schema.yaml structure with per-kind counts + field types."""
    counts: Dict[str, int] = {"photo": 0, "marginalia": 0}
    photo_keys: dict[str, str] = {}
    marginalia_keys: dict[str, str] = {}

    for rec in records:
        kind = rec.get("kind")
        if kind in counts:
            counts[kind] += 1
        meta = rec.get("metadata") or {}
        target = photo_keys if kind == "photo" else marginalia_keys if kind == "marginalia" else None
        if target is None:
            continue
        for key, value in meta.items():
            if key not in target:
                target[key] = _infer_type(value)

    return {
        "scheme": "photo-memex",
        "counts": counts,
        "kinds": {
            "photo": {
                "description": "A single photo with metadata, tags, and albums.",
                "uri": "photo-memex://photo/<sha256>",
                "metadata_keys": dict(sorted(photo_keys.items())),
            },
            "marginalia": {
                "description": (
                    "A free-form note attached to a photo (or orphaned)."
                ),
                "uri": "photo-memex://marginalia/<id>",
                "metadata_keys": dict(sorted(marginalia_keys.items())),
            },
        },
    }


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _records_to_jsonl_bytes(records: Iterable[dict[str, Any]]) -> bytes:
    buf = io.StringIO()
    for rec in records:
        buf.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    return buf.getvalue().encode("utf-8")


def _schema_yaml_bytes(schema: dict[str, Any]) -> bytes:
    buf = io.StringIO()
    buf.write("# Auto-generated by photo-memex. Edit freely.\n")
    yaml.safe_dump(
        schema, buf, default_flow_style=False, sort_keys=False, allow_unicode=True
    )
    return buf.getvalue().encode("utf-8")


def _readme_bytes(counts: dict[str, int], title: str | None = None) -> bytes:
    n_photo = counts.get("photo", 0)
    n_margin = counts.get("marginalia", 0)
    name = title or "photo-memex library"
    now = datetime.now(UTC).isoformat()
    lines = [
        "---",
        f"name: {name}",
        (
            f'description: "{n_photo} photos + {n_margin} marginalia '
            'exported from photo-memex"'
        ),
        f"datetime: {now}",
        f"generator: photo-memex {__version__}",
        "contents:",
        "  - path: records.jsonl",
        "    description: Photo + marginalia records (arkiv JSONL)",
        "  - path: schema.yaml",
        "    description: Record schema + per-kind counts",
        "---",
        "",
        "# photo-memex Archive",
        "",
        (
            f"This archive contains {n_photo} photo(s) and {n_margin} "
            "note(s) (marginalia)"
        ),
        "exported from photo-memex in "
        "[arkiv](https://github.com/queelius/arkiv) format.",
        "",
        "Each line in `records.jsonl` is one record. Records are typed by `kind`:",
        "",
        "- `photo`: a single photo with metadata, tags, albums.",
        "- `marginalia`: a free-form note attached (by URI) to a photo.",
        "",
        "URIs follow the cross-archive `photo-memex://` scheme and stay stable",
        "across re-imports; marginalia survive their target being re-imported.",
        "",
        "## Importing back into photo-memex",
        "",
        "```bash",
        "# Insert-or-skip on sha256 (photos); safe for re-imports.",
        "photo-memex import-arkiv <this bundle>",
        "```",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _write_file(path: Path, data: bytes) -> None:
    path.write_bytes(data)


def _write_zip(path: Path, jsonl: bytes, schema_yaml: bytes, readme: bytes) -> None:
    """Write the three bundle files into a single .zip archive."""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("records.jsonl", jsonl)
        zf.writestr("schema.yaml", schema_yaml)
        zf.writestr("README.md", readme)


def _write_tar_gz(
    path: Path, jsonl: bytes, schema_yaml: bytes, readme: bytes
) -> None:
    """Write the three bundle files into a single .tar.gz archive."""
    with tarfile.open(path, "w:gz") as tf:
        for name, data in (
            ("records.jsonl", jsonl),
            ("schema.yaml", schema_yaml),
            ("README.md", readme),
        ):
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def export_arkiv(output_path: Path, title: str | None = None) -> int:
    """Export the photo library to an arkiv bundle.

    Output format is inferred from *output_path*'s extension:

    - ``path.zip``              -> single zip file
    - ``path.tar.gz``/``.tgz``  -> single gzip-compressed tarball
    - any other path            -> directory containing records.jsonl,
                                   schema.yaml, and README.md

    Returns the number of photo records emitted (for backwards
    compatibility with existing callers; use the bundle on disk to
    inspect full per-kind counts).
    """
    output_path = Path(output_path)

    with session_scope() as session:
        photos = (
            session.query(Photo)
            .filter(Photo.archived_at.is_(None))
            .options(joinedload(Photo.tags), joinedload(Photo.albums))
            .all()
        )
        marginalia = (
            session.query(Marginalia)
            .filter(Marginalia.archived_at.is_(None))
            .all()
        )
        photo_records = [_photo_to_record(p) for p in photos]
        marginalia_records = [_marginalia_to_record(m) for m in marginalia]

    records: List[dict[str, Any]] = photo_records + marginalia_records
    schema = _build_schema(records)
    counts = schema["counts"]

    jsonl_bytes = _records_to_jsonl_bytes(records)
    schema_bytes = _schema_yaml_bytes(schema)
    readme_bytes = _readme_bytes(counts, title=title)

    fmt = _detect_compression(output_path)
    if fmt == "zip":
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _write_zip(output_path, jsonl_bytes, schema_bytes, readme_bytes)
    elif fmt == "tar.gz":
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _write_tar_gz(output_path, jsonl_bytes, schema_bytes, readme_bytes)
    else:
        output_path.mkdir(parents=True, exist_ok=True)
        _write_file(output_path / "records.jsonl", jsonl_bytes)
        _write_file(output_path / "schema.yaml", schema_bytes)
        _write_file(output_path / "README.md", readme_bytes)

    return counts["photo"]
