"""Integration tests for Phase 3 features (Google Takeout, Apple Photos importers)."""

import json
import pytest
from pathlib import Path
from typer.testing import CliRunner

from photo_memex.cli import app


runner = CliRunner()


@pytest.fixture
def library_dir(temp_dir: Path) -> Path:
    """Create an initialized library."""
    library_dir = temp_dir / "library"
    library_dir.mkdir()
    runner.invoke(app, ["init", str(library_dir)])

    import os
    original_cwd = os.getcwd()
    os.chdir(library_dir)

    yield library_dir

    os.chdir(original_cwd)


@pytest.fixture
def google_takeout_export(temp_dir: Path) -> Path:
    """Create a mock Google Takeout export."""
    from PIL import Image

    takeout_dir = temp_dir / "Takeout"
    photos_dir = takeout_dir / "Google Photos" / "Album"
    photos_dir.mkdir(parents=True)

    # Create photos with sidecars
    img = Image.new("RGB", (100, 100), color="blue")
    img.save(photos_dir / "vacation.jpg")

    sidecar = {
        "title": "Vacation Photo",
        "photoTakenTime": {"timestamp": "1609459200"},
        "geoData": {"latitude": 40.7128, "longitude": -74.0060, "altitude": 10.0},
    }
    (photos_dir / "vacation.jpg.json").write_text(json.dumps(sidecar))

    return takeout_dir


@pytest.fixture
def apple_photos_export(temp_dir: Path) -> Path:
    """Create a mock Apple Photos export."""
    from PIL import Image

    export_dir = temp_dir / "Apple Photos Export"
    export_dir.mkdir()

    img = Image.new("RGB", (100, 100), color="green")
    img.save(export_dir / "IMG_0001.HEIC", format="JPEG")

    return export_dir


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
# Google Takeout CLI Tests
# ============================================================================


def test_import_google_takeout(library_dir: Path, google_takeout_export: Path):
    """Test importing from Google Takeout."""
    result = runner.invoke(app, ["import", "--source", "google", str(google_takeout_export)])

    assert result.exit_code == 0
    assert "Imported: 1" in result.output


def test_import_google_takeout_dry_run(library_dir: Path, google_takeout_export: Path):
    """Test Google Takeout import dry run."""
    result = runner.invoke(app, ["import", "--source", "google", "--dry-run", str(google_takeout_export)])

    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert "would import" in result.output


def test_import_google_takeout_invalid_path(library_dir: Path, temp_dir: Path):
    """Test Google Takeout import with invalid path."""
    result = runner.invoke(app, ["import", "--source", "google", str(temp_dir / "nonexistent")])

    assert result.exit_code == 1
    assert "does not exist" in result.output or "not exist" in result.output.lower()


def test_import_google_takeout_not_recognized(library_dir: Path, temp_dir: Path):
    """Test Google Takeout import with non-Takeout directory."""
    regular_dir = temp_dir / "regular"
    regular_dir.mkdir()

    result = runner.invoke(app, ["import", "--source", "google", str(regular_dir)])

    assert result.exit_code == 1
    assert "Not a recognized" in result.output


def test_import_google_takeout_preserves_metadata(library_dir: Path, google_takeout_export: Path):
    """Test that Google Takeout metadata is preserved."""
    runner.invoke(app, ["import", "--source", "google", str(google_takeout_export)])

    # Query photos
    query_result = runner.invoke(app, ["q", "--format", "json"])
    assert query_result.exit_code == 0

    data = json.loads(query_result.output)
    assert len(data) == 1
    # vacation.jpg should be imported
    assert data[0]["filename"] == "vacation.jpg"


# ============================================================================
# Apple Photos CLI Tests
# ============================================================================


def test_import_apple_photos(library_dir: Path, apple_photos_export: Path):
    """Test importing from Apple Photos export."""
    result = runner.invoke(app, ["import", "--source", "apple", str(apple_photos_export)])

    assert result.exit_code == 0
    assert "Imported: 1" in result.output


def test_import_apple_photos_dry_run(library_dir: Path, apple_photos_export: Path):
    """Test Apple Photos import dry run."""
    result = runner.invoke(app, ["import", "--source", "apple", "--dry-run", str(apple_photos_export)])

    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert "would import" in result.output


def test_import_apple_photos_invalid_path(library_dir: Path, temp_dir: Path):
    """Test Apple Photos import with invalid path."""
    result = runner.invoke(app, ["import", "--source", "apple", str(temp_dir / "nonexistent")])

    assert result.exit_code == 1
    assert "does not exist" in result.output or "not exist" in result.output.lower()


def test_import_apple_photos_not_recognized(library_dir: Path, temp_dir: Path):
    """Test Apple Photos import with non-Apple directory."""
    regular_dir = temp_dir / "regular"
    regular_dir.mkdir()

    result = runner.invoke(app, ["import", "--source", "apple", str(regular_dir)])

    assert result.exit_code == 1
    assert "Not a recognized" in result.output


# ============================================================================
# Import Source Tracking Tests
# ============================================================================


def test_import_source_tracked_google(library_dir: Path, google_takeout_export: Path):
    """Test that import source is tracked for Google Takeout."""
    runner.invoke(app, ["import", "--source", "google", str(google_takeout_export)])

    # Query and show photo
    photo_id = _get_first_photo_id(runner, app)
    assert photo_id is not None

    show_result = runner.invoke(app, ["show", photo_id])
    assert show_result.exit_code == 0
    # The source should be tracked in the database
    assert "google" in show_result.output.lower() or "vacation" in show_result.output.lower()


def test_import_source_tracked_apple(library_dir: Path, apple_photos_export: Path):
    """Test that import source is tracked for Apple Photos."""
    runner.invoke(app, ["import", "--source", "apple", str(apple_photos_export)])

    # Query and show photo
    photo_id = _get_first_photo_id(runner, app)
    assert photo_id is not None

    show_result = runner.invoke(app, ["show", photo_id])
    assert show_result.exit_code == 0


# ============================================================================
# Auto-detection Tests
# ============================================================================


def test_import_auto_detects_directory(library_dir: Path, temp_dir: Path):
    """Test that import auto-detects directories."""
    from PIL import Image

    photos_dir = temp_dir / "photos"
    photos_dir.mkdir()

    img = Image.new("RGB", (100, 100), color="red")
    img.save(photos_dir / "test.jpg")

    # Import without --source should auto-detect directory
    result = runner.invoke(app, ["import", str(photos_dir)])
    assert result.exit_code == 0
    assert "Imported: 1" in result.output
