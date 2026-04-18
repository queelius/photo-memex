"""Integration tests for ptk CLI."""

import pytest
from pathlib import Path
from typer.testing import CliRunner

from ptk.cli import app
from ptk.core.constants import DEFAULT_DATABASE_NAME


runner = CliRunner()


def test_version():
    """Test --version flag."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "photo-memex version" in result.output


def test_help():
    """Test --help flag."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "photo-memex" in result.output


def test_init_creates_database(temp_dir: Path):
    """Test that init creates a database."""
    result = runner.invoke(app, ["init", str(temp_dir)])

    assert result.exit_code == 0
    assert "Initialized" in result.output
    assert (temp_dir / DEFAULT_DATABASE_NAME).exists()


def test_init_fails_if_exists(temp_dir: Path):
    """Test that init fails if library exists."""
    # First init
    runner.invoke(app, ["init", str(temp_dir)])

    # Second init should fail
    result = runner.invoke(app, ["init", str(temp_dir)])
    assert result.exit_code == 1
    assert "Library exists" in result.output or "already exists" in result.output


def test_init_force_overwrites(temp_dir: Path):
    """Test that init --force overwrites existing library."""
    runner.invoke(app, ["init", str(temp_dir)])
    result = runner.invoke(app, ["init", "--force", str(temp_dir)])

    assert result.exit_code == 0
    assert "Initialized" in result.output


def test_stats_empty_library(temp_dir: Path):
    """Test stats on empty library."""
    runner.invoke(app, ["init", str(temp_dir)])

    # Change to library directory for stats command
    import os
    original_cwd = os.getcwd()
    os.chdir(temp_dir)

    try:
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "Total photos" in result.output or "0" in result.output
    finally:
        os.chdir(original_cwd)


def test_query_empty_library(temp_dir: Path):
    """Test query on empty library."""
    runner.invoke(app, ["init", str(temp_dir)])

    import os
    original_cwd = os.getcwd()
    os.chdir(temp_dir)

    try:
        result = runner.invoke(app, ["q"])
        assert result.exit_code == 0
        assert "No photos found" in result.output
    finally:
        os.chdir(original_cwd)


def test_import_directory(temp_dir: Path, sample_image: Path):
    """Test importing from a directory."""
    import shutil

    # Setup library
    library_dir = temp_dir / "library"
    library_dir.mkdir()
    runner.invoke(app, ["init", str(library_dir)])

    # Setup photos directory
    photos_dir = temp_dir / "photos"
    photos_dir.mkdir()
    shutil.copy(sample_image, photos_dir / "photo1.jpg")

    import os
    original_cwd = os.getcwd()
    os.chdir(library_dir)

    try:
        result = runner.invoke(app, ["import", str(photos_dir)])
        assert result.exit_code == 0
        assert "Imported: 1" in result.output
    finally:
        os.chdir(original_cwd)


def test_import_dry_run(temp_dir: Path, sample_image: Path):
    """Test import --dry-run."""
    import shutil

    library_dir = temp_dir / "library"
    library_dir.mkdir()
    runner.invoke(app, ["init", str(library_dir)])

    photos_dir = temp_dir / "photos"
    photos_dir.mkdir()
    shutil.copy(sample_image, photos_dir / "photo1.jpg")

    import os
    original_cwd = os.getcwd()
    os.chdir(library_dir)

    try:
        result = runner.invoke(app, ["import", "--dry-run", str(photos_dir)])
        assert result.exit_code == 0
        assert "Dry run" in result.output

        # Check that nothing was actually imported
        query_result = runner.invoke(app, ["q"])
        assert "No photos found" in query_result.output
    finally:
        os.chdir(original_cwd)


def test_show_photo(temp_dir: Path, sample_image: Path):
    """Test showing photo details."""
    import shutil

    library_dir = temp_dir / "library"
    library_dir.mkdir()
    runner.invoke(app, ["init", str(library_dir)])

    photos_dir = temp_dir / "photos"
    photos_dir.mkdir()
    shutil.copy(sample_image, photos_dir / "photo1.jpg")

    import os
    original_cwd = os.getcwd()
    os.chdir(library_dir)

    try:
        # Import first
        runner.invoke(app, ["import", str(photos_dir)])

        # Query to get the IDs
        query_result = runner.invoke(app, ["q", "--format", "ids"])

        # Get the first ID
        photo_id = query_result.output.strip().split("\n")[0].strip()
        if not photo_id or photo_id == "No photos found.":
            pytest.fail("Could not find photo ID in query output")

        # Show the photo
        result = runner.invoke(app, ["show", photo_id])
        assert result.exit_code == 0
        assert "photo1.jpg" in result.output
    finally:
        os.chdir(original_cwd)


def test_query_with_format_json(temp_dir: Path, sample_image: Path):
    """Test query with JSON format."""
    import shutil
    import json

    library_dir = temp_dir / "library"
    library_dir.mkdir()
    runner.invoke(app, ["init", str(library_dir)])

    photos_dir = temp_dir / "photos"
    photos_dir.mkdir()
    shutil.copy(sample_image, photos_dir / "photo1.jpg")

    import os
    original_cwd = os.getcwd()
    os.chdir(library_dir)

    try:
        runner.invoke(app, ["import", str(photos_dir)])
        result = runner.invoke(app, ["q", "--format", "json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["filename"] == "photo1.jpg"
    finally:
        os.chdir(original_cwd)


def test_query_with_format_count(temp_dir: Path, sample_image: Path):
    """Test query with count format."""
    import shutil

    library_dir = temp_dir / "library"
    library_dir.mkdir()
    runner.invoke(app, ["init", str(library_dir)])

    photos_dir = temp_dir / "photos"
    photos_dir.mkdir()
    shutil.copy(sample_image, photos_dir / "photo1.jpg")

    import os
    original_cwd = os.getcwd()
    os.chdir(library_dir)

    try:
        runner.invoke(app, ["import", str(photos_dir)])
        result = runner.invoke(app, ["q", "--format", "count"])

        assert result.exit_code == 0
        assert "1" in result.output
    finally:
        os.chdir(original_cwd)


def test_set_favorite(temp_dir: Path, sample_image: Path):
    """Test setting a photo as favorite."""
    import shutil

    library_dir = temp_dir / "library"
    library_dir.mkdir()
    runner.invoke(app, ["init", str(library_dir)])

    photos_dir = temp_dir / "photos"
    photos_dir.mkdir()
    shutil.copy(sample_image, photos_dir / "photo1.jpg")

    import os
    original_cwd = os.getcwd()
    os.chdir(library_dir)

    try:
        runner.invoke(app, ["import", str(photos_dir)])

        # Get photo ID
        query_result = runner.invoke(app, ["q", "--format", "ids"])
        photo_id = query_result.output.strip().split("\n")[0].strip()

        # Set as favorite
        result = runner.invoke(app, ["set", photo_id, "--favorite"])
        assert result.exit_code == 0

        # Query favorites
        fav_result = runner.invoke(app, ["q", "--favorite", "--format", "count"])
        assert "1" in fav_result.output
    finally:
        os.chdir(original_cwd)


def test_set_tag(temp_dir: Path, sample_image: Path):
    """Test adding a tag to a photo."""
    import shutil

    library_dir = temp_dir / "library"
    library_dir.mkdir()
    runner.invoke(app, ["init", str(library_dir)])

    photos_dir = temp_dir / "photos"
    photos_dir.mkdir()
    shutil.copy(sample_image, photos_dir / "photo1.jpg")

    import os
    original_cwd = os.getcwd()
    os.chdir(library_dir)

    try:
        runner.invoke(app, ["import", str(photos_dir)])

        # Get photo ID
        query_result = runner.invoke(app, ["q", "--format", "ids"])
        photo_id = query_result.output.strip().split("\n")[0].strip()

        # Add tag
        result = runner.invoke(app, ["set", photo_id, "--tag", "beach"])
        assert result.exit_code == 0

        # Query by tag
        tag_result = runner.invoke(app, ["q", "--tag", "beach", "--format", "count"])
        assert "1" in tag_result.output
    finally:
        os.chdir(original_cwd)
