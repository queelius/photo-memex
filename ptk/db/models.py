"""SQLAlchemy models for ptk database."""

from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Table,
    Index,
    LargeBinary,
    JSON,
)
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


# Many-to-many association tables

photo_tags = Table(
    "photo_tags",
    Base.metadata,
    Column(
        "photo_id",
        String(64),
        ForeignKey("photos.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        Integer,
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Index("ix_photo_tags_photo", "photo_id"),
    Index("ix_photo_tags_tag", "tag_id"),
)

photo_albums = Table(
    "photo_albums",
    Base.metadata,
    Column(
        "photo_id",
        String(64),
        ForeignKey("photos.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "album_id",
        Integer,
        ForeignKey("albums.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("sort_order", Integer, default=0),
    Index("ix_photo_albums_photo", "photo_id"),
    Index("ix_photo_albums_album", "album_id"),
)

photo_events = Table(
    "photo_events",
    Base.metadata,
    Column(
        "photo_id",
        String(64),
        ForeignKey("photos.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "event_id",
        Integer,
        ForeignKey("events.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Index("ix_photo_events_photo", "photo_id"),
    Index("ix_photo_events_event", "event_id"),
)


class Photo(Base):
    """Core photo entity - identified by SHA256 hash."""

    __tablename__ = "photos"

    # Identity (SHA256 hash of file content)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    # File info
    original_path: Mapped[str] = mapped_column(String(4096), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Temporal (from EXIF or file)
    date_taken: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    date_imported: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    date_modified: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # EXIF metadata
    camera_make: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    camera_model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    lens: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    focal_length: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    aperture: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    shutter_speed: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    iso: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Location (GPS)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=True)
    altitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    location_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # AI-generated content
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    objects: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    scene: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    ai_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ai_analyzed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ai_model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Status and flags
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    is_screenshot: Mapped[bool] = mapped_column(Boolean, default=False)
    is_video: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Thumbnail (stored as BLOB for portability)
    thumbnail_data: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    thumbnail_mime: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Import source tracking
    import_source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    tags: Mapped[List["Tag"]] = relationship(
        "Tag", secondary=photo_tags, back_populates="photos"
    )
    albums: Mapped[List["Album"]] = relationship(
        "Album", secondary=photo_albums, back_populates="photos"
    )
    events: Mapped[List["Event"]] = relationship(
        "Event", secondary=photo_events, back_populates="photos"
    )
    faces: Mapped[List["Face"]] = relationship(
        "Face", back_populates="photo", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("ix_photos_date_location", "date_taken", "latitude", "longitude"),
        Index("ix_photos_camera", "camera_make", "camera_model"),
    )

    def __repr__(self) -> str:
        return f"<Photo {self.id[:8]}... {self.filename}>"


class Face(Base):
    """Detected face in a photo."""

    __tablename__ = "faces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    photo_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("photos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("people.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Bounding box (normalized 0-1)
    bbox_x: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_y: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_width: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_height: Mapped[float] = mapped_column(Float, nullable=False)

    # Detection confidence
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    # Face embedding (stored as BLOB - 128 dims for dlib)
    embedding: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)

    # Cluster assignment (before named)
    cluster_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    # Cropped face thumbnail
    thumbnail_data: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)

    # Relationships
    photo: Mapped["Photo"] = relationship("Photo", back_populates="faces")
    person: Mapped[Optional["Person"]] = relationship("Person", back_populates="faces")

    def __repr__(self) -> str:
        return f"<Face {self.id} in photo {self.photo_id[:8]}...>"


class Person(Base):
    """A named person (collection of faces)."""

    __tablename__ = "people"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)
    relationship_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Representative face embedding (average of confirmed faces)
    representative_embedding: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary, nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    faces: Mapped[List["Face"]] = relationship("Face", back_populates="person")

    @property
    def photo_count(self) -> int:
        """Number of unique photos this person appears in."""
        return len(set(f.photo_id for f in self.faces))

    def __repr__(self) -> str:
        return f"<Person {self.id}: {self.name}>"


class Event(Base):
    """A clustered event (birthday party, vacation, wedding, etc.)."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Date range
    start_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    end_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Location (centroid)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    location_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Auto-detected vs manual
    is_auto_detected: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    photos: Mapped[List["Photo"]] = relationship(
        "Photo", secondary=photo_events, back_populates="events"
    )

    def __repr__(self) -> str:
        return f"<Event {self.id}: {self.name}>"


class Album(Base):
    """User-created album."""

    __tablename__ = "albums"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cover_photo_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("photos.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    photos: Mapped[List["Photo"]] = relationship(
        "Photo", secondary=photo_albums, back_populates="albums"
    )

    def __repr__(self) -> str:
        return f"<Album {self.id}: {self.name}>"


class Tag(Base):
    """Tags for organization."""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)

    # Relationships
    photos: Mapped[List["Photo"]] = relationship(
        "Photo", secondary=photo_tags, back_populates="tags"
    )

    def __repr__(self) -> str:
        return f"<Tag {self.id}: {self.name}>"


class PhotoEmbedding(Base):
    """CLIP embeddings for semantic search - separate table for performance."""

    __tablename__ = "photo_embeddings"

    photo_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True
    )
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_photo_embeddings_model", "model_name"),)

    def __repr__(self) -> str:
        return f"<PhotoEmbedding {self.photo_id[:8]}... model={self.model_name}>"
