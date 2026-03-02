"""Tests for arkiv export functionality."""

import json
from pathlib import Path

import pytest
import yaml

from ptk.db.models import Photo, Tag


@pytest.fixture
def library_with_tagged_photo(populated_library, db_session):
    """Create a library with a photo that has tags and a caption."""
    photo = db_session.query(Photo).first()
    photo.caption = "A red test image"
    photo.is_favorite = True
    tag = Tag(name="test-tag")
    db_session.add(tag)
    photo.tags.append(tag)
    db_session.commit()
    return populated_library


class TestArkivExport:
    """Tests for the arkiv export module."""

    def test_creates_output_directory(self, library_with_tagged_photo, tmp_path):
        """Export creates the output directory if it doesn't exist."""
        from ptk.exports.arkiv import export_arkiv

        output_dir = tmp_path / "arkiv-out"
        export_arkiv(output_dir)
        assert output_dir.is_dir()

    def test_creates_readme(self, library_with_tagged_photo, tmp_path):
        """Export creates a README.md with YAML frontmatter."""
        from ptk.exports.arkiv import export_arkiv

        output_dir = tmp_path / "arkiv-out"
        export_arkiv(output_dir)

        readme = output_dir / "README.md"
        assert readme.exists()
        content = readme.read_text()
        assert content.startswith("---\n")
        # Parse frontmatter
        parts = content.split("---\n", 2)
        assert len(parts) >= 3
        frontmatter = yaml.safe_load(parts[1])
        assert "generator" in frontmatter
        assert frontmatter["generator"].startswith("ptk")

    def test_readme_contains_photo_count(self, library_with_tagged_photo, tmp_path):
        """README description includes the number of photos."""
        from ptk.exports.arkiv import export_arkiv

        output_dir = tmp_path / "arkiv-out"
        count = export_arkiv(output_dir)

        readme = output_dir / "README.md"
        content = readme.read_text()
        parts = content.split("---\n", 2)
        frontmatter = yaml.safe_load(parts[1])
        assert f"{count} photo" in frontmatter["description"]

    def test_readme_contents_list(self, library_with_tagged_photo, tmp_path):
        """README frontmatter lists photos.jsonl in contents."""
        from ptk.exports.arkiv import export_arkiv

        output_dir = tmp_path / "arkiv-out"
        export_arkiv(output_dir)

        readme = output_dir / "README.md"
        content = readme.read_text()
        parts = content.split("---\n", 2)
        frontmatter = yaml.safe_load(parts[1])
        assert "contents" in frontmatter
        paths = [c["path"] for c in frontmatter["contents"]]
        assert "photos.jsonl" in paths

    def test_creates_jsonl(self, library_with_tagged_photo, tmp_path):
        """Export creates a photos.jsonl file."""
        from ptk.exports.arkiv import export_arkiv

        output_dir = tmp_path / "arkiv-out"
        export_arkiv(output_dir)

        jsonl_path = output_dir / "photos.jsonl"
        assert jsonl_path.exists()

    def test_jsonl_one_record_per_photo(self, library_with_tagged_photo, tmp_path, db_session):
        """JSONL file has exactly one record per photo."""
        from ptk.exports.arkiv import export_arkiv

        output_dir = tmp_path / "arkiv-out"
        count = export_arkiv(output_dir)

        jsonl_path = output_dir / "photos.jsonl"
        lines = [line for line in jsonl_path.read_text().strip().split("\n") if line]
        assert len(lines) == count

        total_photos = db_session.query(Photo).count()
        assert count == total_photos

    def test_jsonl_record_has_required_fields(self, library_with_tagged_photo, tmp_path):
        """Each JSONL record has mimetype, uri, and metadata fields."""
        from ptk.exports.arkiv import export_arkiv

        output_dir = tmp_path / "arkiv-out"
        export_arkiv(output_dir)

        jsonl_path = output_dir / "photos.jsonl"
        record = json.loads(jsonl_path.read_text().strip().split("\n")[0])

        assert "mimetype" in record
        assert "uri" in record
        assert "metadata" in record

    def test_jsonl_metadata_sha256(self, library_with_tagged_photo, tmp_path, db_session):
        """metadata.sha256 is the 64-character photo ID."""
        from ptk.exports.arkiv import export_arkiv

        output_dir = tmp_path / "arkiv-out"
        export_arkiv(output_dir)

        jsonl_path = output_dir / "photos.jsonl"
        record = json.loads(jsonl_path.read_text().strip().split("\n")[0])

        photo = db_session.query(Photo).first()
        assert record["metadata"]["sha256"] == photo.id
        assert len(record["metadata"]["sha256"]) == 64

    def test_jsonl_metadata_tags(self, library_with_tagged_photo, tmp_path):
        """metadata.tags contains the tag names."""
        from ptk.exports.arkiv import export_arkiv

        output_dir = tmp_path / "arkiv-out"
        export_arkiv(output_dir)

        jsonl_path = output_dir / "photos.jsonl"
        record = json.loads(jsonl_path.read_text().strip().split("\n")[0])

        assert "tags" in record["metadata"]
        assert "test-tag" in record["metadata"]["tags"]

    def test_jsonl_metadata_caption(self, library_with_tagged_photo, tmp_path):
        """metadata.caption is set when the photo has a caption."""
        from ptk.exports.arkiv import export_arkiv

        output_dir = tmp_path / "arkiv-out"
        export_arkiv(output_dir)

        jsonl_path = output_dir / "photos.jsonl"
        record = json.loads(jsonl_path.read_text().strip().split("\n")[0])

        assert record["metadata"]["caption"] == "A red test image"

    def test_jsonl_uri_starts_with_file(self, library_with_tagged_photo, tmp_path):
        """uri starts with file:///."""
        from ptk.exports.arkiv import export_arkiv

        output_dir = tmp_path / "arkiv-out"
        export_arkiv(output_dir)

        jsonl_path = output_dir / "photos.jsonl"
        record = json.loads(jsonl_path.read_text().strip().split("\n")[0])

        assert record["uri"].startswith("file:///")

    def test_jsonl_mimetype(self, library_with_tagged_photo, tmp_path, db_session):
        """mimetype comes from photo.mime_type."""
        from ptk.exports.arkiv import export_arkiv

        output_dir = tmp_path / "arkiv-out"
        export_arkiv(output_dir)

        jsonl_path = output_dir / "photos.jsonl"
        record = json.loads(jsonl_path.read_text().strip().split("\n")[0])

        photo = db_session.query(Photo).first()
        assert record["mimetype"] == photo.mime_type

    def test_creates_schema_yaml(self, library_with_tagged_photo, tmp_path):
        """Export creates a schema.yaml file."""
        from ptk.exports.arkiv import export_arkiv

        output_dir = tmp_path / "arkiv-out"
        export_arkiv(output_dir)

        schema_path = output_dir / "schema.yaml"
        assert schema_path.exists()

    def test_schema_has_photos_key(self, library_with_tagged_photo, tmp_path):
        """schema.yaml has a 'photos' key with metadata_keys."""
        from ptk.exports.arkiv import export_arkiv

        output_dir = tmp_path / "arkiv-out"
        export_arkiv(output_dir)

        schema_path = output_dir / "schema.yaml"
        schema = yaml.safe_load(schema_path.read_text())

        assert "photos" in schema
        assert "metadata_keys" in schema["photos"]

    def test_schema_metadata_keys_types(self, library_with_tagged_photo, tmp_path):
        """schema.yaml metadata_keys contain type info for each key."""
        from ptk.exports.arkiv import export_arkiv

        output_dir = tmp_path / "arkiv-out"
        export_arkiv(output_dir)

        schema_path = output_dir / "schema.yaml"
        schema = yaml.safe_load(schema_path.read_text())

        metadata_keys = schema["photos"]["metadata_keys"]
        # sha256 should always be present
        assert "sha256" in metadata_keys
        assert metadata_keys["sha256"] == "string"

    def test_null_fields_omitted(self, populated_library, db_session, tmp_path):
        """None/null fields are omitted from metadata."""
        from ptk.exports.arkiv import export_arkiv

        # The default photo has no caption, no tags, etc.
        output_dir = tmp_path / "arkiv-out"
        export_arkiv(output_dir)

        jsonl_path = output_dir / "photos.jsonl"
        record = json.loads(jsonl_path.read_text().strip().split("\n")[0])

        metadata = record["metadata"]
        # caption is None on the default photo, should not be in metadata
        assert "caption" not in metadata
        # tags should not be present if empty
        assert "tags" not in metadata

    def test_is_favorite_in_metadata(self, library_with_tagged_photo, tmp_path):
        """metadata.is_favorite is present when True."""
        from ptk.exports.arkiv import export_arkiv

        output_dir = tmp_path / "arkiv-out"
        export_arkiv(output_dir)

        jsonl_path = output_dir / "photos.jsonl"
        record = json.loads(jsonl_path.read_text().strip().split("\n")[0])

        assert record["metadata"]["is_favorite"] is True

    def test_returns_photo_count(self, library_with_tagged_photo, tmp_path, db_session):
        """export_arkiv returns the number of exported photos."""
        from ptk.exports.arkiv import export_arkiv

        output_dir = tmp_path / "arkiv-out"
        count = export_arkiv(output_dir)

        total = db_session.query(Photo).count()
        assert count == total
        assert count > 0

    def test_custom_title(self, library_with_tagged_photo, tmp_path):
        """Custom title appears in README frontmatter."""
        from ptk.exports.arkiv import export_arkiv

        output_dir = tmp_path / "arkiv-out"
        export_arkiv(output_dir, title="My Photo Archive")

        readme = output_dir / "README.md"
        content = readme.read_text()
        parts = content.split("---\n", 2)
        frontmatter = yaml.safe_load(parts[1])
        assert frontmatter["name"] == "My Photo Archive"

    def test_tags_are_sorted(self, populated_library, db_session, tmp_path):
        """Tags in metadata are sorted alphabetically."""
        from ptk.exports.arkiv import export_arkiv

        photo = db_session.query(Photo).first()
        tag_z = Tag(name="zebra")
        tag_a = Tag(name="alpha")
        db_session.add_all([tag_z, tag_a])
        photo.tags.extend([tag_z, tag_a])
        db_session.commit()

        output_dir = tmp_path / "arkiv-out"
        export_arkiv(output_dir)

        jsonl_path = output_dir / "photos.jsonl"
        record = json.loads(jsonl_path.read_text().strip().split("\n")[0])

        tags = record["metadata"]["tags"]
        assert tags == sorted(tags)
        assert tags == ["alpha", "zebra"]
