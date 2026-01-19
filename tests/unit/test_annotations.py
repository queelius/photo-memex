"""Tests for the annotation system."""

import pytest
from pathlib import Path
from tempfile import NamedTemporaryFile

from ptk.ai.annotations import (
    AnnotationField,
    AnnotationProfile,
    AnnotationResult,
    FieldType,
    BUILTIN_PROFILES,
    get_profile,
    list_profiles,
    load_profile_from_yaml,
)


class TestFieldType:
    """Tests for FieldType enum."""

    def test_all_types_defined(self):
        """Verify all expected types exist."""
        assert FieldType.STRING.value == "string"
        assert FieldType.INTEGER.value == "integer"
        assert FieldType.FLOAT.value == "float"
        assert FieldType.BOOLEAN.value == "boolean"
        assert FieldType.ENUM.value == "enum"
        assert FieldType.LIST.value == "list"
        assert FieldType.TEXT.value == "text"


class TestAnnotationField:
    """Tests for AnnotationField."""

    def test_basic_field(self):
        """Test creating a basic string field."""
        field = AnnotationField(
            name="caption",
            field_type=FieldType.STRING,
            prompt="Describe this image.",
        )
        assert field.name == "caption"
        assert field.field_type == FieldType.STRING
        assert "Describe" in field.prompt

    def test_build_prompt_integer(self):
        """Test integer field adds number instruction."""
        field = AnnotationField(
            name="count",
            field_type=FieldType.INTEGER,
            prompt="How many people?",
        )
        prompt = field.build_prompt()
        assert "How many people?" in prompt
        assert "ONLY a number" in prompt

    def test_build_prompt_boolean(self):
        """Test boolean field adds yes/no instruction."""
        field = AnnotationField(
            name="outdoors",
            field_type=FieldType.BOOLEAN,
            prompt="Is this outdoors?",
        )
        prompt = field.build_prompt()
        assert "ONLY 'yes' or 'no'" in prompt

    def test_build_prompt_enum(self):
        """Test enum field lists options."""
        field = AnnotationField(
            name="mood",
            field_type=FieldType.ENUM,
            prompt="What is the mood?",
            options=["happy", "sad", "neutral"],
        )
        prompt = field.build_prompt()
        assert "happy, sad, neutral" in prompt

    def test_build_prompt_list(self):
        """Test list field adds comma-separated instruction."""
        field = AnnotationField(
            name="tags",
            field_type=FieldType.LIST,
            prompt="List tags.",
        )
        prompt = field.build_prompt()
        assert "comma-separated" in prompt

    def test_parse_integer(self):
        """Test parsing integer responses."""
        field = AnnotationField("count", FieldType.INTEGER, "How many?")
        assert field.parse_response("3") == 3
        assert field.parse_response("There are 5 people") == 5
        assert field.parse_response("-2") == -2

    def test_parse_integer_fallback(self):
        """Test integer parsing falls back to default."""
        field = AnnotationField("count", FieldType.INTEGER, "How many?", default=0)
        assert field.parse_response("none") == 0
        assert field.parse_response("") == 0

    def test_parse_float(self):
        """Test parsing float responses."""
        field = AnnotationField("rating", FieldType.FLOAT, "Rate it.")
        assert field.parse_response("3.5") == 3.5
        assert field.parse_response("The rating is 7.2 out of 10") == 7.2

    def test_parse_boolean_yes(self):
        """Test parsing affirmative boolean responses."""
        field = AnnotationField("outdoor", FieldType.BOOLEAN, "Outdoors?")
        assert field.parse_response("yes") is True
        assert field.parse_response("Yes, definitely") is True
        assert field.parse_response("true") is True
        assert field.parse_response("correct") is True

    def test_parse_boolean_no(self):
        """Test parsing negative boolean responses."""
        field = AnnotationField("outdoor", FieldType.BOOLEAN, "Outdoors?")
        assert field.parse_response("no") is False
        assert field.parse_response("No, it's indoor") is False
        assert field.parse_response("false") is False
        assert field.parse_response("negative") is False

    def test_parse_boolean_default(self):
        """Test boolean parsing falls back to default."""
        field = AnnotationField("outdoor", FieldType.BOOLEAN, "Outdoors?", default=None)
        assert field.parse_response("maybe") is None

    def test_parse_enum_exact(self):
        """Test enum parsing with exact match."""
        field = AnnotationField(
            "mood", FieldType.ENUM, "Mood?",
            options=["happy", "sad", "neutral"]
        )
        assert field.parse_response("happy") == "happy"
        assert field.parse_response("The mood is sad") == "sad"

    def test_parse_enum_fuzzy(self):
        """Test enum parsing with fuzzy matching."""
        field = AnnotationField(
            "decade", FieldType.ENUM, "Decade?",
            options=["1970s", "1980s", "1990s"]
        )
        assert field.parse_response("1980") == "1980s"

    def test_parse_list(self):
        """Test parsing comma-separated list."""
        field = AnnotationField("tags", FieldType.LIST, "Tags?")
        result = field.parse_response("beach, sunset, vacation")
        assert "beach" in result
        assert "sunset" in result
        assert "vacation" in result

    def test_parse_list_cleans_bullets(self):
        """Test list parsing removes bullets and numbers."""
        field = AnnotationField("tags", FieldType.LIST, "Tags?")
        result = field.parse_response("1. beach, 2. sunset, * vacation")
        assert "beach" in result
        assert "sunset" in result
        assert "vacation" in result

    def test_parse_string(self):
        """Test string parsing returns as-is."""
        field = AnnotationField("caption", FieldType.STRING, "Caption?")
        assert field.parse_response("A beautiful sunset") == "A beautiful sunset"

    def test_parse_text(self):
        """Test text parsing returns as-is."""
        field = AnnotationField("description", FieldType.TEXT, "Describe?")
        text = "This is a long\nmulti-line description."
        assert field.parse_response(text) == text


class TestAnnotationProfile:
    """Tests for AnnotationProfile."""

    def test_create_profile(self):
        """Test creating a profile with fields."""
        profile = AnnotationProfile(
            name="test",
            description="Test profile",
            fields=[
                AnnotationField("caption", FieldType.STRING, "Caption?"),
                AnnotationField("tags", FieldType.LIST, "Tags?"),
            ]
        )
        assert profile.name == "test"
        assert len(profile.fields) == 2

    def test_get_field(self):
        """Test retrieving a field by name."""
        profile = AnnotationProfile(
            name="test",
            fields=[
                AnnotationField("caption", FieldType.STRING, "Caption?"),
                AnnotationField("tags", FieldType.LIST, "Tags?"),
            ]
        )
        assert profile.get_field("caption") is not None
        assert profile.get_field("caption").name == "caption"
        assert profile.get_field("nonexistent") is None


class TestAnnotationResult:
    """Tests for AnnotationResult."""

    def test_to_dict(self):
        """Test converting result to dictionary."""
        result = AnnotationResult(
            profile_name="test",
            annotations={"caption": "A photo", "count": 3},
            model="llava",
            timestamp="2024-01-01T00:00:00Z",
        )
        d = result.to_dict()
        assert d["profile"] == "test"
        assert d["annotations"]["caption"] == "A photo"
        assert d["model"] == "llava"

    def test_from_dict(self):
        """Test creating result from dictionary."""
        data = {
            "profile": "test",
            "annotations": {"caption": "A photo"},
            "model": "llava",
            "timestamp": "2024-01-01T00:00:00Z",
        }
        result = AnnotationResult.from_dict(data)
        assert result.profile_name == "test"
        assert result.annotations["caption"] == "A photo"


class TestBuiltinProfiles:
    """Tests for built-in profiles."""

    def test_quick_profile_exists(self):
        """Test quick profile exists with expected fields."""
        profile = get_profile("quick")
        assert profile is not None
        assert profile.name == "quick"
        assert profile.get_field("caption") is not None
        assert profile.get_field("tags") is not None

    def test_family_profile_exists(self):
        """Test family profile exists with expected fields."""
        profile = get_profile("family")
        assert profile is not None
        assert profile.get_field("people_count") is not None
        assert profile.get_field("decade") is not None
        assert profile.get_field("has_children") is not None

    def test_detailed_profile_exists(self):
        """Test detailed profile exists."""
        profile = get_profile("detailed")
        assert profile is not None
        assert profile.get_field("objects") is not None
        assert profile.get_field("lighting") is not None

    def test_minimal_profile_exists(self):
        """Test minimal profile exists."""
        profile = get_profile("minimal")
        assert profile is not None
        assert len(profile.fields) == 1

    def test_portrait_profile_exists(self):
        """Test portrait profile exists."""
        profile = get_profile("portrait")
        assert profile is not None
        assert profile.get_field("ages") is not None

    def test_list_profiles(self):
        """Test listing all profiles."""
        profiles = list_profiles()
        assert len(profiles) >= 5
        names = [p[0] for p in profiles]
        assert "quick" in names
        assert "family" in names

    def test_unknown_profile_returns_none(self):
        """Test that unknown profile returns None."""
        assert get_profile("nonexistent") is None


class TestYAMLLoading:
    """Tests for YAML profile loading."""

    def test_load_simple_profile(self, tmp_path):
        """Test loading a simple YAML profile."""
        yaml_content = """
name: test_profile
description: A test profile
fields:
  - name: subject
    type: string
    prompt: What is the main subject?
  - name: count
    type: integer
    prompt: How many items?
    default: 0
"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml_content)

        profile = load_profile_from_yaml(yaml_file)
        assert profile.name == "test_profile"
        assert profile.description == "A test profile"
        assert len(profile.fields) == 2
        assert profile.get_field("subject").field_type == FieldType.STRING
        assert profile.get_field("count").default == 0

    def test_load_enum_profile(self, tmp_path):
        """Test loading a profile with enum field."""
        yaml_content = """
name: enum_test
fields:
  - name: season
    type: enum
    prompt: What season?
    options: [spring, summer, fall, winter]
"""
        yaml_file = tmp_path / "enum.yaml"
        yaml_file.write_text(yaml_content)

        profile = load_profile_from_yaml(yaml_file)
        field = profile.get_field("season")
        assert field.field_type == FieldType.ENUM
        assert "summer" in field.options

    def test_load_profile_with_all_types(self, tmp_path):
        """Test loading a profile with all field types."""
        yaml_content = """
name: comprehensive
fields:
  - name: caption
    type: string
    prompt: Caption?
  - name: count
    type: integer
    prompt: Count?
  - name: rating
    type: float
    prompt: Rating?
  - name: outdoor
    type: boolean
    prompt: Outdoor?
  - name: mood
    type: enum
    prompt: Mood?
    options: [happy, sad]
  - name: tags
    type: list
    prompt: Tags?
  - name: description
    type: text
    prompt: Description?
"""
        yaml_file = tmp_path / "all_types.yaml"
        yaml_file.write_text(yaml_content)

        profile = load_profile_from_yaml(yaml_file)
        assert len(profile.fields) == 7
        assert profile.get_field("caption").field_type == FieldType.STRING
        assert profile.get_field("count").field_type == FieldType.INTEGER
        assert profile.get_field("rating").field_type == FieldType.FLOAT
        assert profile.get_field("outdoor").field_type == FieldType.BOOLEAN
        assert profile.get_field("mood").field_type == FieldType.ENUM
        assert profile.get_field("tags").field_type == FieldType.LIST
        assert profile.get_field("description").field_type == FieldType.TEXT
