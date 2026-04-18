"""Tests for ptk MCP server logic."""

import json
from datetime import UTC, datetime

import pytest

from ptk.core.config import get_config
from ptk.db.models import Album, Event, Face, Person, Photo, Tag
from ptk.db.session import session_scope
from ptk.mcp.server import PtkServer


@pytest.fixture
def server(populated_library):
    """Create a PtkServer against the test library's database."""
    db_path = get_config().database_path
    srv = PtkServer(str(db_path))
    yield srv
    srv.close()


@pytest.fixture
def photo_id(server):
    """Get the ID of the first photo in the test library."""
    rows = server.run_sql("SELECT id FROM photos LIMIT 1")
    return rows[0]["id"]


# ── get_schema ──────────────────────────────────────────────────────────────


class TestGetSchema:
    def test_returns_create_table_statements(self, server):
        schema = server.get_schema()
        assert "CREATE TABLE" in schema

    def test_includes_photos_table(self, server):
        schema = server.get_schema()
        assert "photos" in schema

    def test_includes_tags_table(self, server):
        schema = server.get_schema()
        assert "tags" in schema

    def test_includes_albums_table(self, server):
        schema = server.get_schema()
        assert "albums" in schema


# ── get_stats ───────────────────────────────────────────────────────────────


class TestGetStats:
    def test_returns_photo_count(self, server):
        stats = server.get_stats()
        assert stats["photo_count"] >= 1

    def test_returns_tag_count(self, server):
        stats = server.get_stats()
        assert "tag_count" in stats
        assert isinstance(stats["tag_count"], int)

    def test_returns_album_count(self, server):
        stats = server.get_stats()
        assert "album_count" in stats
        assert isinstance(stats["album_count"], int)

    def test_returns_total_size_bytes(self, server):
        stats = server.get_stats()
        assert "total_size_bytes" in stats
        assert stats["total_size_bytes"] > 0

    def test_returns_favorites(self, server):
        stats = server.get_stats()
        assert "favorites" in stats
        assert isinstance(stats["favorites"], int)

    def test_returns_date_range(self, server):
        stats = server.get_stats()
        assert "earliest_date" in stats
        assert "latest_date" in stats


# ── run_sql ─────────────────────────────────────────────────────────────────


class TestRunSql:
    def test_select_returns_list_of_dicts(self, server):
        rows = server.run_sql("SELECT id, filename FROM photos")
        assert isinstance(rows, list)
        assert len(rows) >= 1
        assert isinstance(rows[0], dict)
        assert "id" in rows[0]
        assert "filename" in rows[0]

    def test_select_column_names_as_keys(self, server):
        rows = server.run_sql("SELECT id, file_size FROM photos LIMIT 1")
        row = rows[0]
        assert set(row.keys()) >= {"id", "file_size"}

    def test_empty_result(self, server):
        rows = server.run_sql("SELECT id FROM photos WHERE id = 'nonexistent'")
        assert rows == []

    def test_aggregate_query(self, server):
        rows = server.run_sql("SELECT count(*) AS cnt FROM photos")
        assert len(rows) == 1
        assert rows[0]["cnt"] >= 1

    @pytest.mark.parametrize(
        "statement",
        [
            "DELETE FROM photos",
            "DROP TABLE photos",
            "INSERT INTO photos (id) VALUES ('x')",
            "UPDATE photos SET filename='x'",
        ],
    )
    def test_rejects_non_select(self, server, statement):
        with pytest.raises(ValueError, match="Only read-only"):
            server.run_sql(statement)

    def test_rejects_non_select_with_leading_whitespace(self, server):
        with pytest.raises(ValueError, match="Only read-only"):
            server.run_sql("   DELETE FROM photos")

    def test_rejects_non_select_with_leading_comment(self, server):
        with pytest.raises(ValueError, match="Only read-only"):
            server.run_sql("/* comment */ DELETE FROM photos")

    def test_rejects_multiple_statements(self, server):
        import sqlite3

        with pytest.raises(sqlite3.ProgrammingError):
            server.run_sql("SELECT 1; DROP TABLE photos")

    def test_cte_with_select(self, server):
        rows = server.run_sql(
            "WITH recent AS (SELECT id, filename FROM photos LIMIT 5) SELECT * FROM recent"
        )
        assert isinstance(rows, list)
        assert len(rows) >= 1

    def test_explain_allowed(self, server):
        rows = server.run_sql("EXPLAIN QUERY PLAN SELECT id FROM photos")
        assert isinstance(rows, list)

    def test_values_allowed(self, server):
        rows = server.run_sql("VALUES (1, 'a'), (2, 'b')")
        assert len(rows) == 2

    def test_rejects_non_select_after_mixed_comments(self, server):
        with pytest.raises(ValueError, match="Only read-only"):
            server.run_sql("-- comment\n/* block */ DELETE FROM photos")

    def test_rejects_with_delete(self, server):
        """WITH can precede DELETE in SQLite. Allowlist permits WITH; PRAGMA
        query_only=ON must block the DELETE at the engine level.
        """
        import sqlite3

        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            server.run_sql("WITH t AS (SELECT 1) DELETE FROM photos WHERE id IN (SELECT * FROM t)")


# ── get_photo ───────────────────────────────────────────────────────────────


class TestGetPhoto:
    def test_returns_full_metadata(self, server, photo_id):
        result = server.get_photo(photo_id)
        assert result["photo_id"] == photo_id
        assert "filename" in result
        assert "original_path" in result
        assert "file_size" in result
        assert "mime_type" in result
        assert "tags" in result
        assert "albums" in result
        assert "people" in result
        assert "events" in result
        assert "has_thumbnail" in result

    def test_prefix_lookup(self, server, photo_id):
        prefix = photo_id[:8]
        result = server.get_photo(prefix)
        assert result["photo_id"] == photo_id

    def test_nonexistent_photo_raises(self, server):
        with pytest.raises(ValueError, match="No photo found"):
            server.get_photo("aaaa_nonexistent")

    def test_empty_photo_id_raises(self, server):
        with pytest.raises(ValueError, match="at least 4 characters"):
            server.get_photo("")

    def test_short_prefix_raises(self, server):
        with pytest.raises(ValueError, match="at least 4 characters"):
            server.get_photo("ab")

    def test_tags_initially_empty(self, server, photo_id):
        result = server.get_photo(photo_id)
        assert result["tags"] == []

    def test_people_initially_empty(self, server, photo_id):
        result = server.get_photo(photo_id)
        assert result["people"] == []


# ── get_thumbnail ───────────────────────────────────────────────────────────


class TestGetThumbnail:
    def test_returns_list_of_two(self, server, photo_id):
        result = server.get_thumbnail(photo_id)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_second_element_is_json_metadata(self, server, photo_id):
        result = server.get_thumbnail(photo_id)
        metadata = json.loads(result[1])
        assert metadata["photo_id"] == photo_id
        assert "filename" in metadata
        assert "tags" in metadata

    def test_first_element_is_image(self, server, photo_id):
        from mcp.server.fastmcp.utilities.types import Image

        result = server.get_thumbnail(photo_id)
        assert isinstance(result[0], Image)

    def test_prefix_lookup(self, server, photo_id):
        prefix = photo_id[:8]
        result = server.get_thumbnail(prefix)
        metadata = json.loads(result[1])
        assert metadata["photo_id"] == photo_id


# ── list_tags ───────────────────────────────────────────────────────────────


class TestListTags:
    def test_returns_list(self, server):
        result = server.list_tags()
        assert isinstance(result, list)

    def test_initially_empty(self, server):
        result = server.list_tags()
        assert result == []

    def test_shows_tags_after_add(self, server, photo_id):
        server.add_tags(photo_id, ["sunset", "beach"])
        result = server.list_tags()
        names = {t["name"] for t in result}
        assert "sunset" in names
        assert "beach" in names

    def test_includes_photo_count(self, server, photo_id):
        server.add_tags(photo_id, ["nature"])
        result = server.list_tags()
        nature = next(t for t in result if t["name"] == "nature")
        assert nature["photo_count"] == 1


# ── list_albums ─────────────────────────────────────────────────────────────


class TestListAlbums:
    def test_returns_list(self, server):
        result = server.list_albums()
        assert isinstance(result, list)

    def test_initially_empty(self, server):
        result = server.list_albums()
        assert result == []

    def test_shows_albums_after_add(self, server, photo_id):
        server.add_to_album(photo_id, "Vacation 2024")
        result = server.list_albums()
        names = {a["name"] for a in result}
        assert "Vacation 2024" in names

    def test_includes_photo_count(self, server, photo_id):
        server.add_to_album(photo_id, "Summer")
        result = server.list_albums()
        summer = next(a for a in result if a["name"] == "Summer")
        assert summer["photo_count"] == 1


# ── list_people ─────────────────────────────────────────────────────────────


class TestListPeople:
    def test_returns_list(self, server):
        result = server.list_people()
        assert isinstance(result, list)

    def test_initially_empty(self, server):
        result = server.list_people()
        assert result == []

    def test_shows_people_after_tag(self, server, photo_id):
        server.tag_person(photo_id, "Alice")
        result = server.list_people()
        names = {p["name"] for p in result}
        assert "Alice" in names

    def test_includes_photo_count(self, server, photo_id):
        server.tag_person(photo_id, "Bob")
        result = server.list_people()
        bob = next(p for p in result if p["name"] == "Bob")
        assert bob["photo_count"] == 1


# ── set_caption ─────────────────────────────────────────────────────────────


class TestSetCaption:
    def test_sets_caption(self, server, photo_id):
        result = server.set_caption(photo_id, "A red test image")
        assert result["status"] == "ok"
        assert result["caption"] == "A red test image"

    def test_overwrites_caption(self, server, photo_id):
        server.set_caption(photo_id, "First caption")
        result = server.set_caption(photo_id, "Second caption")
        assert result["caption"] == "Second caption"

    def test_idempotent(self, server, photo_id):
        server.set_caption(photo_id, "Same caption")
        result = server.set_caption(photo_id, "Same caption")
        assert result["status"] == "ok"
        assert result["caption"] == "Same caption"

    def test_nonexistent_photo_raises(self, server):
        with pytest.raises(ValueError, match="No photo found"):
            server.set_caption("aaaa_nonexistent", "caption")

    def test_reflected_in_get_photo(self, server, photo_id):
        server.set_caption(photo_id, "Verifiable caption")
        photo = server.get_photo(photo_id)
        assert photo["caption"] == "Verifiable caption"

    def test_stamps_ai_model(self, server, photo_id):
        server.set_caption(photo_id, "AI caption", model="claude-sonnet-4-20250514")
        photo = server.get_photo(photo_id)
        assert photo["caption"] == "AI caption"
        rows = server.run_sql(
            f"SELECT ai_model, ai_analyzed_at FROM photos WHERE id = '{photo_id}'"
        )
        assert rows[0]["ai_model"] == "claude-sonnet-4-20250514"
        assert rows[0]["ai_analyzed_at"] is not None

    def test_no_model_does_not_stamp(self, server, photo_id):
        server.set_caption(photo_id, "Plain caption")
        rows = server.run_sql(f"SELECT ai_model FROM photos WHERE id = '{photo_id}'")
        assert rows[0]["ai_model"] is None


# ── add_tags ────────────────────────────────────────────────────────────────


class TestAddTags:
    def test_adds_tags(self, server, photo_id):
        result = server.add_tags(photo_id, ["sunset", "beach"])
        assert result["status"] == "ok"
        assert "sunset" in result["tags"]
        assert "beach" in result["tags"]

    def test_idempotent_add(self, server, photo_id):
        server.add_tags(photo_id, ["nature"])
        result = server.add_tags(photo_id, ["nature"])
        assert result["tags"].count("nature") == 1

    def test_get_or_create_reuses_existing_tag(self, server, photo_id):
        server.add_tags(photo_id, ["shared"])
        # Adding same tag name again should reuse the Tag row
        result = server.add_tags(photo_id, ["shared", "new"])
        assert "shared" in result["tags"]
        assert "new" in result["tags"]

    def test_nonexistent_photo_raises(self, server):
        with pytest.raises(ValueError, match="No photo found"):
            server.add_tags("aaaa_nonexistent", ["tag"])

    def test_archived_tag_resurrected(self, server, photo_id):
        """An archived tag with the same name should be resurrected, not duplicated."""
        with session_scope() as s:
            s.add(Tag(name="ghost", archived_at=datetime.now(UTC)))

        result = server.add_tags(photo_id, ["ghost"])
        assert "ghost" in result["tags"]

        # Verify only one Tag row exists and it is no longer archived.
        with session_scope() as s:
            tags = s.query(Tag).filter(Tag.name == "ghost").all()
            assert len(tags) == 1
            assert tags[0].archived_at is None

    def test_archived_tag_on_photo_does_not_block_re_add(self, server, photo_id):
        """If a photo has an archived tag attached, add_tags must still surface it."""
        with session_scope() as s:
            tag = Tag(name="zombie")
            photo = s.query(Photo).filter(Photo.id == photo_id).one()
            photo.tags.append(tag)
            s.flush()
            tag.archived_at = datetime.now(UTC)

        result = server.add_tags(photo_id, ["zombie"])
        assert "zombie" in result["tags"]


# ── remove_tags ─────────────────────────────────────────────────────────────


class TestRemoveTags:
    def test_removes_tags(self, server, photo_id):
        server.add_tags(photo_id, ["a", "b", "c"])
        result = server.remove_tags(photo_id, ["b"])
        assert "b" not in result["tags"]
        assert "a" in result["tags"]
        assert "c" in result["tags"]

    def test_noop_for_nonexistent_tag(self, server, photo_id):
        server.add_tags(photo_id, ["keep"])
        result = server.remove_tags(photo_id, ["nonexistent"])
        assert result["status"] == "ok"
        assert "keep" in result["tags"]

    def test_remove_all(self, server, photo_id):
        server.add_tags(photo_id, ["x", "y"])
        result = server.remove_tags(photo_id, ["x", "y"])
        assert result["tags"] == []


# ── set_favorite ────────────────────────────────────────────────────────────


class TestSetFavorite:
    def test_set_favorite_true(self, server, photo_id):
        result = server.set_favorite(photo_id, True)
        assert result["status"] == "ok"
        assert result["is_favorite"] is True

    def test_set_favorite_false(self, server, photo_id):
        server.set_favorite(photo_id, True)
        result = server.set_favorite(photo_id, False)
        assert result["is_favorite"] is False

    def test_idempotent(self, server, photo_id):
        server.set_favorite(photo_id, True)
        result = server.set_favorite(photo_id, True)
        assert result["status"] == "ok"
        assert result["is_favorite"] is True


# ── add_to_album / remove_from_album ───────────────────────────────────────


class TestAlbumOperations:
    def test_add_to_album(self, server, photo_id):
        result = server.add_to_album(photo_id, "Vacation 2024")
        assert result["status"] == "ok"
        assert "Vacation 2024" in result["albums"]

    def test_add_to_album_idempotent(self, server, photo_id):
        server.add_to_album(photo_id, "Summer")
        result = server.add_to_album(photo_id, "Summer")
        assert result["albums"].count("Summer") == 1

    def test_add_creates_album(self, server, photo_id):
        server.add_to_album(photo_id, "New Album")
        albums = server.list_albums()
        names = {a["name"] for a in albums}
        assert "New Album" in names

    def test_remove_from_album(self, server, photo_id):
        server.add_to_album(photo_id, "Temp")
        result = server.remove_from_album(photo_id, "Temp")
        assert "Temp" not in result["albums"]

    def test_remove_noop(self, server, photo_id):
        result = server.remove_from_album(photo_id, "Nonexistent")
        assert result["status"] == "ok"

    def test_archived_album_resurrected(self, server, photo_id):
        """Adding to an archived album by name should resurrect it."""
        now = datetime.now(UTC)
        with session_scope() as s:
            s.add(Album(name="Memories", created_at=now, updated_at=now, archived_at=now))

        result = server.add_to_album(photo_id, "Memories")
        assert "Memories" in result["albums"]

        with session_scope() as s:
            albums = s.query(Album).filter(Album.name == "Memories").all()
            assert len(albums) == 1
            assert albums[0].archived_at is None


# ── set_scene ───────────────────────────────────────────────────────────────


class TestSetScene:
    def test_sets_scene(self, server, photo_id):
        result = server.set_scene(photo_id, "outdoor")
        assert result["status"] == "ok"
        assert result["scene"] == "outdoor"

    def test_overwrites_scene(self, server, photo_id):
        server.set_scene(photo_id, "indoor")
        result = server.set_scene(photo_id, "portrait")
        assert result["scene"] == "portrait"

    def test_reflected_in_get_photo(self, server, photo_id):
        server.set_scene(photo_id, "landscape")
        photo = server.get_photo(photo_id)
        assert photo["scene"] == "landscape"

    def test_stamps_ai_model(self, server, photo_id):
        server.set_scene(photo_id, "outdoor", model="claude-sonnet-4-20250514")
        rows = server.run_sql(
            f"SELECT ai_model, ai_analyzed_at FROM photos WHERE id = '{photo_id}'"
        )
        assert rows[0]["ai_model"] == "claude-sonnet-4-20250514"
        assert rows[0]["ai_analyzed_at"] is not None


# ── tag_person / untag_person ───────────────────────────────────────────────


class TestPersonOperations:
    def test_tag_person(self, server, photo_id):
        result = server.tag_person(photo_id, "Alice")
        assert result["status"] == "ok"
        assert "Alice" in result["people"]

    def test_tag_person_creates_person(self, server, photo_id):
        server.tag_person(photo_id, "Charlie")
        people = server.list_people()
        names = {p["name"] for p in people}
        assert "Charlie" in names

    def test_tag_person_creates_face_record(self, server, photo_id):
        server.tag_person(photo_id, "Diana")
        with session_scope() as session:
            person = session.query(Person).filter(Person.name == "Diana").first()
            face = (
                session.query(Face)
                .filter(Face.photo_id == photo_id, Face.person_id == person.id)
                .first()
            )
            assert face is not None
            assert face.confidence == 0.0
            assert face.bbox_x == 0.0
            assert face.bbox_y == 0.0
            assert face.bbox_width == 1.0
            assert face.bbox_height == 1.0

    def test_tag_person_idempotent(self, server, photo_id):
        server.tag_person(photo_id, "Eve")
        result = server.tag_person(photo_id, "Eve")
        assert result["people"].count("Eve") == 1

        with session_scope() as session:
            person = session.query(Person).filter(Person.name == "Eve").first()
            faces = (
                session.query(Face)
                .filter(Face.photo_id == photo_id, Face.person_id == person.id)
                .all()
            )
            assert len(faces) == 1

    def test_untag_person(self, server, photo_id):
        server.tag_person(photo_id, "Frank")
        result = server.untag_person(photo_id, "Frank")
        assert "Frank" not in result["people"]

    def test_untag_nonexistent_person(self, server, photo_id):
        result = server.untag_person(photo_id, "Nobody")
        assert result["status"] == "ok"

    def test_untag_deletes_face_record(self, server, photo_id):
        server.tag_person(photo_id, "Grace")
        server.untag_person(photo_id, "Grace")

        with session_scope() as session:
            person = session.query(Person).filter(Person.name == "Grace").first()
            if person:
                faces = (
                    session.query(Face)
                    .filter(Face.photo_id == photo_id, Face.person_id == person.id)
                    .all()
                )
                assert len(faces) == 0

    def test_archived_person_resurrected(self, server, photo_id):
        """Tagging an archived person by name should resurrect them."""
        with session_scope() as s:
            s.add(Person(name="Henry", created_at=datetime.now(UTC), archived_at=datetime.now(UTC)))

        result = server.tag_person(photo_id, "Henry")
        assert "Henry" in result["people"]

        with session_scope() as s:
            people = s.query(Person).filter(Person.name == "Henry").all()
            assert len(people) == 1
            assert people[0].archived_at is None


# ── archived photo guard ────────────────────────────────────────────────────


class TestArchivedPhotoGuard:
    def test_resolve_rejects_archived_photo(self, server, photo_id):
        """_resolve_photo must hide archived photos so writes don't target them."""
        with session_scope() as s:
            photo = s.query(Photo).filter(Photo.id == photo_id).one()
            photo.archived_at = datetime.now(UTC)

        with pytest.raises(ValueError, match="No photo found"):
            server.add_tags(photo_id, ["x"])
        with pytest.raises(ValueError, match="No photo found"):
            server.set_caption(photo_id, "x")


# ── create_event / add_to_event ─────────────────────────────────────────────


class TestEventOperations:
    def test_create_event(self, server, photo_id):
        result = server.create_event("Beach Day", [photo_id])
        assert result["status"] == "ok"
        assert result["event"] == "Beach Day"
        assert result["photo_count"] == 1

    def test_create_event_with_description(self, server, photo_id):
        result = server.create_event("Party", [photo_id], description="Birthday party")
        assert result["status"] == "ok"

    def test_create_event_idempotent(self, server, photo_id):
        server.create_event("Trip", [photo_id])
        result = server.create_event("Trip", [photo_id])
        assert result["photo_count"] == 1

    def test_create_event_reflected_in_get_photo(self, server, photo_id):
        server.create_event("Hike", [photo_id])
        photo = server.get_photo(photo_id)
        assert "Hike" in photo["events"]

    def test_add_to_event(self, server, photo_id):
        result = server.add_to_event(photo_id, "Concert")
        assert result["status"] == "ok"
        assert result["event"] == "Concert"
        assert result["photo_count"] == 1

    def test_add_to_event_creates_event(self, server, photo_id):
        server.add_to_event(photo_id, "New Event")
        photo = server.get_photo(photo_id)
        assert "New Event" in photo["events"]

    def test_create_event_with_invalid_photo_raises(self, server):
        with pytest.raises(ValueError, match="No photo found"):
            server.create_event("Bad Event", ["aaaa_nonexistent"])

    def test_add_to_event_idempotent(self, server, photo_id):
        server.add_to_event(photo_id, "Dinner")
        result = server.add_to_event(photo_id, "Dinner")
        assert result["photo_count"] == 1


# ── batch_add_tags ──────────────────────────────────────────────────────────


class TestBatchAddTags:
    def test_batch_add_tags(self, server, photo_id):
        result = server.batch_add_tags([photo_id], ["batch1", "batch2"])
        assert result["status"] == "ok"
        assert result["succeeded"] == 1
        assert result["failed"] == 0

    def test_batch_with_invalid_id(self, server, photo_id):
        result = server.batch_add_tags([photo_id, "aaaa_nonexistent"], ["tag"])
        assert result["status"] == "partial"
        assert result["succeeded"] == 1
        assert result["failed"] == 1
        assert len(result["errors"]) == 1

    def test_all_invalid_ids_returns_error(self, server):
        result = server.batch_add_tags(["aaaa_bad1", "aaaa_bad2"], ["tag"])
        assert result["status"] == "error"
        assert result["succeeded"] == 0
        assert result["failed"] == 2

    def test_tags_applied_to_photo(self, server, photo_id):
        server.batch_add_tags([photo_id], ["applied"])
        photo = server.get_photo(photo_id)
        assert "applied" in photo["tags"]


# ── batch_set_caption ───────────────────────────────────────────────────────


class TestBatchSetCaption:
    def test_batch_set_caption(self, server, photo_id):
        result = server.batch_set_caption([photo_id], "Batch caption")
        assert result["status"] == "ok"
        assert result["succeeded"] == 1

    def test_batch_with_invalid_id(self, server, photo_id):
        result = server.batch_set_caption([photo_id, "aaaa_nonexistent"], "caption")
        assert result["status"] == "partial"
        assert result["succeeded"] == 1
        assert result["failed"] == 1

    def test_all_invalid_ids_returns_error(self, server):
        result = server.batch_set_caption(["aaaa_bad1", "aaaa_bad2"], "caption")
        assert result["status"] == "error"
        assert result["succeeded"] == 0
        assert result["failed"] == 2

    def test_caption_applied(self, server, photo_id):
        server.batch_set_caption([photo_id], "Verified batch caption")
        photo = server.get_photo(photo_id)
        assert photo["caption"] == "Verified batch caption"
