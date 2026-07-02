"""MCP server for ptk photo library.

Exposes the SQLite photo library over stdio using FastMCP.
Read-only tools use raw sqlite3; write tools use SQLAlchemy session_scope().
"""

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from photo_memex.core.uri import InvalidUriError, build_photo_uri, parse_uri
from photo_memex.db.models import (
    Album,
    Event,
    Face,
    Marginalia,
    Person,
    Photo,
    Tag,
)
from photo_memex.db.session import session_scope

# Cap rows returned by the read-only run_sql tool so a wide/large SELECT
# cannot blow the LLM context. Callers paginate with LIMIT/OFFSET.
_MAX_SQL_ROWS = 1000


def _active_names(items) -> list[str]:
    """Return names of items whose archived_at is None."""
    return [item.name for item in items if item.archived_at is None]


def _active_photo_count(photos) -> int:
    """Count photos whose archived_at is None."""
    return sum(1 for p in photos if p.archived_at is None)


class PtkServer:
    """Core server logic for the ptk MCP interface.

    Uses a direct sqlite3 connection (not SQLAlchemy) for read-only
    raw SQL access to the photo library. Uses SQLAlchemy session_scope()
    for structured writes.
    """

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA query_only=ON")

    # ── helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_photo(session, photo_id: str) -> Photo:
        """Resolve a photo by full ID or prefix match.

        Raises ValueError if no match, ambiguous prefix, or prefix too short.
        """
        if not photo_id or len(photo_id) < 4:
            raise ValueError("Photo ID or prefix must be at least 4 characters")
        # autoescape=True treats %/_ in the prefix as literals rather than
        # LIKE wildcards. Without it, a prefix like "a_c%" would match photos
        # whose real IDs differ from the literal prefix, so a caller could
        # resolve (and then mutate) an unintended photo. SHA256 IDs never
        # contain %/_, so escaping only ever narrows matches to literal ones.
        matches = (
            session.query(Photo)
            .filter(
                Photo.id.startswith(photo_id, autoescape=True),
                Photo.archived_at.is_(None),
            )
            .limit(2)
            .all()
        )
        if not matches:
            raise ValueError(f"No photo found matching ID prefix: {photo_id}")
        if len(matches) > 1:
            raise ValueError(f"Ambiguous prefix '{photo_id}' matches multiple photos")
        return matches[0]

    @staticmethod
    def _people_names(photo: Photo) -> list[str]:
        """Extract unique person names from a photo's face records (active people only)."""
        return list({
            f.person.name
            for f in photo.faces
            if f.person and f.person.archived_at is None
        })

    @staticmethod
    def _get_or_resurrect(session, model, name: str, **create_kwargs):
        """Get an instance by unique name, un-archiving if archived, else create.

        The unique constraint on `name` for Tag/Album/Event/Person means there
        is at most one row per name. If an archived row exists, resurrect it
        (clear archived_at) so subsequent reads include it. This avoids silent
        inconsistency where writes target an archived row that responses hide.
        """
        instance = session.query(model).filter(model.name == name).first()
        if instance is None:
            instance = model(name=name, **create_kwargs)
            session.add(instance)
        elif instance.archived_at is not None:
            instance.archived_at = None
        return instance

    @staticmethod
    def _photo_summary(photo: Photo) -> dict[str, Any]:
        """Build a summary dict for a photo (used in write responses)."""
        return {
            "photo_id": photo.id,
            "filename": photo.filename,
            "caption": photo.caption,
            "scene": photo.scene,
            "is_favorite": photo.is_favorite,
            "tags": _active_names(photo.tags),
            "albums": _active_names(photo.albums),
            "people": PtkServer._people_names(photo),
        }

    def _mutate_photo(
        self,
        photo_id: str,
        mutate: Callable[[Session, Photo], None],
    ) -> dict[str, Any]:
        """Resolve a photo, apply a mutation, flush, and return the standard summary.

        Encapsulates the boilerplate shared by every single-photo write tool:
        session_scope -> _resolve_photo -> mutate -> session.flush -> ok summary.
        """
        with session_scope() as session:
            photo = self._resolve_photo(session, photo_id)
            mutate(session, photo)
            session.flush()
            return {"status": "ok", **self._photo_summary(photo)}

    @staticmethod
    def _resolve_photo_any(session, photo_id: str) -> Photo:
        """Resolve a photo by full id or prefix, INCLUDING archived rows.

        Used by archive/restore so a soft-deleted photo (which _resolve_photo
        hides) can still be targeted.
        """
        if not photo_id or len(photo_id) < 4:
            raise ValueError("Photo ID or prefix must be at least 4 characters")
        matches = (
            session.query(Photo)
            .filter(Photo.id.startswith(photo_id, autoescape=True))
            .limit(2)
            .all()
        )
        if not matches:
            raise ValueError(f"No photo found matching ID prefix: {photo_id}")
        if len(matches) > 1:
            raise ValueError(
                f"Ambiguous prefix '{photo_id}' matches multiple photos"
            )
        return matches[0]

    # ── soft-delete + marginalia write tools (R6) ──────────────────────────

    def archive_photo(self, photo_id: str, hard: bool = False) -> dict[str, Any]:
        """Soft-delete a photo (default) or hard-delete it (hard=True).

        Soft delete sets archived_at so default reads hide it while trails and
        marginalia keep resolving it. Idempotent: re-archiving preserves the
        original timestamp.
        """
        with session_scope() as session:
            photo = self._resolve_photo_any(session, photo_id)
            pid = photo.id
            if hard:
                session.delete(photo)
                session.flush()
                return {"status": "ok", "photo_id": pid, "deleted": "hard"}
            if photo.archived_at is None:
                photo.archived_at = datetime.now(UTC)
            session.flush()
            return {
                "status": "ok",
                "photo_id": pid,
                "archived_at": str(photo.archived_at),
            }

    def restore_photo(self, photo_id: str) -> dict[str, Any]:
        """Clear archived_at on a (soft-deleted) photo."""
        with session_scope() as session:
            photo = self._resolve_photo_any(session, photo_id)
            photo.archived_at = None
            session.flush()
            return {"status": "ok", "photo_id": photo.id, "archived_at": None}

    def add_marginalia(self, photo_id: str, body: str) -> dict[str, Any]:
        """Attach a free-form note to a photo. Returns the created note."""
        if not body or not body.strip():
            raise ValueError("marginalia body must be a non-empty string")
        with session_scope() as session:
            photo = self._resolve_photo_any(session, photo_id)
            note = Marginalia(
                photo_id=photo.id, body=body, created_at=datetime.now(UTC)
            )
            session.add(note)
            session.flush()
            return {"status": "ok", **self._marginalia_record(note)}

    def list_marginalia(
        self, photo_id: str, include_archived: bool = False
    ) -> list[dict[str, Any]]:
        """List a photo's notes (active only unless include_archived)."""
        with session_scope() as session:
            photo = self._resolve_photo_any(session, photo_id)
            q = session.query(Marginalia).filter(Marginalia.photo_id == photo.id)
            if not include_archived:
                q = q.filter(Marginalia.archived_at.is_(None))
            return [
                self._marginalia_record(m)
                for m in q.order_by(Marginalia.id.asc()).all()
            ]

    def get_marginalia(self, note_id: int) -> dict[str, Any]:
        """Return a single note by id (resolves archived notes too)."""
        with session_scope() as session:
            note = session.get(Marginalia, note_id)
            if note is None:
                raise ValueError(f"marginalia {note_id} not found")
            return self._marginalia_record(note)

    def update_marginalia(self, note_id: int, body: str) -> dict[str, Any]:
        """Replace a note's body and bump updated_at."""
        if not body or not body.strip():
            raise ValueError("marginalia body must be a non-empty string")
        with session_scope() as session:
            note = session.get(Marginalia, note_id)
            if note is None:
                raise ValueError(f"marginalia {note_id} not found")
            note.body = body
            note.updated_at = datetime.now(UTC)
            session.flush()
            return {"status": "ok", **self._marginalia_record(note)}

    def delete_marginalia(
        self, note_id: int, hard: bool = False
    ) -> dict[str, Any]:
        """Soft-delete a note (default) or hard-delete it (hard=True)."""
        with session_scope() as session:
            note = session.get(Marginalia, note_id)
            if note is None:
                raise ValueError(f"marginalia {note_id} not found")
            if hard:
                session.delete(note)
                session.flush()
                return {"status": "ok", "id": note_id, "deleted": "hard"}
            if note.archived_at is None:
                note.archived_at = datetime.now(UTC)
            session.flush()
            return {"status": "ok", **self._marginalia_record(note)}

    def restore_marginalia(self, note_id: int) -> dict[str, Any]:
        """Clear archived_at on a (soft-deleted) note."""
        with session_scope() as session:
            note = session.get(Marginalia, note_id)
            if note is None:
                raise ValueError(f"marginalia {note_id} not found")
            note.archived_at = None
            session.flush()
            return {"status": "ok", **self._marginalia_record(note)}

    # ── read tools (raw sqlite3) ───────────────────────────────────────────

    def get_schema(self) -> str:
        """Return CREATE TABLE statements for all tables in the database."""
        cursor = self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL ORDER BY name"
        )
        statements = [row[0] for row in cursor.fetchall()]
        return "\n\n".join(statements)

    def get_stats(self) -> dict[str, Any]:
        """Return library statistics as a dict."""
        row = self._conn.execute("""
            SELECT
                count(*)                              AS photo_count,
                count(*) FILTER (WHERE is_favorite)   AS favorites,
                coalesce(sum(file_size), 0)            AS total_size_bytes,
                min(date_taken)                        AS earliest_date,
                max(date_taken)                        AS latest_date,
                (SELECT count(*) FROM tags   WHERE archived_at IS NULL) AS tag_count,
                (SELECT count(*) FROM albums WHERE archived_at IS NULL) AS album_count
            FROM photos
            WHERE archived_at IS NULL
        """).fetchone()

        return dict(row)

    def run_sql(self, query: str) -> list[dict[str, Any]]:
        """Execute a read-only SQL query and return results as list of dicts.

        Only read-only statements are allowed (SELECT, WITH...SELECT, EXPLAIN,
        VALUES). The connection uses PRAGMA query_only=ON as a defense-in-depth
        guarantee. Multi-statement injection is blocked by sqlite3's
        single-statement enforcement.
        """
        cleaned = _strip_sql_comments(query).strip()
        words = cleaned.split()
        first_word = words[0].upper() if words else ""
        if first_word not in ("SELECT", "WITH", "EXPLAIN", "VALUES"):
            raise ValueError(
                "Only read-only statements are allowed (SELECT, WITH, EXPLAIN, VALUES)."
            )

        cursor = self._conn.execute(cleaned)
        columns = [desc[0] for desc in cursor.description]
        # Cap rows and summarize BLOBs: `SELECT *` over photos would otherwise
        # pull every thumbnail_data blob, which json.dumps(default=str) renders
        # as multi-KB b'\xff...' strings and blows the LLM context. Callers
        # paginate with LIMIT/OFFSET if they hit the cap.
        rows = cursor.fetchmany(_MAX_SQL_ROWS)

        def _clean(value: Any) -> Any:
            if isinstance(value, (bytes, bytearray)):
                return f"<blob {len(value)} bytes>"
            return value

        return [
            {col: _clean(val) for col, val in zip(columns, row, strict=True)}
            for row in rows
        ]

    # ── read tools (SQLAlchemy) ────────────────────────────────────────────

    def get_thumbnail(self, photo_id: str) -> list[Any]:
        """Return [Image, metadata_json] for a photo."""
        from mcp.server.fastmcp.utilities.types import Image  # optional dep

        with session_scope() as session:
            photo = self._resolve_photo(session, photo_id)

            metadata = self._photo_summary(photo)
            metadata["date_taken"] = str(photo.date_taken) if photo.date_taken else None

            if photo.thumbnail_data:
                fmt = (photo.thumbnail_mime or "image/jpeg").split("/")[-1]
                image = Image(data=photo.thumbnail_data, format=fmt)
            else:
                image = Image(path=photo.original_path)

            return [image, json.dumps(metadata, default=str)]

    @staticmethod
    def _photo_record(photo: Photo) -> dict[str, Any]:
        """Serialize a Photo to the comprehensive metadata dict."""
        return {
                "photo_id": photo.id,
                "filename": photo.filename,
                "original_path": photo.original_path,
                "file_size": photo.file_size,
                "mime_type": photo.mime_type,
                "width": photo.width,
                "height": photo.height,
                "date_taken": str(photo.date_taken) if photo.date_taken else None,
                "date_imported": str(photo.date_imported),
                "camera_make": photo.camera_make,
                "camera_model": photo.camera_model,
                "lens": photo.lens,
                "focal_length": photo.focal_length,
                "aperture": photo.aperture,
                "shutter_speed": photo.shutter_speed,
                "iso": photo.iso,
                "latitude": photo.latitude,
                "longitude": photo.longitude,
                "location_name": photo.location_name,
                "caption": photo.caption,
                "scene": photo.scene,
                "objects": photo.objects,
                "is_favorite": photo.is_favorite,
                "is_screenshot": photo.is_screenshot,
                "tags": _active_names(photo.tags),
                "albums": _active_names(photo.albums),
                "people": PtkServer._people_names(photo),
                "events": _active_names(photo.events),
                "has_thumbnail": photo.thumbnail_data is not None,
            }

    @staticmethod
    def _marginalia_record(m: Marginalia) -> dict[str, Any]:
        """Serialize a Marginalia note to a dict."""
        return {
            "id": m.id,
            "photo_id": m.photo_id,
            "photo_uri": build_photo_uri(m.photo_id) if m.photo_id else None,
            "body": m.body,
            "created_at": str(m.created_at) if m.created_at else None,
            "updated_at": str(m.updated_at) if m.updated_at else None,
            "archived_at": str(m.archived_at) if m.archived_at else None,
        }

    def get_photo(self, photo_id: str) -> dict[str, Any]:
        """Return comprehensive metadata for a single photo."""
        with session_scope() as session:
            photo = self._resolve_photo(session, photo_id)
            return self._photo_record(photo)

    def get_record(self, uri: str) -> dict[str, Any]:
        """Resolve a photo-memex:// URI to its record (federation contract).

        Accepts photo-memex://photo/<sha256> and
        photo-memex://marginalia/<id>. A URI fragment (e.g. #region=x,y,w,h)
        addresses a position within a record, so it is stripped before lookup
        and echoed back. Archived records still resolve (flagged) so
        cross-archive references survive soft-delete. Photo lookup is exact on
        the full SHA256 (the durable id the URI carries), not a prefix.
        """
        try:
            parsed = parse_uri(uri)
        except InvalidUriError as e:
            return {"error": "invalid_uri", "detail": str(e)}

        with session_scope() as session:
            if parsed.kind == "photo":
                photo = (
                    session.query(Photo)
                    .filter(Photo.id == parsed.id)
                    .first()
                )
                if photo is None:
                    return {"error": "not_found", "kind": "photo", "id": parsed.id}
                record = self._photo_record(photo)
                archived = photo.archived_at is not None
            elif parsed.kind == "marginalia":
                m = None
                if parsed.id.isdigit():
                    m = (
                        session.query(Marginalia)
                        .filter(Marginalia.id == int(parsed.id))
                        .first()
                    )
                if m is None:
                    return {
                        "error": "not_found",
                        "kind": "marginalia",
                        "id": parsed.id,
                    }
                record = self._marginalia_record(m)
                archived = m.archived_at is not None
            else:  # pragma: no cover - parse_uri already allowlists kinds
                return {"error": "unknown_kind", "kind": parsed.kind}

        result: dict[str, Any] = {
            "kind": parsed.kind,
            "uri": uri,
            "record": record,
            "archived": archived,
        }
        if parsed.fragment:
            result["fragment"] = parsed.fragment
        return result

    def list_tags(self) -> list[dict[str, Any]]:
        """Return all tags with photo counts."""
        with session_scope() as session:
            tags = session.query(Tag).filter(Tag.archived_at.is_(None)).order_by(Tag.name).all()
            return [
                {"id": t.id, "name": t.name, "photo_count": _active_photo_count(t.photos)}
                for t in tags
            ]

    def list_albums(self) -> list[dict[str, Any]]:
        """Return all albums with photo counts."""
        with session_scope() as session:
            albums = (
                session.query(Album).filter(Album.archived_at.is_(None)).order_by(Album.name).all()
            )
            return [
                {
                    "id": a.id,
                    "name": a.name,
                    "description": a.description,
                    "photo_count": _active_photo_count(a.photos),
                }
                for a in albums
            ]

    def list_people(self) -> list[dict[str, Any]]:
        """Return all people with photo counts."""
        with session_scope() as session:
            people = (
                session.query(Person)
                .filter(Person.archived_at.is_(None))
                .order_by(Person.name)
                .all()
            )
            return [{"id": p.id, "name": p.name, "photo_count": p.photo_count} for p in people]

    # ── single-photo write tools ───────────────────────────────────────────

    @staticmethod
    def _stamp_ai(photo: Photo, model: str | None) -> None:
        """Record AI provenance if a model name is provided."""
        if model:
            photo.ai_model = model
            photo.ai_analyzed_at = datetime.now(UTC)

    def set_caption(self, photo_id: str, caption: str, model: str | None = None) -> dict[str, Any]:
        """Set or overwrite a photo's caption. Optionally record which AI model did it."""

        def mutate(_session: Session, photo: Photo) -> None:
            photo.caption = caption
            self._stamp_ai(photo, model)

        return self._mutate_photo(photo_id, mutate)

    def add_tags(self, photo_id: str, tags: list[str]) -> dict[str, Any]:
        """Add tags to a photo (get-or-create, resurrects archived tags).

        Returns current tag list.
        """

        def mutate(session: Session, photo: Photo) -> None:
            # Compare against active tags only so archived tags don't suppress re-add.
            existing_names = {t.name for t in photo.tags if t.archived_at is None}
            for tag_name in tags:
                if tag_name in existing_names:
                    continue
                tag = self._get_or_resurrect(session, Tag, tag_name)
                if tag not in photo.tags:
                    photo.tags.append(tag)

        return self._mutate_photo(photo_id, mutate)

    def remove_tags(self, photo_id: str, tags: list[str]) -> dict[str, Any]:
        """Remove tags from a photo. Noop for tags not on this photo."""
        remove_set = set(tags)

        def mutate(_session: Session, photo: Photo) -> None:
            photo.tags = [t for t in photo.tags if t.name not in remove_set]

        return self._mutate_photo(photo_id, mutate)

    def set_favorite(self, photo_id: str, favorite: bool) -> dict[str, Any]:
        """Set or clear a photo's favorite status."""

        def mutate(_session: Session, photo: Photo) -> None:
            photo.is_favorite = favorite

        return self._mutate_photo(photo_id, mutate)

    def add_to_album(self, photo_id: str, album_name: str) -> dict[str, Any]:
        """Add a photo to an album (get-or-create, resurrects archived album)."""

        def mutate(session: Session, photo: Photo) -> None:
            now = datetime.now(UTC)
            album = self._get_or_resurrect(
                session, Album, album_name, created_at=now, updated_at=now
            )
            if album not in photo.albums:
                photo.albums.append(album)

        return self._mutate_photo(photo_id, mutate)

    def remove_from_album(self, photo_id: str, album_name: str) -> dict[str, Any]:
        """Remove a photo from an album. Noop if not in the album."""

        def mutate(_session: Session, photo: Photo) -> None:
            photo.albums = [a for a in photo.albums if a.name != album_name]

        return self._mutate_photo(photo_id, mutate)

    def set_scene(self, photo_id: str, scene: str, model: str | None = None) -> dict[str, Any]:
        """Set or overwrite a photo's scene classification. Optionally record AI provenance."""

        def mutate(_session: Session, photo: Photo) -> None:
            photo.scene = scene
            self._stamp_ai(photo, model)

        return self._mutate_photo(photo_id, mutate)

    # ── person tools ───────────────────────────────────────────────────────

    def tag_person(self, photo_id: str, person_name: str) -> dict[str, Any]:
        """Tag a person in a photo. Creates Person if new, creates Face record.

        Uses bbox=(0,0,1,1) placeholder and confidence=0.0 to indicate
        manual identification (no face detection).
        """

        def mutate(session: Session, photo: Photo) -> None:
            person = self._get_or_resurrect(
                session, Person, person_name, created_at=datetime.now(UTC)
            )
            session.flush()

            # Check if this person is already tagged in this photo
            existing = (
                session.query(Face)
                .filter(Face.photo_id == photo.id, Face.person_id == person.id)
                .first()
            )
            if not existing:
                session.add(
                    Face(
                        photo_id=photo.id,
                        person_id=person.id,
                        bbox_x=0.0,
                        bbox_y=0.0,
                        bbox_width=1.0,
                        bbox_height=1.0,
                        confidence=0.0,
                    )
                )

        return self._mutate_photo(photo_id, mutate)

    def untag_person(self, photo_id: str, person_name: str) -> dict[str, Any]:
        """Remove a person tag from a photo. Deletes the Face record."""

        def mutate(session: Session, photo: Photo) -> None:
            person = session.query(Person).filter(Person.name == person_name).first()
            if not person:
                return
            face = (
                session.query(Face)
                .filter(Face.photo_id == photo.id, Face.person_id == person.id)
                .first()
            )
            if face:
                session.delete(face)

        return self._mutate_photo(photo_id, mutate)

    # ── event tools ────────────────────────────────────────────────────────

    def _get_or_create_event(self, session, name: str) -> Event:
        """Get an existing event by name or create a new one (resurrects if archived)."""
        return self._get_or_resurrect(session, Event, name, is_auto_detected=False)

    @staticmethod
    def _update_event_dates(event: Event) -> None:
        """Auto-set event date range from active photos' date_taken values."""
        dates = [
            p.date_taken
            for p in event.photos
            if p.date_taken is not None and p.archived_at is None
        ]
        if dates:
            event.start_date = min(dates)
            event.end_date = max(dates)

    def create_event(
        self,
        name: str,
        photo_ids: list[str],
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create an event and add photos to it. Auto-sets date range from photos."""
        with session_scope() as session:
            event = self._get_or_create_event(session, name)

            if description is not None:
                event.description = description

            for pid in photo_ids:
                photo = self._resolve_photo(session, pid)
                if photo not in event.photos:
                    event.photos.append(photo)

            self._update_event_dates(event)

            session.flush()
            return {
                "status": "ok",
                "event": event.name,
                "photo_count": _active_photo_count(event.photos),
                "start_date": str(event.start_date) if event.start_date else None,
                "end_date": str(event.end_date) if event.end_date else None,
            }

    def add_to_event(self, photo_id: str, event_name: str) -> dict[str, Any]:
        """Add a single photo to an existing or new event."""
        with session_scope() as session:
            photo = self._resolve_photo(session, photo_id)
            event = self._get_or_create_event(session, event_name)

            if photo not in event.photos:
                event.photos.append(photo)

            self._update_event_dates(event)

            session.flush()
            return {
                "status": "ok",
                "event": event.name,
                "photo_id": photo.id,
                "photo_count": _active_photo_count(event.photos),
            }

    # ── batch tools ────────────────────────────────────────────────────────

    @staticmethod
    def _batch_apply(
        photo_ids: list[str],
        apply_fn: Callable[[str], Any],
    ) -> dict[str, Any]:
        """Apply a function to each photo ID, collecting errors per photo."""
        succeeded = 0
        errors: list[dict[str, str]] = []
        for pid in photo_ids:
            try:
                apply_fn(pid)
                succeeded += 1
            except ValueError as e:
                errors.append({"photo_id": pid, "error": str(e)})

        if not errors:
            status = "ok"
        elif succeeded > 0:
            status = "partial"
        else:
            status = "error"

        return {
            "status": status,
            "succeeded": succeeded,
            "failed": len(errors),
            "errors": errors,
        }

    def batch_add_tags(self, photo_ids: list[str], tags: list[str]) -> dict[str, Any]:
        """Add tags to multiple photos at once. Reports per-photo errors."""
        return self._batch_apply(photo_ids, lambda pid: self.add_tags(pid, tags))

    def batch_set_caption(self, photo_ids: list[str], caption: str) -> dict[str, Any]:
        """Set the same caption on multiple photos. Reports per-photo errors."""
        return self._batch_apply(photo_ids, lambda pid: self.set_caption(pid, caption))

    # ── lifecycle ──────────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()


def _strip_sql_comments(sql: str) -> str:
    """Strip leading SQL comments (block and line) from a query string."""
    result = sql.strip()
    while True:
        if result.startswith("/*"):
            end = result.find("*/")
            if end == -1:
                break
            result = result[end + 2 :].strip()
        elif result.startswith("--"):
            newline = result.find("\n")
            if newline == -1:
                result = ""
                break
            result = result[newline + 1 :].strip()
        else:
            break
    return result


def run_mcp_server(db_path: str) -> None:
    """Run the ptk MCP server over stdio."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise ImportError(
            "MCP server requires 'mcp' package. Install with: pip install photo-memex[mcp]"
        ) from exc

    from typing import Annotated

    from mcp.types import ToolAnnotations
    from pydantic import Field

    mcp = FastMCP("photo-memex")
    server = PtkServer(db_path)

    # Reusable type alias for the photo_id parameter
    _photo_id = Annotated[str, Field(description="Photo SHA256 ID or unique prefix")]
    _photo_id_list = Annotated[list[str], Field(description="Photo IDs (or prefixes)")]

    # Shared annotation presets
    _read = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
    _write = ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
    _destructive = ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=False,
    )

    # ── read tools ─────────────────────────────────────────────────────

    @mcp.tool(annotations=_read)
    def get_schema() -> str:
        """Get the database schema (CREATE TABLE statements). Call this first to understand the data model before writing SQL queries."""
        return server.get_schema()

    @mcp.tool(annotations=_read)
    def get_stats() -> str:
        """Get library statistics: photo count, tag count, album count, date range, total size, favorites."""
        return json.dumps(server.get_stats(), indent=2, default=str)

    @mcp.tool(annotations=_read)
    def run_sql(
        query: Annotated[
            str,
            Field(description="SQL SELECT query to execute against the photo library"),
        ],
    ) -> str:
        """Run a read-only SQL query against the photo library. Read-only
        statements only (SELECT, WITH, EXPLAIN, VALUES). Results are capped at
        1000 rows (add LIMIT/OFFSET to paginate) and BLOB columns such as
        thumbnail_data are summarized as '<blob N bytes>'. Tables: photos,
        tags, albums, photo_tags, photo_albums, people, faces, events,
        photo_events. Use JOIN for relationships."""
        return json.dumps(server.run_sql(query), indent=2, default=str)

    @mcp.tool(annotations=_read)
    def get_thumbnail(photo_id: _photo_id) -> list:
        """Get a photo's thumbnail image and current metadata. Returns the image and a JSON string with caption, tags, people, etc. Use this to SEE a photo before annotating it."""
        return server.get_thumbnail(photo_id)

    @mcp.tool(annotations=_read)
    def get_photo(photo_id: _photo_id) -> str:
        """Get comprehensive metadata for a photo: EXIF, location, tags, albums, people, events, AI annotations. Use this when you need full details without the image."""
        return json.dumps(server.get_photo(photo_id), indent=2, default=str)

    @mcp.tool(annotations=_read)
    def get_record(
        uri: Annotated[
            str,
            Field(
                description="A photo-memex:// URI: photo-memex://photo/<sha256> "
                "or photo-memex://marginalia/<id> (an optional #fragment such "
                "as #region=x,y,w,h is echoed back). Resolves the record for "
                "cross-archive references; archived records still resolve."
            ),
        ],
    ) -> str:
        """Resolve a photo-memex:// URI to its record (federation entrypoint)."""
        return json.dumps(server.get_record(uri), indent=2, default=str)

    @mcp.tool(annotations=_read)
    def list_tags() -> str:
        """List all tags in the library with their photo counts. Use this to see existing tags before adding new ones."""
        return json.dumps(server.list_tags(), indent=2)

    @mcp.tool(annotations=_read)
    def list_albums() -> str:
        """List all albums in the library with their photo counts."""
        return json.dumps(server.list_albums(), indent=2)

    @mcp.tool(annotations=_read)
    def list_people() -> str:
        """List all known people in the library with their photo counts."""
        return json.dumps(server.list_people(), indent=2)

    # ── single-photo write tools ───────────────────────────────────────

    @mcp.tool(annotations=_write)
    def set_caption(
        photo_id: _photo_id,
        caption: Annotated[
            str,
            Field(description="Rich description of what's in the photo. Be specific and detailed."),
        ],
        model: Annotated[
            str | None,
            Field(
                description="AI model name for provenance tracking, e.g. 'claude-sonnet-4-20250514'"
            ),
        ] = None,
    ) -> str:
        """Set or overwrite a photo's caption. Write a detailed description of the photo's content, subjects, setting, and mood. Pass your model name to record AI provenance."""
        return json.dumps(server.set_caption(photo_id, caption, model), default=str)

    @mcp.tool(annotations=_write)
    def add_tags(
        photo_id: _photo_id,
        tags: Annotated[
            list[str],
            Field(description="Tags to add. Use lowercase, e.g. ['sunset', 'beach', 'family']"),
        ],
    ) -> str:
        """Add tags to a photo. Creates new tags if they don't exist. Returns the photo's current tag list. Check list_tags() first to use consistent tag names."""
        return json.dumps(server.add_tags(photo_id, tags), default=str)

    @mcp.tool(annotations=_destructive)
    def remove_tags(
        photo_id: _photo_id,
        tags: Annotated[
            list[str],
            Field(description="Tag names to remove"),
        ],
    ) -> str:
        """Remove tags from a photo. Silently ignores tags that aren't on this photo."""
        return json.dumps(server.remove_tags(photo_id, tags), default=str)

    @mcp.tool(annotations=_write)
    def set_favorite(
        photo_id: _photo_id,
        favorite: Annotated[
            bool,
            Field(description="True to favorite, False to unfavorite"),
        ],
    ) -> str:
        """Set or clear a photo's favorite status."""
        return json.dumps(server.set_favorite(photo_id, favorite), default=str)

    @mcp.tool(annotations=_write)
    def add_to_album(
        photo_id: _photo_id,
        album_name: Annotated[
            str,
            Field(description="Album name. Created automatically if it doesn't exist."),
        ],
    ) -> str:
        """Add a photo to an album. Creates the album if it doesn't exist. Check list_albums() first to use consistent album names."""
        return json.dumps(server.add_to_album(photo_id, album_name), default=str)

    @mcp.tool(annotations=_destructive)
    def remove_from_album(
        photo_id: _photo_id,
        album_name: Annotated[
            str,
            Field(description="Album name to remove from"),
        ],
    ) -> str:
        """Remove a photo from an album. Silently ignores if the photo isn't in the album."""
        return json.dumps(server.remove_from_album(photo_id, album_name), default=str)

    @mcp.tool(annotations=_write)
    def set_scene(
        photo_id: _photo_id,
        scene: Annotated[
            str,
            Field(
                description="Scene classification, e.g. 'outdoor', 'indoor', 'portrait', 'landscape', 'night'"
            ),
        ],
        model: Annotated[
            str | None,
            Field(description="AI model name for provenance tracking"),
        ] = None,
    ) -> str:
        """Set a photo's scene classification (e.g. outdoor, indoor, portrait, landscape). Pass your model name to record AI provenance."""
        return json.dumps(server.set_scene(photo_id, scene, model), default=str)

    # ── person tools ───────────────────────────────────────────────────

    @mcp.tool(annotations=_write)
    def tag_person(
        photo_id: _photo_id,
        person_name: Annotated[
            str,
            Field(description="Full name of the person"),
        ],
    ) -> str:
        """Tag a person in a photo. Creates the person if new. Use this AFTER showing the photo to the user with get_thumbnail and asking them to identify people. Check list_people() first for consistent naming."""
        return json.dumps(server.tag_person(photo_id, person_name), default=str)

    @mcp.tool(annotations=_destructive)
    def untag_person(
        photo_id: _photo_id,
        person_name: Annotated[
            str,
            Field(description="Name of the person to untag"),
        ],
    ) -> str:
        """Remove a person tag from a photo."""
        return json.dumps(server.untag_person(photo_id, person_name), default=str)

    # ── event tools ────────────────────────────────────────────────────

    @mcp.tool(annotations=_write)
    def create_event(
        name: Annotated[
            str,
            Field(description="Event name, e.g. 'Beach vacation 2024'"),
        ],
        photo_ids: Annotated[
            list[str],
            Field(description="Photo IDs (or prefixes) to include in the event"),
        ],
        description: Annotated[
            str | None,
            Field(description="Optional event description"),
        ] = None,
    ) -> str:
        """Create an event grouping photos together. Auto-detects date range from photos. Creates the event if it doesn't exist, or adds photos to an existing event with the same name."""
        return json.dumps(server.create_event(name, photo_ids, description), default=str)

    @mcp.tool(annotations=_write)
    def add_to_event(
        photo_id: _photo_id,
        event_name: Annotated[
            str,
            Field(description="Event name to add the photo to"),
        ],
    ) -> str:
        """Add a single photo to an event. Creates the event if it doesn't exist."""
        return json.dumps(server.add_to_event(photo_id, event_name), default=str)

    # ── batch tools ────────────────────────────────────────────────────

    @mcp.tool(annotations=_write)
    def batch_add_tags(
        photo_ids: _photo_id_list,
        tags: Annotated[
            list[str],
            Field(description="Tags to add to all specified photos"),
        ],
    ) -> str:
        """Add the same tags to multiple photos at once. Reports any per-photo errors."""
        return json.dumps(server.batch_add_tags(photo_ids, tags), default=str)

    @mcp.tool(annotations=_write)
    def batch_set_caption(
        photo_ids: _photo_id_list,
        caption: Annotated[
            str,
            Field(description="Caption to set on all specified photos"),
        ],
    ) -> str:
        """Set the same caption on multiple photos. Useful for batch classification."""
        return json.dumps(server.batch_set_caption(photo_ids, caption), default=str)

    # ── soft-delete + marginalia tools (R6) ────────────────────────────

    _note_id = Annotated[int, Field(description="Marginalia note id")]

    @mcp.tool(annotations=_destructive)
    def archive_photo(
        photo_id: _photo_id,
        hard: Annotated[
            bool,
            Field(description="Hard-delete instead of soft-delete (irreversible)"),
        ] = False,
    ) -> str:
        """Soft-delete a photo (hidden from default reads, still resolvable) or hard-delete it with hard=True."""
        return json.dumps(server.archive_photo(photo_id, hard=hard), default=str)

    @mcp.tool(annotations=_write)
    def restore_photo(photo_id: _photo_id) -> str:
        """Restore a soft-deleted photo (clear its archived_at)."""
        return json.dumps(server.restore_photo(photo_id), default=str)

    @mcp.tool(annotations=_write)
    def add_marginalia(
        photo_id: _photo_id,
        body: Annotated[str, Field(description="Free-form note text")],
    ) -> str:
        """Attach a free-form note (marginalia) to a photo."""
        return json.dumps(server.add_marginalia(photo_id, body), default=str)

    @mcp.tool(annotations=_read)
    def list_marginalia(
        photo_id: _photo_id,
        include_archived: Annotated[
            bool, Field(description="Include soft-deleted notes")
        ] = False,
    ) -> str:
        """List the notes attached to a photo."""
        return json.dumps(
            server.list_marginalia(photo_id, include_archived=include_archived),
            indent=2,
            default=str,
        )

    @mcp.tool(annotations=_read)
    def get_marginalia(note_id: _note_id) -> str:
        """Get a single marginalia note by id."""
        return json.dumps(server.get_marginalia(note_id), indent=2, default=str)

    @mcp.tool(annotations=_write)
    def update_marginalia(
        note_id: _note_id,
        body: Annotated[str, Field(description="New note text")],
    ) -> str:
        """Replace a note's body."""
        return json.dumps(server.update_marginalia(note_id, body), default=str)

    @mcp.tool(annotations=_destructive)
    def delete_marginalia(
        note_id: _note_id,
        hard: Annotated[
            bool, Field(description="Hard-delete instead of soft-delete")
        ] = False,
    ) -> str:
        """Soft-delete a note (default) or hard-delete it with hard=True."""
        return json.dumps(
            server.delete_marginalia(note_id, hard=hard), default=str
        )

    @mcp.tool(annotations=_write)
    def restore_marginalia(note_id: _note_id) -> str:
        """Restore a soft-deleted note (clear its archived_at)."""
        return json.dumps(server.restore_marginalia(note_id), default=str)

    mcp.run(transport="stdio")
