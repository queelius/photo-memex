"""SQLAlchemy models for ptk database."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class SoftDeleteMixin:
    """Adds archived_at column for soft delete (ecosystem contract).

    All memex-family record tables carry this column. Default queries
    filter WHERE archived_at IS NULL. Hard delete is opt-in.
    """

    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )


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


class Photo(SoftDeleteMixin, Base):
    """Core photo entity - identified by SHA256 hash."""

    __tablename__ = "photos"

    # Identity (SHA256 hash of file content)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    # File info
    original_path: Mapped[str] = mapped_column(String(4096), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Temporal (from EXIF or file)
    date_taken: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    date_imported: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    date_modified: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # EXIF metadata
    camera_make: Mapped[str | None] = mapped_column(String(128), nullable=True)
    camera_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lens: Mapped[str | None] = mapped_column(String(128), nullable=True)
    focal_length: Mapped[float | None] = mapped_column(Float, nullable=True)
    aperture: Mapped[float | None] = mapped_column(Float, nullable=True)
    shutter_speed: Mapped[str | None] = mapped_column(String(32), nullable=True)
    iso: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Location (GPS)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    altitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    city: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # AI-generated content (populated via MCP by Claude Code)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    objects: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    scene: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ai_analyzed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ai_model: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Status and flags
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    is_screenshot: Mapped[bool] = mapped_column(Boolean, default=False)
    is_video: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Thumbnail (stored as BLOB for portability)
    thumbnail_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    thumbnail_mime: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Import source tracking
    import_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    tags: Mapped[list["Tag"]] = relationship(
        "Tag", secondary=photo_tags, back_populates="photos"
    )
    albums: Mapped[list["Album"]] = relationship(
        "Album", secondary=photo_albums, back_populates="photos"
    )
    events: Mapped[list["Event"]] = relationship(
        "Event", secondary=photo_events, back_populates="photos"
    )
    faces: Mapped[list["Face"]] = relationship(
        "Face", back_populates="photo", cascade="all, delete-orphan"
    )
    marginalia: Mapped[list["Marginalia"]] = relationship(
        "Marginalia", back_populates="photo", cascade="save-update, merge"
    )

    # Indexes
    __table_args__ = (
        Index("ix_photos_date_location", "date_taken", "latitude", "longitude"),
        Index("ix_photos_camera", "camera_make", "camera_model"),
    )

    def __repr__(self) -> str:
        return f"<Photo {self.id[:8]}... {self.filename}>"


class Face(SoftDeleteMixin, Base):
    """A face linked to a photo, optionally identified as a person.

    For manual identification (via MCP tag_person), bbox is (0,0,1,1) full-frame
    and confidence is 0.0. Future face detection can populate real values.
    """

    __tablename__ = "faces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    photo_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("photos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("people.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Bounding box (normalized 0-1)
    bbox_x: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_y: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_width: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_height: Mapped[float] = mapped_column(Float, nullable=False)

    # Detection confidence (0.0 = manual identification)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    # Relationships
    photo: Mapped["Photo"] = relationship("Photo", back_populates="faces")
    person: Mapped["Person | None"] = relationship("Person", back_populates="faces")

    def __repr__(self) -> str:
        return f"<Face {self.id} in photo {self.photo_id[:8]}...>"


class Person(SoftDeleteMixin, Base):
    """A named person (collection of faces)."""

    __tablename__ = "people"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    faces: Mapped[list["Face"]] = relationship("Face", back_populates="person")

    @property
    def photo_count(self) -> int:
        """Number of unique non-archived photos this person appears in."""
        return len({f.photo_id for f in self.faces if f.photo and f.photo.archived_at is None})

    def __repr__(self) -> str:
        return f"<Person {self.id}: {self.name}>"


class Event(SoftDeleteMixin, Base):
    """A clustered event (birthday party, vacation, wedding, etc.)."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Date range
    start_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    end_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Location (centroid)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_name: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Auto-detected vs manual
    is_auto_detected: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    photos: Mapped[list["Photo"]] = relationship(
        "Photo", secondary=photo_events, back_populates="events"
    )

    def __repr__(self) -> str:
        return f"<Event {self.id}: {self.name}>"


class Album(SoftDeleteMixin, Base):
    """User-created album."""

    __tablename__ = "albums"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_photo_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("photos.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    photos: Mapped[list["Photo"]] = relationship(
        "Photo", secondary=photo_albums, back_populates="albums"
    )

    def __repr__(self) -> str:
        return f"<Album {self.id}: {self.name}>"


class Tag(SoftDeleteMixin, Base):
    """Tags for organization."""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)

    # Relationships
    photos: Mapped[list["Photo"]] = relationship(
        "Photo", secondary=photo_tags, back_populates="tags"
    )

    def __repr__(self) -> str:
        return f"<Tag {self.id}: {self.name}>"


class Marginalia(SoftDeleteMixin, Base):
    """Free-form note attachable to a photo. Survives photo deletion (orphan survival)."""

    __tablename__ = "marginalia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    photo_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("photos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    photo: Mapped["Photo | None"] = relationship("Photo", back_populates="marginalia")

    def __repr__(self) -> str:
        target = f"photo {self.photo_id[:8]}..." if self.photo_id else "orphan"
        return f"<Marginalia {self.id} on {target}>"
