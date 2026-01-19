"""SQLAlchemy models for the view system.

Storage model for views and annotations:

Views Table:
    Stores view metadata - name, definition (YAML), status, timestamps.
    Each view is a named, versioned computation over photos.

ViewAnnotations Table:
    Stores per-photo annotations for each view.
    Composite key: (photo_id, view_name, field_name)
    This allows multiple views to annotate the same photo independently.

Design decisions:
    - Values stored as JSON strings for flexibility (handles all types)
    - Separate raw_value column for LLM's original response
    - Indexes on (view_name, field_name, value) for efficient filtering
    - Views track their own status and can be incrementally updated
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Any
import json

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Float,
    ForeignKey,
    Index,
    JSON,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

from ptk.db.models import Base


class ViewStatus(str, Enum):
    """Status of a view's computation."""
    DRAFT = "draft"           # Definition exists but never run
    COMPUTING = "computing"   # Currently being computed
    COMPLETE = "complete"     # Fully computed
    PARTIAL = "partial"       # Partially computed (interrupted or incremental)
    STALE = "stale"           # Needs recomputation (photos added/changed)
    ERROR = "error"           # Computation failed


class View(Base):
    """A named, materialized computation over photos.

    Views store:
    - The definition (YAML spec) of what to compute
    - Status of the computation
    - Statistics about coverage
    - Provenance (model used, timestamps)

    Multiple views can coexist, each providing different "layers"
    of annotations over the same photos.
    """

    __tablename__ = "views"

    # Identity
    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    # Definition
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    definition_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    profile_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    selector_yaml: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Computation settings
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    model_host: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(32), default=ViewStatus.DRAFT.value, index=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Statistics
    photo_count: Mapped[int] = mapped_column(Integer, default=0)
    annotation_count: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    computed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    annotations: Mapped[List["ViewAnnotation"]] = relationship(
        "ViewAnnotation",
        back_populates="view",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<View {self.name} v{self.version} ({self.status})>"


class ViewAnnotation(Base):
    """A single annotation value for a photo within a view.

    Each annotation is a (photo_id, view_name, field_name) -> value mapping.
    This allows:
    - Multiple views to annotate the same photo
    - Each view to have multiple fields
    - Efficient querying by any combination

    Values are stored as JSON for type flexibility. The field_type
    column indicates how to interpret the value.
    """

    __tablename__ = "view_annotations"

    # Composite primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    photo_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("photos.id", ondelete="CASCADE"),
        nullable=False
    )
    view_name: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("views.name", ondelete="CASCADE"),
        nullable=False
    )
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)

    # Value storage
    field_type: Mapped[str] = mapped_column(String(32), nullable=False)  # string, integer, etc.
    value_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded value
    raw_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # LLM's raw output

    # Confidence/quality
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Relationships
    view: Mapped["View"] = relationship("View", back_populates="annotations")

    # Indexes for efficient querying
    __table_args__ = (
        # Unique constraint on (photo, view, field)
        Index(
            "ix_view_annotations_unique",
            "photo_id", "view_name", "field_name",
            unique=True
        ),
        # Query by view and field (for filtering)
        Index("ix_view_annotations_view_field", "view_name", "field_name"),
        # Query by photo (for showing all annotations)
        Index("ix_view_annotations_photo", "photo_id"),
        # Query by view (for stats)
        Index("ix_view_annotations_view", "view_name"),
    )

    @property
    def value(self) -> Any:
        """Get the decoded value."""
        return json.loads(self.value_json)

    @value.setter
    def value(self, val: Any) -> None:
        """Set the value (will be JSON encoded)."""
        self.value_json = json.dumps(val)

    def __repr__(self) -> str:
        return f"<ViewAnnotation {self.view_name}.{self.field_name} for {self.photo_id[:8]}...>"


# Convenience function for creating annotations
def create_annotation(
    photo_id: str,
    view_name: str,
    field_name: str,
    field_type: str,
    value: Any,
    raw_response: Optional[str] = None,
    confidence: Optional[float] = None,
) -> ViewAnnotation:
    """Create a ViewAnnotation with proper JSON encoding."""
    from datetime import timezone

    return ViewAnnotation(
        photo_id=photo_id,
        view_name=view_name,
        field_name=field_name,
        field_type=field_type,
        value_json=json.dumps(value),
        raw_response=raw_response,
        confidence=confidence,
        created_at=datetime.now(timezone.utc),
    )
