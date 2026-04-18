"""Tests for soft delete (archived_at) on all record tables."""

from datetime import UTC, datetime

from ptk.db.models import Album, Event, Face, Person, Photo, Tag


class TestSoftDeleteColumns:
    """Verify archived_at column exists and defaults to None."""

    def test_photo_has_archived_at(self, populated_library, db_session):
        photo = db_session.query(Photo).first()
        assert photo.archived_at is None

    def test_photo_can_be_archived(self, populated_library, db_session):
        photo = db_session.query(Photo).first()
        photo.archived_at = datetime.now(UTC)
        db_session.commit()

        reloaded = db_session.query(Photo).filter_by(id=photo.id).first()
        assert reloaded.archived_at is not None

    def test_tag_has_archived_at(self, populated_library, db_session):
        tag = Tag(name="test-archive")
        db_session.add(tag)
        db_session.commit()
        assert tag.archived_at is None

    def test_album_has_archived_at(self, populated_library, db_session):
        now = datetime.now(UTC)
        album = Album(name="test-archive", created_at=now, updated_at=now)
        db_session.add(album)
        db_session.commit()
        assert album.archived_at is None

    def test_event_has_archived_at(self, populated_library, db_session):
        event = Event(name="test-archive", is_auto_detected=False)
        db_session.add(event)
        db_session.commit()
        assert event.archived_at is None

    def test_person_has_archived_at(self, populated_library, db_session):
        person = Person(name="Test Person", created_at=datetime.now(UTC))
        db_session.add(person)
        db_session.commit()
        assert person.archived_at is None

    def test_face_has_archived_at(self, populated_library, db_session):
        photo = db_session.query(Photo).first()
        face = Face(
            photo_id=photo.id,
            bbox_x=0.0, bbox_y=0.0, bbox_width=1.0, bbox_height=1.0,
            confidence=0.0,
        )
        db_session.add(face)
        db_session.commit()
        assert face.archived_at is None


class TestQueryBuilderFiltersArchived:
    """QueryBuilder should exclude archived photos by default."""

    def test_excludes_archived_in_sql(self, populated_library):
        from ptk.query import QueryBuilder

        builder = QueryBuilder()
        sql, params = builder.build()
        assert "archived_at IS NULL" in sql

    def test_no_results_when_all_archived(self, populated_library, db_session):
        from ptk.query import QueryBuilder, execute_query

        photo = db_session.query(Photo).first()
        photo.archived_at = datetime.now(UTC)
        db_session.commit()

        builder = QueryBuilder()
        result = execute_query(db_session, builder)
        assert result.count == 0
