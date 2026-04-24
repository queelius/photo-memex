"""Tests for photo_memex.db.models."""

import pytest
from datetime import datetime, timezone

from photo_memex.db.models import Photo, Face, Person, Album, Tag, Event


def test_photo_creation(db_session):
    """Test creating a Photo record."""
    now = datetime.now(timezone.utc)
    photo = Photo(
        id="a" * 64,
        original_path="/test/photo.jpg",
        filename="photo.jpg",
        file_size=1024,
        mime_type="image/jpeg",
        date_imported=now,
    )

    db_session.add(photo)
    db_session.commit()

    # Query it back
    result = db_session.query(Photo).filter_by(id="a" * 64).first()
    assert result is not None
    assert result.filename == "photo.jpg"
    assert result.file_size == 1024


def test_photo_with_metadata(db_session):
    """Test Photo with full metadata."""
    now = datetime.now(timezone.utc)
    photo = Photo(
        id="b" * 64,
        original_path="/test/photo2.jpg",
        filename="photo2.jpg",
        file_size=2048,
        mime_type="image/jpeg",
        width=1920,
        height=1080,
        date_taken=now,
        date_imported=now,
        camera_make="Canon",
        camera_model="EOS R5",
        latitude=37.7749,
        longitude=-122.4194,
        is_favorite=True,
    )

    db_session.add(photo)
    db_session.commit()

    result = db_session.query(Photo).filter_by(id="b" * 64).first()
    assert result.width == 1920
    assert result.camera_make == "Canon"
    assert result.is_favorite is True


def test_photo_tag_relationship(db_session):
    """Test Photo-Tag many-to-many relationship."""
    now = datetime.now(timezone.utc)

    tag = Tag(name="vacation")
    photo = Photo(
        id="c" * 64,
        original_path="/test/photo3.jpg",
        filename="photo3.jpg",
        file_size=1024,
        mime_type="image/jpeg",
        date_imported=now,
    )
    photo.tags.append(tag)

    db_session.add(photo)
    db_session.commit()

    # Query and check relationship
    result = db_session.query(Photo).filter_by(id="c" * 64).first()
    assert len(result.tags) == 1
    assert result.tags[0].name == "vacation"

    # Check reverse relationship
    tag_result = db_session.query(Tag).filter_by(name="vacation").first()
    assert len(tag_result.photos) == 1


def test_person_face_relationship(db_session):
    """Test Person-Face relationship."""
    now = datetime.now(timezone.utc)

    person = Person(name="John Doe", created_at=now)
    photo = Photo(
        id="d" * 64,
        original_path="/test/photo4.jpg",
        filename="photo4.jpg",
        file_size=1024,
        mime_type="image/jpeg",
        date_imported=now,
    )
    face = Face(
        photo=photo,
        person=person,
        bbox_x=0.1,
        bbox_y=0.2,
        bbox_width=0.3,
        bbox_height=0.4,
        confidence=0.95,
    )

    db_session.add_all([person, photo, face])
    db_session.commit()

    # Check relationships
    result_person = db_session.query(Person).filter_by(name="John Doe").first()
    assert len(result_person.faces) == 1
    assert result_person.photo_count == 1


def test_album_creation(db_session):
    """Test Album creation and photo relationship."""
    now = datetime.now(timezone.utc)

    album = Album(name="Summer 2023", created_at=now, updated_at=now)
    photo = Photo(
        id="e" * 64,
        original_path="/test/photo5.jpg",
        filename="photo5.jpg",
        file_size=1024,
        mime_type="image/jpeg",
        date_imported=now,
    )
    album.photos.append(photo)

    db_session.add(album)
    db_session.commit()

    result = db_session.query(Album).filter_by(name="Summer 2023").first()
    assert len(result.photos) == 1


def test_photo_repr():
    """Test Photo string representation."""
    photo = Photo(
        id="f" * 64,
        original_path="/test/photo.jpg",
        filename="photo.jpg",
        file_size=1024,
        mime_type="image/jpeg",
        date_imported=datetime.now(timezone.utc),
    )

    repr_str = repr(photo)
    assert "Photo" in repr_str
    assert "photo.jpg" in repr_str
