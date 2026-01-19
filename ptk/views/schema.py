"""YAML DSL schema definitions using Pydantic.

This module defines the structure of the DSL for:
- Fields (atomic extraction units)
- Profiles (collections of fields)
- Selectors (predicates for filtering photos)
- Views (materialized computations)

All definitions are validated at load time to catch errors early.
"""

from enum import Enum
from typing import Any, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator


class FieldType(str, Enum):
    """Types of annotation fields."""
    STRING = "string"
    TEXT = "text"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    ENUM = "enum"
    LIST = "list"


class FieldDef(BaseModel):
    """Definition of a single annotation field.

    Fields are the atomic units of extraction. Each field has:
    - A name (identifier)
    - A type (how to parse/validate the value)
    - A prompt (what to ask the LLM)
    - Optional: description, options (for enum), default value

    Example YAML:
        name: decade
        type: enum
        options: [1970s, 1980s, 1990s, 2000s, 2010s, 2020s]
        prompt: "What decade is this photo from?"
        default: unknown
    """

    name: str = Field(..., min_length=1, max_length=128)
    type: FieldType = Field(default=FieldType.STRING)
    prompt: str = Field(..., min_length=1)
    description: Optional[str] = None
    options: Optional[list[str]] = None  # For enum type
    default: Optional[Any] = None
    required: bool = False

    # Reference to a shared field definition
    ref: Optional[str] = None

    @field_validator("options")
    @classmethod
    def validate_options(cls, v, info):
        """Ensure options are provided for enum type."""
        # Note: can't access other fields directly in field_validator
        return v

    @model_validator(mode="after")
    def validate_enum_has_options(self):
        """Ensure enum fields have options."""
        if self.type == FieldType.ENUM and not self.options:
            raise ValueError("Enum fields must have 'options' defined")
        return self

    def build_prompt(self) -> str:
        """Build the full prompt for LLM extraction."""
        base = self.prompt.strip()

        # Add type-specific instructions
        if self.type == FieldType.INTEGER:
            base += "\nRespond with ONLY a number."
        elif self.type == FieldType.FLOAT:
            base += "\nRespond with ONLY a decimal number."
        elif self.type == FieldType.BOOLEAN:
            base += "\nRespond with ONLY 'yes' or 'no'."
        elif self.type == FieldType.ENUM and self.options:
            opts = ", ".join(self.options)
            base += f"\nRespond with ONLY one of: {opts}"
        elif self.type == FieldType.LIST:
            base += "\nRespond with a comma-separated list."

        return base


class ProfileDef(BaseModel):
    """Definition of an annotation profile (collection of fields).

    Profiles group related fields for batch extraction. Each profile
    represents a particular "lens" for viewing photos.

    Example YAML:
        name: family
        version: 2
        description: "Family photo analysis"
        fields:
          - name: caption
            type: text
            prompt: "Describe this photo"
          - name: people_count
            type: integer
            prompt: "How many people?"
    """

    name: str = Field(..., min_length=1, max_length=128)
    version: int = Field(default=1, ge=1)
    description: Optional[str] = None
    fields: list[FieldDef] = Field(default_factory=list)

    @field_validator("fields")
    @classmethod
    def validate_unique_field_names(cls, v):
        """Ensure all field names are unique within a profile."""
        names = [f.name for f in v]
        if len(names) != len(set(names)):
            raise ValueError("Field names must be unique within a profile")
        return v

    def get_field(self, name: str) -> Optional[FieldDef]:
        """Get a field by name."""
        for f in self.fields:
            if f.name == name:
                return f
        return None


# ============================================================================
# Expression Language for Predicates
# ============================================================================

class ComparisonOp(BaseModel):
    """A comparison operation for predicates.

    Supports: eq, ne, gt, gte, lt, lte, in, contains, matches, exists, between
    """

    eq: Optional[Any] = None
    ne: Optional[Any] = None
    gt: Optional[Union[int, float, str]] = None
    gte: Optional[Union[int, float, str]] = None
    lt: Optional[Union[int, float, str]] = None
    lte: Optional[Union[int, float, str]] = None
    contains: Optional[str] = None
    matches: Optional[str] = None  # regex
    exists: Optional[bool] = None
    between: Optional[list] = None  # [low, high]

    # For 'in' we use a different name since 'in' is a Python keyword
    in_: Optional[list] = Field(default=None, alias="in")

    model_config = {"populate_by_name": True}


class Predicate(BaseModel):
    """A predicate expression for filtering photos.

    Can be:
    - A simple field comparison: {field: value} or {field: {op: value}}
    - A logical combination: {and: [...]} or {or: [...]} or {not: ...}

    Examples:
        # Simple equality
        decade: "1980s"

        # Comparison
        people_count: {gt: 2}

        # Membership
        mood: {in: [happy, playful]}

        # Logical AND
        and:
          - has_children: true
          - decade: {in: [1980s, 1990s]}
    """

    # Logical operators
    and_: Optional[list["Predicate"]] = Field(default=None, alias="and")
    or_: Optional[list["Predicate"]] = Field(default=None, alias="or")
    not_: Optional["Predicate"] = Field(default=None, alias="not")

    # Field comparisons (dynamic keys)
    # These are handled via model_extra
    model_config = {"extra": "allow", "populate_by_name": True}

    def is_logical(self) -> bool:
        """Check if this is a logical (and/or/not) predicate."""
        return self.and_ is not None or self.or_ is not None or self.not_ is not None

    def get_field_comparisons(self) -> dict[str, Any]:
        """Get field comparisons (non-logical fields)."""
        if hasattr(self, "model_extra"):
            return self.model_extra
        return {}


class SelectorDef(BaseModel):
    """Definition of a named selector (predicate).

    Selectors are reusable predicates that can be referenced by name.

    Example YAML:
        name: childhood-80s
        description: "Happy childhood photos from the 80s"
        where:
          and:
            - view.family.has_children: true
            - view.family.decade: {in: [1980s, 1990s]}
    """

    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = None
    where: Predicate


# ============================================================================
# View Definition
# ============================================================================

class ComputeSettings(BaseModel):
    """Settings for view computation."""

    model: str = Field(default="llava")
    host: Optional[str] = None
    port: int = Field(default=11434)
    batch_size: int = Field(default=10, ge=1)
    timeout: int = Field(default=120, ge=1)


class UpdatePolicy(BaseModel):
    """Policy for view updates."""

    on_new_photos: str = Field(default="manual")  # auto, manual
    on_model_change: str = Field(default="manual")
    retention: str = Field(default="forever")  # forever, superseded, duration


class ViewDef(BaseModel):
    """Definition of a materialized view.

    Views are the main unit of computation. They combine:
    - A profile (what to extract)
    - A selector (which photos)
    - Compute settings (model, batching)
    - Update policy (when to recompute)

    Example YAML:
        name: family_v2
        description: "Family analysis with qwen2.5vl"
        profile: family
        selector:
          album: "Family Photos"
        compute:
          model: qwen2.5vl
          host: 192.168.0.225
        policy:
          on_new_photos: auto
    """

    name: str = Field(..., min_length=1, max_length=128)
    version: int = Field(default=1, ge=1)
    description: Optional[str] = None

    # What to compute
    profile: str  # Reference to profile name
    fields: Optional[list[str]] = None  # Subset of profile fields (optional)

    # Which photos
    selector: Optional[Predicate] = None  # If None, all photos

    # How to compute
    compute: ComputeSettings = Field(default_factory=ComputeSettings)

    # Update policy
    policy: UpdatePolicy = Field(default_factory=UpdatePolicy)


# ============================================================================
# Top-level definitions file
# ============================================================================

class PtkDefinitions(BaseModel):
    """Top-level container for all DSL definitions.

    Can be loaded from a single YAML file containing all definitions,
    or assembled from multiple files.

    Example YAML:
        fields:
          - name: decade
            type: enum
            ...
        profiles:
          - name: family
            fields:
              ...
        selectors:
          - name: childhood
            where: ...
        views:
          - name: family_v1
            profile: family
            ...
    """

    fields: list[FieldDef] = Field(default_factory=list)
    profiles: list[ProfileDef] = Field(default_factory=list)
    selectors: list[SelectorDef] = Field(default_factory=list)
    views: list[ViewDef] = Field(default_factory=list)

    def get_profile(self, name: str) -> Optional[ProfileDef]:
        """Get a profile by name."""
        for p in self.profiles:
            if p.name == name:
                return p
        return None

    def get_field(self, name: str) -> Optional[FieldDef]:
        """Get a shared field by name."""
        for f in self.fields:
            if f.name == name:
                return f
        return None

    def get_selector(self, name: str) -> Optional[SelectorDef]:
        """Get a selector by name."""
        for s in self.selectors:
            if s.name == name:
                return s
        return None

    def get_view(self, name: str) -> Optional[ViewDef]:
        """Get a view by name."""
        for v in self.views:
            if v.name == name:
                return v
        return None
