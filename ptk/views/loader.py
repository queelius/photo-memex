"""YAML loader for DSL definitions.

Loads and validates definitions from:
- Single YAML files
- Directory of YAML files
- Inline YAML strings

Supports:
- Field references (ref: field_name)
- Profile inheritance
- Default profiles (built-in)
"""

from pathlib import Path
from typing import Optional, Union
import yaml

from ptk.views.schema import (
    FieldDef,
    FieldType,
    ProfileDef,
    SelectorDef,
    ViewDef,
    PtkDefinitions,
    Predicate,
    ComputeSettings,
    UpdatePolicy,
)


class DefinitionLoader:
    """Loads and manages DSL definitions.

    Definitions can be loaded from:
    - YAML files in .ptk/ directory
    - Single definition files
    - Inline YAML strings
    - Built-in defaults

    The loader maintains a registry of all loaded definitions,
    resolving references between them.
    """

    def __init__(self):
        self._fields: dict[str, FieldDef] = {}
        self._profiles: dict[str, ProfileDef] = {}
        self._selectors: dict[str, SelectorDef] = {}
        self._views: dict[str, ViewDef] = {}

        # Load built-in defaults
        self._load_builtins()

    def _load_builtins(self) -> None:
        """Load built-in field and profile definitions."""
        # Built-in shared fields
        self._fields["decade"] = FieldDef(
            name="decade",
            type=FieldType.ENUM,
            prompt="Based on clothing, decor, and photo quality, what decade is this from?",
            options=["1940s", "1950s", "1960s", "1970s", "1980s", "1990s", "2000s", "2010s", "2020s", "unknown"],
            default="unknown",
            description="Estimated decade of the photograph",
        )

        # Built-in profiles (matching existing annotation profiles)
        self._profiles["quick"] = ProfileDef(
            name="quick",
            version=1,
            description="Fast basic annotation - caption and tags",
            fields=[
                FieldDef(
                    name="caption",
                    type=FieldType.STRING,
                    prompt="Describe this image in 1-2 concise sentences.",
                    description="Brief description",
                ),
                FieldDef(
                    name="tags",
                    type=FieldType.LIST,
                    prompt="List 5-8 relevant single-word tags for this image.",
                    description="Searchable keywords",
                ),
            ],
        )

        self._profiles["family"] = ProfileDef(
            name="family",
            version=1,
            description="Family photo archive - people, dates, occasions",
            fields=[
                FieldDef(
                    name="caption",
                    type=FieldType.TEXT,
                    prompt="Describe this photo in 1-2 sentences, focusing on people and setting.",
                ),
                FieldDef(
                    name="people_count",
                    type=FieldType.INTEGER,
                    prompt="How many people are visible in this photo?",
                    default=0,
                ),
                FieldDef(
                    name="has_children",
                    type=FieldType.BOOLEAN,
                    prompt="Are there any children (under ~12 years old) in this photo?",
                    default=False,
                ),
                FieldDef(
                    name="decade",
                    type=FieldType.ENUM,
                    prompt="Based on clothing, furniture, photo quality, what decade is this from?",
                    options=["1940s", "1950s", "1960s", "1970s", "1980s", "1990s", "2000s", "2010s", "2020s", "unknown"],
                ),
                FieldDef(
                    name="setting",
                    type=FieldType.ENUM,
                    prompt="Where was this photo taken?",
                    options=["indoor-home", "indoor-other", "outdoor-yard", "outdoor-nature", "outdoor-urban", "studio", "unknown"],
                ),
                FieldDef(
                    name="occasion",
                    type=FieldType.STRING,
                    prompt="What occasion or event is this? (birthday, holiday, vacation, casual, etc.)",
                ),
                FieldDef(
                    name="mood",
                    type=FieldType.ENUM,
                    prompt="What is the overall mood or emotional tone?",
                    options=["happy", "serious", "playful", "formal", "candid", "somber", "celebratory", "neutral"],
                ),
                FieldDef(
                    name="tags",
                    type=FieldType.LIST,
                    prompt="List 5-10 relevant tags for organizing this family photo.",
                ),
            ],
        )

        self._profiles["detailed"] = ProfileDef(
            name="detailed",
            version=1,
            description="Comprehensive analysis - objects, scene, composition",
            fields=[
                FieldDef(
                    name="caption",
                    type=FieldType.TEXT,
                    prompt="Provide a detailed description including main subjects, setting, and notable details.",
                ),
                FieldDef(
                    name="objects",
                    type=FieldType.LIST,
                    prompt="List all significant objects visible in this image.",
                ),
                FieldDef(
                    name="scene_type",
                    type=FieldType.STRING,
                    prompt="What type of scene is this? (portrait, landscape, street, interior, event, etc.)",
                ),
                FieldDef(
                    name="colors",
                    type=FieldType.LIST,
                    prompt="What are the dominant colors in this image?",
                ),
                FieldDef(
                    name="lighting",
                    type=FieldType.ENUM,
                    prompt="How would you describe the lighting?",
                    options=["natural-bright", "natural-soft", "natural-dim", "artificial", "mixed", "flash", "silhouette"],
                ),
                FieldDef(
                    name="composition",
                    type=FieldType.STRING,
                    prompt="Briefly describe the composition (centered, rule-of-thirds, symmetrical, etc.).",
                ),
                FieldDef(
                    name="quality",
                    type=FieldType.ENUM,
                    prompt="Rate the technical quality of this photo.",
                    options=["excellent", "good", "average", "poor", "damaged"],
                ),
                FieldDef(
                    name="tags",
                    type=FieldType.LIST,
                    prompt="List 8-12 descriptive tags for this image.",
                ),
            ],
        )

        self._profiles["minimal"] = ProfileDef(
            name="minimal",
            version=1,
            description="Minimal annotation - just caption",
            fields=[
                FieldDef(
                    name="caption",
                    type=FieldType.STRING,
                    prompt="Describe this image in one sentence.",
                ),
            ],
        )

        self._profiles["portrait"] = ProfileDef(
            name="portrait",
            version=1,
            description="Portrait photo analysis - faces, expressions",
            fields=[
                FieldDef(
                    name="people_count",
                    type=FieldType.INTEGER,
                    prompt="How many people are in this photo?",
                    default=0,
                ),
                FieldDef(
                    name="ages",
                    type=FieldType.LIST,
                    prompt="Estimate age ranges: child, teenager, young-adult, middle-aged, elderly.",
                ),
                FieldDef(
                    name="expressions",
                    type=FieldType.LIST,
                    prompt="Describe facial expressions: smiling, serious, laughing, etc.",
                ),
                FieldDef(
                    name="pose",
                    type=FieldType.STRING,
                    prompt="Describe how subjects are posed: formal portrait, candid, group huddle, etc.",
                ),
                FieldDef(
                    name="eye_contact",
                    type=FieldType.BOOLEAN,
                    prompt="Are any subjects making eye contact with the camera?",
                    default=False,
                ),
                FieldDef(
                    name="relationship_guess",
                    type=FieldType.STRING,
                    prompt="What might their relationship be? (family, friends, colleagues, couple, etc.)",
                ),
            ],
        )

    def load_yaml_string(self, yaml_string: str) -> PtkDefinitions:
        """Load definitions from a YAML string."""
        data = yaml.safe_load(yaml_string)
        return self._parse_definitions(data)

    def load_yaml_file(self, path: Path) -> PtkDefinitions:
        """Load definitions from a single YAML file."""
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return self._parse_definitions(data)

    def load_directory(self, directory: Path) -> PtkDefinitions:
        """Load all definitions from a directory.

        Looks for:
        - fields/*.yaml
        - profiles/*.yaml
        - selectors/*.yaml
        - views/*.yaml
        - ptk-defs.yaml (single file with all definitions)
        """
        all_defs = PtkDefinitions()

        # Check for single definitions file
        single_file = directory / "ptk-defs.yaml"
        if single_file.exists():
            defs = self.load_yaml_file(single_file)
            self._merge_definitions(all_defs, defs)

        # Load from subdirectories
        for subdir, loader in [
            ("fields", self._load_field_file),
            ("profiles", self._load_profile_file),
            ("selectors", self._load_selector_file),
            ("views", self._load_view_file),
        ]:
            subpath = directory / subdir
            if subpath.exists():
                for yaml_file in subpath.glob("*.yaml"):
                    try:
                        result = loader(yaml_file)
                        if isinstance(result, FieldDef):
                            all_defs.fields.append(result)
                        elif isinstance(result, ProfileDef):
                            all_defs.profiles.append(result)
                        elif isinstance(result, SelectorDef):
                            all_defs.selectors.append(result)
                        elif isinstance(result, ViewDef):
                            all_defs.views.append(result)
                    except Exception as e:
                        # Log warning but continue loading
                        print(f"Warning: Failed to load {yaml_file}: {e}")

        # Register all loaded definitions
        for f in all_defs.fields:
            self._fields[f.name] = f
        for p in all_defs.profiles:
            self._profiles[p.name] = p
        for s in all_defs.selectors:
            self._selectors[s.name] = s
        for v in all_defs.views:
            self._views[v.name] = v

        return all_defs

    def _parse_definitions(self, data: dict) -> PtkDefinitions:
        """Parse a dictionary into PtkDefinitions."""
        if not data:
            return PtkDefinitions()

        fields = []
        profiles = []
        selectors = []
        views = []

        # Parse fields
        for field_data in data.get("fields", []):
            fields.append(self._parse_field(field_data))

        # Parse profiles
        for profile_data in data.get("profiles", []):
            profiles.append(self._parse_profile(profile_data))

        # Parse selectors
        for selector_data in data.get("selectors", []):
            selectors.append(self._parse_selector(selector_data))

        # Parse views
        for view_data in data.get("views", []):
            views.append(self._parse_view(view_data))

        return PtkDefinitions(
            fields=fields,
            profiles=profiles,
            selectors=selectors,
            views=views,
        )

    def _parse_field(self, data: dict) -> FieldDef:
        """Parse a field definition."""
        # Handle type as string
        if "type" in data and isinstance(data["type"], str):
            data["type"] = FieldType(data["type"])
        return FieldDef(**data)

    def _parse_profile(self, data: dict) -> ProfileDef:
        """Parse a profile definition."""
        # Parse nested fields
        if "fields" in data:
            parsed_fields = []
            for field_data in data["fields"]:
                # Handle field references
                if "ref" in field_data and len(field_data) == 1:
                    ref_name = field_data["ref"]
                    if ref_name in self._fields:
                        parsed_fields.append(self._fields[ref_name])
                    else:
                        raise ValueError(f"Unknown field reference: {ref_name}")
                else:
                    parsed_fields.append(self._parse_field(field_data))
            data["fields"] = parsed_fields
        return ProfileDef(**data)

    def _parse_selector(self, data: dict) -> SelectorDef:
        """Parse a selector definition."""
        if "where" in data:
            data["where"] = Predicate(**data["where"])
        return SelectorDef(**data)

    def _parse_view(self, data: dict) -> ViewDef:
        """Parse a view definition."""
        if "selector" in data and data["selector"] is not None:
            data["selector"] = Predicate(**data["selector"])
        if "compute" in data:
            data["compute"] = ComputeSettings(**data["compute"])
        if "policy" in data:
            data["policy"] = UpdatePolicy(**data["policy"])
        return ViewDef(**data)

    def _load_field_file(self, path: Path) -> FieldDef:
        """Load a single field from a file."""
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        # Handle top-level "field:" wrapper
        if "field" in data:
            data = data["field"]
        return self._parse_field(data)

    def _load_profile_file(self, path: Path) -> ProfileDef:
        """Load a single profile from a file."""
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        if "profile" in data:
            data = data["profile"]
        return self._parse_profile(data)

    def _load_selector_file(self, path: Path) -> SelectorDef:
        """Load a single selector from a file."""
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        if "selector" in data:
            data = data["selector"]
        return self._parse_selector(data)

    def _load_view_file(self, path: Path) -> ViewDef:
        """Load a single view from a file."""
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        if "view" in data:
            data = data["view"]
        return self._parse_view(data)

    def _merge_definitions(self, target: PtkDefinitions, source: PtkDefinitions) -> None:
        """Merge source definitions into target."""
        target.fields.extend(source.fields)
        target.profiles.extend(source.profiles)
        target.selectors.extend(source.selectors)
        target.views.extend(source.views)

    # Public accessors
    def get_field(self, name: str) -> Optional[FieldDef]:
        """Get a field by name."""
        return self._fields.get(name)

    def get_profile(self, name: str) -> Optional[ProfileDef]:
        """Get a profile by name."""
        return self._profiles.get(name)

    def get_selector(self, name: str) -> Optional[SelectorDef]:
        """Get a selector by name."""
        return self._selectors.get(name)

    def get_view(self, name: str) -> Optional[ViewDef]:
        """Get a view by name."""
        return self._views.get(name)

    def list_profiles(self) -> list[tuple[str, str]]:
        """List all available profiles as (name, description) tuples."""
        return [(name, p.description or "") for name, p in self._profiles.items()]

    def list_views(self) -> list[tuple[str, str]]:
        """List all available views as (name, description) tuples."""
        return [(name, v.description or "") for name, v in self._views.items()]


# Module-level singleton for convenience
_default_loader: Optional[DefinitionLoader] = None


def get_loader() -> DefinitionLoader:
    """Get the default definition loader."""
    global _default_loader
    if _default_loader is None:
        _default_loader = DefinitionLoader()
    return _default_loader


def load_definitions(path: Path) -> PtkDefinitions:
    """Load definitions from a path (file or directory)."""
    loader = get_loader()
    if path.is_dir():
        return loader.load_directory(path)
    else:
        return loader.load_yaml_file(path)
