"""Flexible annotation system for structured image analysis.

This module provides a customizable way to extract structured information
from images using vision-language models. Users can define annotation
"fields" (individual aspects to extract) and group them into "profiles"
for different use cases.

Example:
    # Define a custom profile
    profile = AnnotationProfile(
        name="family_archive",
        fields=[
            AnnotationField("people_count", FieldType.INTEGER,
                "How many people are visible?"),
            AnnotationField("decade", FieldType.ENUM,
                "What decade is this photo from?",
                options=["1950s", "1960s", "1970s", "1980s", "1990s", "2000s"]),
            AnnotationField("occasion", FieldType.STRING,
                "What occasion or event is this?"),
        ]
    )

    # Annotate an image
    result = annotator.annotate(image_path, profile)
    # result.annotations = {"people_count": 3, "decade": "1980s", ...}
"""

import json
import re
import yaml
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Callable


class FieldType(Enum):
    """Types of annotation fields."""
    STRING = "string"       # Free-form text
    INTEGER = "integer"     # Whole number
    FLOAT = "float"         # Decimal number
    BOOLEAN = "boolean"     # Yes/no
    ENUM = "enum"           # One of predefined options
    LIST = "list"           # Comma-separated list of strings
    TEXT = "text"           # Long-form text (paragraphs)


@dataclass
class AnnotationField:
    """A single annotation dimension to extract from an image.

    Attributes:
        name: Unique identifier for this field (e.g., "people_count")
        field_type: The expected type of the response
        prompt: The question/instruction for the VLM
        description: Human-readable description of what this field captures
        options: For ENUM type, the valid options
        default: Default value if extraction fails
        required: Whether this field must be extracted
    """
    name: str
    field_type: FieldType
    prompt: str
    description: str = ""
    options: list[str] = field(default_factory=list)
    default: Any = None
    required: bool = False

    def build_prompt(self) -> str:
        """Build the full prompt for this field."""
        base = self.prompt.strip()

        # Add type-specific instructions
        if self.field_type == FieldType.INTEGER:
            base += "\nRespond with ONLY a number."
        elif self.field_type == FieldType.FLOAT:
            base += "\nRespond with ONLY a decimal number."
        elif self.field_type == FieldType.BOOLEAN:
            base += "\nRespond with ONLY 'yes' or 'no'."
        elif self.field_type == FieldType.ENUM:
            opts = ", ".join(self.options)
            base += f"\nRespond with ONLY one of: {opts}"
        elif self.field_type == FieldType.LIST:
            base += "\nRespond with a comma-separated list."

        return base

    def parse_response(self, response: str) -> Any:
        """Parse VLM response into the appropriate type."""
        response = response.strip()

        if self.field_type == FieldType.INTEGER:
            # Extract first number
            match = re.search(r'-?\d+', response)
            return int(match.group()) if match else self.default

        elif self.field_type == FieldType.FLOAT:
            match = re.search(r'-?\d+\.?\d*', response)
            return float(match.group()) if match else self.default

        elif self.field_type == FieldType.BOOLEAN:
            lower = response.lower()
            if any(x in lower for x in ['yes', 'true', 'correct', 'affirmative']):
                return True
            elif any(x in lower for x in ['no', 'false', 'incorrect', 'negative']):
                return False
            return self.default

        elif self.field_type == FieldType.ENUM:
            # Find which option best matches
            lower = response.lower()
            for opt in self.options:
                if opt.lower() in lower:
                    return opt
            # Fuzzy match - find option with most overlap
            best_match = None
            best_score = 0
            for opt in self.options:
                score = sum(1 for c in opt.lower() if c in lower)
                if score > best_score:
                    best_score = score
                    best_match = opt
            return best_match if best_score > 2 else self.default

        elif self.field_type == FieldType.LIST:
            # Split by comma, clean up
            items = []
            for item in response.split(','):
                item = item.strip().lower()
                item = re.sub(r'^[\d\.\-\*\•]+\s*', '', item)  # Remove bullets
                item = re.sub(r'[^\w\s\-]', '', item)  # Clean special chars
                if item and len(item) > 1:
                    items.append(item)
            return items if items else self.default

        else:  # STRING or TEXT
            return response if response else self.default


@dataclass
class AnnotationProfile:
    """A collection of annotation fields for a specific use case.

    Profiles group related fields together for batch extraction.
    For example, a "family_archive" profile might extract people count,
    decade, occasion, and relationships.
    """
    name: str
    description: str = ""
    fields: list[AnnotationField] = field(default_factory=list)

    def get_field(self, name: str) -> Optional[AnnotationField]:
        """Get a field by name."""
        for f in self.fields:
            if f.name == name:
                return f
        return None


@dataclass
class AnnotationResult:
    """Result of annotating an image with a profile."""
    profile_name: str
    annotations: dict[str, Any] = field(default_factory=dict)
    raw_responses: dict[str, str] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    model: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON storage."""
        return {
            "profile": self.profile_name,
            "annotations": self.annotations,
            "raw_responses": self.raw_responses,
            "errors": self.errors,
            "model": self.model,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AnnotationResult":
        """Create from dictionary."""
        return cls(
            profile_name=data.get("profile", ""),
            annotations=data.get("annotations", {}),
            raw_responses=data.get("raw_responses", {}),
            errors=data.get("errors", {}),
            model=data.get("model", ""),
            timestamp=data.get("timestamp", ""),
        )


# ============================================================================
# Built-in Profiles
# ============================================================================

# Basic quick scan - fast, general purpose
PROFILE_QUICK = AnnotationProfile(
    name="quick",
    description="Fast basic annotation - caption and tags",
    fields=[
        AnnotationField(
            "caption", FieldType.STRING,
            "Describe this image in 1-2 concise sentences.",
            description="Brief description of the image"
        ),
        AnnotationField(
            "tags", FieldType.LIST,
            "List 5-8 relevant single-word tags for this image.",
            description="Searchable keywords"
        ),
    ]
)

# Family photo archive
PROFILE_FAMILY = AnnotationProfile(
    name="family",
    description="Family photo archive - people, dates, occasions",
    fields=[
        AnnotationField(
            "caption", FieldType.TEXT,
            "Describe this photo in 1-2 sentences, focusing on the people and setting.",
            description="Descriptive caption"
        ),
        AnnotationField(
            "people_count", FieldType.INTEGER,
            "How many people are visible in this photo?",
            description="Number of people",
            default=0
        ),
        AnnotationField(
            "has_children", FieldType.BOOLEAN,
            "Are there any children (under ~12 years old) in this photo?",
            description="Children present",
            default=False
        ),
        AnnotationField(
            "decade", FieldType.ENUM,
            "Based on clothing, furniture, photo quality, and styling, what decade is this photo likely from?",
            description="Approximate decade",
            options=["1940s", "1950s", "1960s", "1970s", "1980s", "1990s", "2000s", "2010s", "2020s", "unknown"]
        ),
        AnnotationField(
            "setting", FieldType.ENUM,
            "Where was this photo taken?",
            description="Photo setting",
            options=["indoor-home", "indoor-other", "outdoor-yard", "outdoor-nature", "outdoor-urban", "studio", "unknown"]
        ),
        AnnotationField(
            "occasion", FieldType.STRING,
            "What occasion or event might this photo be from? (e.g., birthday, christmas, vacation, casual, portrait, wedding)",
            description="Type of occasion"
        ),
        AnnotationField(
            "mood", FieldType.ENUM,
            "What is the overall mood or emotional tone of this photo?",
            description="Emotional tone",
            options=["happy", "serious", "playful", "formal", "casual", "somber", "celebratory", "neutral"]
        ),
        AnnotationField(
            "tags", FieldType.LIST,
            "List 5-10 relevant tags for organizing this family photo.",
            description="Searchable tags"
        ),
    ]
)

# Detailed analysis
PROFILE_DETAILED = AnnotationProfile(
    name="detailed",
    description="Comprehensive analysis - objects, scene, composition",
    fields=[
        AnnotationField(
            "caption", FieldType.TEXT,
            "Provide a detailed description of this image, including main subjects, setting, and notable details.",
            description="Detailed description"
        ),
        AnnotationField(
            "objects", FieldType.LIST,
            "List all significant objects visible in this image.",
            description="Visible objects"
        ),
        AnnotationField(
            "scene_type", FieldType.STRING,
            "What type of scene is this? (e.g., portrait, landscape, street, interior, event)",
            description="Scene classification"
        ),
        AnnotationField(
            "colors", FieldType.LIST,
            "What are the dominant colors in this image?",
            description="Color palette"
        ),
        AnnotationField(
            "lighting", FieldType.ENUM,
            "How would you describe the lighting?",
            description="Lighting conditions",
            options=["natural-bright", "natural-soft", "natural-dim", "artificial", "mixed", "flash", "silhouette"]
        ),
        AnnotationField(
            "composition", FieldType.STRING,
            "Briefly describe the composition (e.g., centered subject, rule of thirds, symmetrical).",
            description="Compositional notes"
        ),
        AnnotationField(
            "quality", FieldType.ENUM,
            "Rate the technical quality of this photo.",
            description="Technical quality",
            options=["excellent", "good", "average", "poor", "damaged"]
        ),
        AnnotationField(
            "tags", FieldType.LIST,
            "List 8-12 descriptive tags for this image.",
            description="Searchable tags"
        ),
    ]
)

# Minimal - just essentials
PROFILE_MINIMAL = AnnotationProfile(
    name="minimal",
    description="Minimal annotation - just caption",
    fields=[
        AnnotationField(
            "caption", FieldType.STRING,
            "Describe this image in one sentence.",
            description="Brief caption"
        ),
    ]
)

# Portrait focused
PROFILE_PORTRAIT = AnnotationProfile(
    name="portrait",
    description="Portrait photo analysis - faces, expressions, identity",
    fields=[
        AnnotationField(
            "people_count", FieldType.INTEGER,
            "How many people are in this photo?",
            description="Number of people",
            default=0
        ),
        AnnotationField(
            "ages", FieldType.LIST,
            "Estimate the approximate age range of each person (e.g., 'child', 'teenager', 'young adult', 'middle-aged', 'elderly').",
            description="Age estimates"
        ),
        AnnotationField(
            "expressions", FieldType.LIST,
            "Describe the facial expressions of the people (e.g., 'smiling', 'serious', 'laughing').",
            description="Facial expressions"
        ),
        AnnotationField(
            "pose", FieldType.STRING,
            "Describe how the subjects are posed (e.g., 'formal portrait', 'candid', 'group huddle').",
            description="Pose description"
        ),
        AnnotationField(
            "eye_contact", FieldType.BOOLEAN,
            "Are any subjects making eye contact with the camera?",
            description="Camera eye contact",
            default=False
        ),
        AnnotationField(
            "relationship_guess", FieldType.STRING,
            "If multiple people, what might their relationship be? (e.g., 'family', 'friends', 'colleagues', 'couple')",
            description="Guessed relationship"
        ),
    ]
)


# Registry of built-in profiles
BUILTIN_PROFILES: dict[str, AnnotationProfile] = {
    "quick": PROFILE_QUICK,
    "family": PROFILE_FAMILY,
    "detailed": PROFILE_DETAILED,
    "minimal": PROFILE_MINIMAL,
    "portrait": PROFILE_PORTRAIT,
}


def get_profile(name: str) -> Optional[AnnotationProfile]:
    """Get a profile by name (built-in or custom)."""
    return BUILTIN_PROFILES.get(name)


def list_profiles() -> list[tuple[str, str]]:
    """List all available profiles as (name, description) tuples."""
    return [(name, p.description) for name, p in BUILTIN_PROFILES.items()]


# ============================================================================
# Custom Profile Loading
# ============================================================================

def load_profile_from_yaml(path: Path) -> AnnotationProfile:
    """Load a custom profile from a YAML file.

    Example YAML format:
    ```yaml
    name: my_custom_profile
    description: My custom annotation profile
    fields:
      - name: subject
        type: string
        prompt: What is the main subject of this image?

      - name: era
        type: enum
        prompt: What era is this from?
        options: [ancient, medieval, modern, contemporary]

      - name: keywords
        type: list
        prompt: List relevant keywords
    ```
    """
    with open(path, 'r') as f:
        data = yaml.safe_load(f)

    fields = []
    for field_data in data.get('fields', []):
        field_type = FieldType(field_data.get('type', 'string'))
        fields.append(AnnotationField(
            name=field_data['name'],
            field_type=field_type,
            prompt=field_data['prompt'],
            description=field_data.get('description', ''),
            options=field_data.get('options', []),
            default=field_data.get('default'),
            required=field_data.get('required', False),
        ))

    return AnnotationProfile(
        name=data['name'],
        description=data.get('description', ''),
        fields=fields,
    )


def load_profiles_from_dir(directory: Path) -> dict[str, AnnotationProfile]:
    """Load all custom profiles from a directory."""
    profiles = {}
    if directory.exists():
        for path in directory.glob('*.yaml'):
            try:
                profile = load_profile_from_yaml(path)
                profiles[profile.name] = profile
            except Exception:
                pass  # Skip invalid profiles
        for path in directory.glob('*.yml'):
            try:
                profile = load_profile_from_yaml(path)
                profiles[profile.name] = profile
            except Exception:
                pass
    return profiles
