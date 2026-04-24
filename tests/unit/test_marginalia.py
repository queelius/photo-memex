"""Tests for marginalia (notes attachable to any photo)."""

from datetime import UTC, datetime

from photo_memex.db.models import Marginalia, Photo


class TestMarginaliaModel:
    """Verify Marginalia model and relationship to Photo."""

    def test_create_marginalia(self, populated_library, db_session):
        photo = db_session.query(Photo).first()
        note = Marginalia(
            photo_id=photo.id,
            body="This is grandma's house",
            created_at=datetime.now(UTC),
        )
        db_session.add(note)
        db_session.commit()
        assert note.id is not None

    def test_marginalia_body_required(self, populated_library, db_session):
        photo = db_session.query(Photo).first()
        note = Marginalia(
            photo_id=photo.id,
            body="A note",
            created_at=datetime.now(UTC),
        )
        db_session.add(note)
        db_session.commit()
        assert note.body == "A note"

    def test_marginalia_photo_relationship(self, populated_library, db_session):
        photo = db_session.query(Photo).first()
        note = Marginalia(
            photo_id=photo.id,
            body="Note text",
            created_at=datetime.now(UTC),
        )
        db_session.add(note)
        db_session.commit()
        assert note.photo.id == photo.id

    def test_photo_marginalia_list(self, populated_library, db_session):
        photo = db_session.query(Photo).first()
        note1 = Marginalia(
            photo_id=photo.id,
            body="First note",
            created_at=datetime.now(UTC),
        )
        note2 = Marginalia(
            photo_id=photo.id,
            body="Second note",
            created_at=datetime.now(UTC),
        )
        db_session.add_all([note1, note2])
        db_session.commit()
        assert len(photo.marginalia) == 2

    def test_marginalia_survives_photo_deletion(self, populated_library, db_session):
        """Marginalia orphans survive when their photo is deleted (SET NULL)."""
        photo = db_session.query(Photo).first()
        photo_id = photo.id
        note = Marginalia(
            photo_id=photo_id,
            body="Orphan note",
            created_at=datetime.now(UTC),
        )
        db_session.add(note)
        db_session.commit()
        note_id = note.id

        db_session.delete(photo)
        db_session.commit()

        orphan = db_session.query(Marginalia).filter_by(id=note_id).first()
        assert orphan is not None
        assert orphan.photo_id is None
        assert orphan.body == "Orphan note"

    def test_marginalia_has_archived_at(self, populated_library, db_session):
        photo = db_session.query(Photo).first()
        note = Marginalia(
            photo_id=photo.id,
            body="Archivable note",
            created_at=datetime.now(UTC),
        )
        db_session.add(note)
        db_session.commit()
        assert note.archived_at is None
