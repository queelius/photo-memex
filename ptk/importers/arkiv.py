"""Import an arkiv bundle back into photo-memex.

Bundles emitted by :mod:`ptk.exports.arkiv` (or any other tool
following the arkiv spec, within reason) are read, classified by
record kind, and inserted into the DB.

Supported input layouts (all auto-detected):

- directory with ``records.jsonl``, ``schema.yaml``, and ``README.md``
- ``.zip`` file containing those files
- ``.tar.gz`` / ``.tgz`` file containing those files
- bare ``.jsonl`` file of arkiv records (no schema/README needed)
- ``.jsonl.gz`` file of gzipped arkiv records — the shape an HTML SPA
  would emit for round-tripping marginalia back to the primary DB

Record kinds handled:

- ``kind == "photo"``     : insert or skip-duplicate keyed on SHA256
                            (primary key). Metadata only — the bundle
                            does not carry image payloads; operators
                            acquire files separately and reconcile by
                            SHA256.
- ``kind == "marginalia"``: insert or skip-duplicate keyed on a stable
                            content signature ``(photo_id, body)``
                            pair. See the importer body for why a
                            content-hash key is correct for
                            photo-memex's autoincrement-integer id
                            model.
- unknown kinds are ignored.

Round-trip fidelity:

- Photos: identified by ``sha256`` (the PK). Existing rows are left
  untouched so local enrichments (captions, tags, albums, faces)
  survive. Tag and album names present in the bundle are merged in;
  never removed.
- Marginalia: identified by the ``(photo_id, body)`` content pair.
  This is a soft de-dup — re-importing the same bundle into the same
  archive is idempotent. Moving a bundle to a *different* archive
  will create new integer ids; that's OK because photo-memex
  marginalia are small and the uniqueness invariant is "don't
  duplicate the same note on the same photo," not "preserve integer
  ids across archives."

``--merge`` is accepted for CLI parity with the ``*-memex`` ecosystem.
"""

from __future__ import annotations

import gzip
import io
import json
import tarfile
import zipfile
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def _jsonl_peek_first_record(reader) -> Optional[Dict[str, Any]]:
    try:
        for line in reader:
            if isinstance(line, bytes):
                line = line.decode("utf-8")
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            return rec if isinstance(rec, dict) else None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return None


_KINDS = ("photo", "marginalia")


def _is_photo_memex_record(rec: Dict[str, Any]) -> bool:
    if not isinstance(rec, dict):
        return False
    kind = rec.get("kind")
    if kind not in _KINDS:
        return False
    uri = rec.get("uri", "")
    if isinstance(uri, str) and uri.startswith("photo-memex://"):
        return True
    # Permissive fallback.
    if kind == "photo" and (rec.get("metadata") or {}).get("sha256"):
        return True
    if kind == "marginalia" and (rec.get("metadata") or {}).get("body"):
        return True
    return False


def detect(path: str | Path) -> bool:
    """Return True if *path* looks like an arkiv bundle we can read."""
    p = Path(path)
    if not p.exists():
        return False

    if p.is_dir():
        jsonl = p / "records.jsonl"
        if not jsonl.is_file():
            return False
        with open(jsonl, encoding="utf-8") as f:
            rec = _jsonl_peek_first_record(f)
        return rec is not None and _is_photo_memex_record(rec)

    lower = str(p).lower()
    if lower.endswith(".zip"):
        try:
            with zipfile.ZipFile(p) as zf:
                if "records.jsonl" not in zf.namelist():
                    return False
                with zf.open("records.jsonl") as f:
                    rec = _jsonl_peek_first_record(f)
            return rec is not None and _is_photo_memex_record(rec)
        except (zipfile.BadZipFile, KeyError):
            return False

    if lower.endswith(".tar.gz") or lower.endswith(".tgz"):
        try:
            with tarfile.open(p, "r:gz") as tf:
                try:
                    member = tf.getmember("records.jsonl")
                except KeyError:
                    return False
                extracted = tf.extractfile(member)
                if extracted is None:
                    return False
                rec = _jsonl_peek_first_record(extracted)
            return rec is not None and _is_photo_memex_record(rec)
        except tarfile.TarError:
            return False

    if lower.endswith(".jsonl.gz"):
        try:
            with gzip.open(p, "rt", encoding="utf-8") as f:
                rec = _jsonl_peek_first_record(f)
            return rec is not None and _is_photo_memex_record(rec)
        except (OSError, gzip.BadGzipFile):
            return False

    if lower.endswith(".jsonl"):
        try:
            with open(p, encoding="utf-8") as f:
                rec = _jsonl_peek_first_record(f)
            return rec is not None and _is_photo_memex_record(rec)
        except OSError:
            return False

    return False


# ---------------------------------------------------------------------------
# Bundle reading
# ---------------------------------------------------------------------------


def _open_jsonl(path: str | Path) -> Iterator[Dict[str, Any]]:
    p = Path(path)
    if p.is_dir():
        with open(p / "records.jsonl", encoding="utf-8") as f:
            yield from _parse_jsonl_lines(f)
        return
    lower = str(p).lower()
    if lower.endswith(".zip"):
        with zipfile.ZipFile(p) as zf:
            with zf.open("records.jsonl") as f:
                text = io.TextIOWrapper(f, encoding="utf-8")
                yield from _parse_jsonl_lines(text)
        return
    if lower.endswith(".tar.gz") or lower.endswith(".tgz"):
        with tarfile.open(p, "r:gz") as tf:
            member = tf.getmember("records.jsonl")
            extracted = tf.extractfile(member)
            if extracted is None:
                return
            text = io.TextIOWrapper(extracted, encoding="utf-8")
            yield from _parse_jsonl_lines(text)
        return
    if lower.endswith(".jsonl.gz"):
        with gzip.open(p, "rt", encoding="utf-8") as f:
            yield from _parse_jsonl_lines(f)
        return
    if lower.endswith(".jsonl"):
        with open(p, encoding="utf-8") as f:
            yield from _parse_jsonl_lines(f)
        return
    raise ValueError(f"unrecognized arkiv bundle: {path!r}")


def _parse_jsonl_lines(reader) -> Iterable[Dict[str, Any]]:
    for line in reader:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_timestamp(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        # Fallback: strict RFC3339 variants.
        cleaned = ts.replace("Z", "+00:00").split("+")[0]
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                continue
    return None


def _sha256_from_photo_uri(uri: Optional[str]) -> Optional[str]:
    """Extract the sha256 from a ``photo-memex://photo/<sha256>`` URI."""
    if not uri:
        return None
    prefix = "photo-memex://photo/"
    if not uri.startswith(prefix):
        return None
    tail = uri[len(prefix):]
    for sep in ("?", "#"):
        idx = tail.find(sep)
        if idx >= 0:
            tail = tail[:idx]
    return tail or None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def import_arkiv(path: str | Path, *, merge: bool = False) -> Dict[str, int]:
    """Import an arkiv bundle into the current photo-memex library.

    Uses :func:`ptk.db.session.session_scope` so the caller must have
    already run ``ptk init`` (or ``find_library()``) to locate the DB.

    Parameters
    ----------
    path:
        Directory, ``.zip``, ``.tar.gz`` / ``.tgz``, bare ``.jsonl``,
        or ``.jsonl.gz``.
    merge:
        Reserved for CLI parity; current insert path is already
        duplicate-safe.

    Returns
    -------
    dict
        ``{"photos_seen", "photos_added", "photos_skipped_existing",
           "marginalia_seen", "marginalia_added", "marginalia_skipped_existing",
           "marginalia_orphaned"}``.

        ``marginalia_orphaned`` counts records whose photo_uri does not
        resolve to a local photo; the note is still created with
        ``photo_id=None`` (orphan-survival contract).
    """
    from ptk.db.models import Marginalia, Photo
    from ptk.db.session import session_scope

    stats = {
        "photos_seen": 0,
        "photos_added": 0,
        "photos_skipped_existing": 0,
        "marginalia_seen": 0,
        "marginalia_added": 0,
        "marginalia_skipped_existing": 0,
        "marginalia_orphaned": 0,
    }

    records = list(_open_jsonl(path))

    with session_scope() as session:
        # Pass 1: photos. Insert-or-skip on SHA256 PK.
        sha_to_photo: Dict[str, Photo] = {}
        now = datetime.now(UTC)

        for rec in records:
            if not isinstance(rec, dict) or rec.get("kind") != "photo":
                continue
            stats["photos_seen"] += 1
            meta = rec.get("metadata") or {}
            sha = meta.get("sha256")
            if not sha:
                continue

            existing = session.get(Photo, sha)
            if existing is not None:
                sha_to_photo[sha] = existing
                _merge_photo_tags_and_albums(session, existing, meta)
                stats["photos_skipped_existing"] += 1
                continue

            # Create a metadata-only row. original_path is derived from
            # the bundle's source_path URI; if absent we set a synthetic
            # placeholder so the NOT NULL constraint is satisfied —
            # callers reconcile with the real file later.
            source_path = rec.get("source_path") or ""
            if source_path.startswith("file:///"):
                path_only = source_path[len("file://"):]
            else:
                path_only = source_path or f"imported:{sha}"

            photo = Photo(
                id=sha,
                original_path=path_only,
                filename=meta.get("filename") or sha[:12],
                file_size=meta.get("file_size") or 0,
                mime_type=rec.get("mimetype") or "application/octet-stream",
                width=meta.get("width"),
                height=meta.get("height"),
                date_taken=_parse_timestamp(rec.get("timestamp")),
                date_imported=now,
                camera_make=meta.get("camera_make"),
                camera_model=meta.get("camera_model"),
                lens=meta.get("lens"),
                focal_length=meta.get("focal_length"),
                aperture=meta.get("aperture"),
                shutter_speed=meta.get("shutter_speed"),
                iso=meta.get("iso"),
                latitude=meta.get("latitude"),
                longitude=meta.get("longitude"),
                altitude=meta.get("altitude"),
                location_name=meta.get("location_name"),
                country=meta.get("country"),
                city=meta.get("city"),
                caption=meta.get("caption"),
                scene=meta.get("scene"),
                is_favorite=bool(meta.get("is_favorite", False)),
                is_screenshot=bool(meta.get("is_screenshot", False)),
                is_video=bool(meta.get("is_video", False)),
                import_source=meta.get("import_source") or "arkiv",
            )
            session.add(photo)
            session.flush()
            _merge_photo_tags_and_albums(session, photo, meta)
            sha_to_photo[sha] = photo
            stats["photos_added"] += 1

        session.flush()

        # Pass 2: marginalia. Key by (photo_id, body) content for
        # idempotent re-imports.
        for rec in records:
            if not isinstance(rec, dict) or rec.get("kind") != "marginalia":
                continue
            stats["marginalia_seen"] += 1
            meta = rec.get("metadata") or {}
            body = meta.get("body") or rec.get("content") or ""
            if not body:
                continue

            parent_sha = _sha256_from_photo_uri(meta.get("photo_uri"))
            photo_obj = sha_to_photo.get(parent_sha) if parent_sha else None
            if photo_obj is None and parent_sha:
                photo_obj = session.get(Photo, parent_sha)
                if photo_obj is not None:
                    sha_to_photo[parent_sha] = photo_obj

            photo_id = photo_obj.id if photo_obj is not None else None
            if parent_sha and photo_obj is None:
                stats["marginalia_orphaned"] += 1

            existing = (
                session.query(Marginalia)
                .filter(Marginalia.photo_id == photo_id)
                .filter(Marginalia.body == body)
                .first()
            )
            if existing is not None:
                stats["marginalia_skipped_existing"] += 1
                continue

            note = Marginalia(
                photo_id=photo_id,
                body=body,
                created_at=(
                    _parse_timestamp(meta.get("created_at"))
                    or datetime.now(UTC)
                ),
                updated_at=_parse_timestamp(meta.get("updated_at")),
            )
            session.add(note)
            stats["marginalia_added"] += 1

        # session_scope commits on exit.
    return stats


def _merge_photo_tags_and_albums(session, photo, meta: Dict[str, Any]) -> None:
    """Merge tag names and album names from the bundle metadata into *photo*.

    Additive-only; existing local enrichments survive.
    """
    from ptk.db.models import Album, Tag

    now = datetime.now(UTC)

    tag_names = meta.get("tags") or []
    for name in tag_names:
        if not name:
            continue
        tag = session.query(Tag).filter(Tag.name == name).first()
        if tag is None:
            tag = Tag(name=name)
            session.add(tag)
            session.flush()
        if tag not in photo.tags:
            photo.tags.append(tag)

    album_names = meta.get("albums") or []
    for name in album_names:
        if not name:
            continue
        album = session.query(Album).filter(Album.name == name).first()
        if album is None:
            # Album.created_at / updated_at are NOT NULL.
            album = Album(name=name, created_at=now, updated_at=now)
            session.add(album)
            session.flush()
        if album not in photo.albums:
            photo.albums.append(album)
