"""Integration tests for Phase 2 features (organization, tags, favorites, query)."""

import pytest
from pathlib import Path
from typer.testing import CliRunner

from ptk.cli import app


runner = CliRunner()


@pytest.fixture
def library_with_photos(temp_dir: Path):
    """Create a library with sample photos."""
    from PIL import Image

    library_dir = temp_dir / "library"
    library_dir.mkdir()
    runner.invoke(app, ["init", str(library_dir)])

    photos_dir = temp_dir / "photos"
    photos_dir.mkdir()

    # Create two different images (different colors = different hashes)
    img1 = Image.new("RGB", (100, 100), color="red")
    img1.save(photos_dir / "photo1.jpg")
    img2 = Image.new("RGB", (100, 100), color="blue")
    img2.save(photos_dir / "photo2.jpg")

    import os
    original_cwd = os.getcwd()
    os.chdir(library_dir)

    # Import photos using new unified import command
    runner.invoke(app, ["import", str(photos_dir)])

    yield library_dir

    os.chdir(original_cwd)


def _get_photo_ids(runner, app) -> list[str]:
    """Get all photo IDs from the library."""
    result = runner.invoke(app, ["q", "--format", "ids"])
    ids = [line.strip() for line in result.output.strip().split("\n") if line.strip()]
    return ids


def _get_first_photo_id(runner, app) -> str | None:
    """Get the first photo ID from the library."""
    ids = _get_photo_ids(runner, app)
    return ids[0] if ids else None


# ============================================================================
# Tag Tests
# ============================================================================


def test_set_tag(library_with_photos: Path):
    """Test adding tags to a photo."""
    photo_id = _get_first_photo_id(runner, app)

    assert photo_id is not None
    result = runner.invoke(app, ["set", photo_id, "--tag", "vacation", "--tag", "beach"])
    assert result.exit_code == 0
    assert "Modified" in result.output or "1 photo" in result.output


def test_query_by_tag(library_with_photos: Path):
    """Test querying photos by tag."""
    photo_id = _get_first_photo_id(runner, app)
    assert photo_id is not None

    # Add the tag
    runner.invoke(app, ["set", photo_id, "--tag", "test-tag"])

    # Query by tag
    result = runner.invoke(app, ["q", "--tag", "test-tag", "--format", "ids"])
    assert result.exit_code == 0
    assert photo_id[:12] in result.output  # ID might be truncated


def test_remove_tag(library_with_photos: Path):
    """Test removing tags from a photo."""
    photo_id = _get_first_photo_id(runner, app)
    assert photo_id is not None

    # Add a tag
    runner.invoke(app, ["set", photo_id, "--tag", "removeme"])

    # Remove the tag
    result = runner.invoke(app, ["set", photo_id, "--untag", "removeme"])
    assert result.exit_code == 0

    # Verify tag is gone by querying
    query_result = runner.invoke(app, ["q", "--tag", "removeme", "--format", "count"])
    assert "0" in query_result.output


def test_multiple_tags_and(library_with_photos: Path):
    """Test querying with multiple tags (AND logic)."""
    ids = _get_photo_ids(runner, app)
    assert len(ids) >= 2

    # Tag first photo with both tags
    runner.invoke(app, ["set", ids[0], "--tag", "beach", "--tag", "sunset"])
    # Tag second photo with only one tag
    runner.invoke(app, ["set", ids[1], "--tag", "beach"])

    # Query for photos with BOTH tags
    result = runner.invoke(app, ["q", "--tag", "beach", "--tag", "sunset", "--format", "count"])
    assert result.exit_code == 0
    assert "1" in result.output  # Only first photo has both


# ============================================================================
# Favorites Tests
# ============================================================================


def test_set_favorite(library_with_photos: Path):
    """Test marking a photo as favorite."""
    photo_id = _get_first_photo_id(runner, app)

    assert photo_id is not None
    result = runner.invoke(app, ["set", photo_id, "--favorite"])
    assert result.exit_code == 0


def test_query_favorites(library_with_photos: Path):
    """Test querying favorites."""
    photo_id = _get_first_photo_id(runner, app)
    assert photo_id is not None

    # Mark as favorite
    runner.invoke(app, ["set", photo_id, "--favorite"])

    # Query favorites
    result = runner.invoke(app, ["q", "--favorite", "--format", "count"])
    assert result.exit_code == 0
    assert "1" in result.output


def test_unfavorite(library_with_photos: Path):
    """Test removing favorite status."""
    photo_id = _get_first_photo_id(runner, app)
    assert photo_id is not None

    # Mark as favorite
    runner.invoke(app, ["set", photo_id, "--favorite"])

    # Unfavorite (use --no-favorite)
    result = runner.invoke(app, ["set", photo_id, "--no-favorite"])
    assert result.exit_code == 0

    # Verify no favorites
    query_result = runner.invoke(app, ["q", "--favorite", "--format", "count"])
    assert "0" in query_result.output


# ============================================================================
# Album Tests
# ============================================================================


def test_set_album(library_with_photos: Path):
    """Test adding a photo to an album."""
    photo_id = _get_first_photo_id(runner, app)
    assert photo_id is not None

    result = runner.invoke(app, ["set", photo_id, "--album", "Vacation"])
    assert result.exit_code == 0


def test_query_by_album(library_with_photos: Path):
    """Test querying photos by album."""
    photo_id = _get_first_photo_id(runner, app)
    assert photo_id is not None

    # Add to album
    runner.invoke(app, ["set", photo_id, "--album", "Summer 2020"])

    # Query by album
    result = runner.invoke(app, ["q", "--album", "Summer 2020", "--format", "count"])
    assert result.exit_code == 0
    assert "1" in result.output


# ============================================================================
# Query Tests
# ============================================================================


def test_query_all(library_with_photos: Path):
    """Test querying all photos."""
    result = runner.invoke(app, ["q"])
    assert result.exit_code == 0
    # Should show 2 photos
    assert "2 photo(s)" in result.output


def test_query_format_json(library_with_photos: Path):
    """Test query with JSON format."""
    import json

    result = runner.invoke(app, ["q", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 2


def test_query_format_ids(library_with_photos: Path):
    """Test query with IDs format."""
    result = runner.invoke(app, ["q", "--format", "ids"])
    assert result.exit_code == 0
    ids = [line.strip() for line in result.output.strip().split("\n") if line.strip()]
    assert len(ids) == 2


def test_query_format_count(library_with_photos: Path):
    """Test query with count format."""
    result = runner.invoke(app, ["q", "--format", "count"])
    assert result.exit_code == 0
    assert "2" in result.output


def test_query_limit(library_with_photos: Path):
    """Test query with limit."""
    result = runner.invoke(app, ["q", "--limit", "1", "--format", "count"])
    assert result.exit_code == 0
    assert "1" in result.output


def test_query_sql(library_with_photos: Path):
    """Test raw SQL query."""
    result = runner.invoke(
        app,
        ["q", "--sql", "SELECT id FROM photos WHERE filename = 'photo1.jpg'", "--format", "ids"]
    )
    assert result.exit_code == 0
    # Should find photo1.jpg


def test_query_combined_filters(library_with_photos: Path):
    """Test combining multiple query filters."""
    photo_id = _get_first_photo_id(runner, app)
    assert photo_id is not None

    # Set up: make photo favorite and add tag
    runner.invoke(app, ["set", photo_id, "--favorite", "--tag", "special"])

    # Query with combined filters
    result = runner.invoke(
        app,
        ["q", "--favorite", "--tag", "special", "--format", "count"]
    )
    assert result.exit_code == 0
    assert "1" in result.output


# ============================================================================
# Show Command Tests
# ============================================================================


def test_show_photo(library_with_photos: Path):
    """Test showing photo details."""
    photo_id = _get_first_photo_id(runner, app)
    assert photo_id is not None

    result = runner.invoke(app, ["show", photo_id])
    assert result.exit_code == 0
    assert "photo" in result.output.lower()  # Should show photo details


def test_show_photo_not_found(library_with_photos: Path):
    """Test showing non-existent photo."""
    result = runner.invoke(app, ["show", "nonexistent123"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()
