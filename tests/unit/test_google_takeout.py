"""Tests for ptk.importers.google_takeout."""

import json
import pytest
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from ptk.importers.google_takeout import GoogleTakeoutImporter


@pytest.fixture
def google_takeout_dir(temp_dir: Path) -> Path:
    """Create a mock Google Takeout directory structure."""
    from PIL import Image

    # Create Takeout/Google Photos structure
    takeout_dir = temp_dir / "Takeout"
    photos_dir = takeout_dir / "Google Photos" / "2023 Vacation"
    photos_dir.mkdir(parents=True)

    # Create a photo
    img = Image.new("RGB", (100, 100), color="blue")
    photo_path = photos_dir / "beach.jpg"
    img.save(photo_path)

    # Create JSON sidecar with metadata
    sidecar = {
        "title": "Beach photo",
        "description": "A beautiful beach sunset",
        "photoTakenTime": {"timestamp": "1609459200"},  # 2021-01-01 00:00:00 UTC
        "geoData": {
            "latitude": 34.0522,
            "longitude": -118.2437,
            "altitude": 100.0,
        },
        "people": [{"name": "John Doe"}],
    }
    sidecar_path = photos_dir / "beach.jpg.json"
    sidecar_path.write_text(json.dumps(sidecar))

    # Create another photo without sidecar
    img2 = Image.new("RGB", (100, 100), color="green")
    img2.save(photos_dir / "forest.jpg")

    return takeout_dir


@pytest.fixture
def google_takeout_zip(temp_dir: Path, google_takeout_dir: Path) -> Path:
    """Create a mock Google Takeout ZIP file."""
    zip_path = temp_dir / "takeout.zip"

    with zipfile.ZipFile(zip_path, "w") as zf:
        for file_path in google_takeout_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(temp_dir)
                zf.write(file_path, arcname)

    return zip_path


def test_importer_name():
    """Test importer name."""
    importer = GoogleTakeoutImporter()
    assert importer.name == "google_takeout"


def test_can_handle_takeout_dir(google_takeout_dir: Path):
    """Test recognizing Google Takeout directory."""
    importer = GoogleTakeoutImporter()
    assert importer.can_handle(google_takeout_dir) is True


def test_can_handle_takeout_zip(google_takeout_zip: Path):
    """Test recognizing Google Takeout ZIP."""
    importer = GoogleTakeoutImporter()
    assert importer.can_handle(google_takeout_zip) is True


def test_cannot_handle_regular_dir(temp_dir: Path):
    """Test that regular directories are rejected."""
    importer = GoogleTakeoutImporter()
    assert importer.can_handle(temp_dir) is False


def test_scan_directory(google_takeout_dir: Path):
    """Test scanning a Takeout directory."""
    importer = GoogleTakeoutImporter()
    items = list(importer.scan(google_takeout_dir))

    # Should find both photos
    assert len(items) == 2

    # Check filenames
    filenames = {item.path.name for item in items}
    assert filenames == {"beach.jpg", "forest.jpg"}


def test_scan_with_metadata(google_takeout_dir: Path):
    """Test that metadata is extracted from sidecars."""
    importer = GoogleTakeoutImporter()
    items = list(importer.scan(google_takeout_dir))

    # Find the beach photo (has sidecar)
    beach_item = next(item for item in items if item.path.name == "beach.jpg")

    assert beach_item.source_metadata is not None
    assert beach_item.source_metadata["source"] == "google_takeout"
    assert beach_item.source_metadata["title"] == "Beach photo"
    assert beach_item.source_metadata["description"] == "A beautiful beach sunset"
    assert beach_item.source_metadata["latitude"] == 34.0522
    assert beach_item.source_metadata["longitude"] == -118.2437
    assert "date_taken" in beach_item.source_metadata

    # Check date parsing (stored as ISO string for JSON serialization)
    date_taken = beach_item.source_metadata["date_taken"]
    assert isinstance(date_taken, str)
    assert "2021-01-01" in date_taken


def test_scan_without_sidecar(google_takeout_dir: Path):
    """Test photo without sidecar has no metadata."""
    importer = GoogleTakeoutImporter()
    items = list(importer.scan(google_takeout_dir))

    # Find the forest photo (no sidecar)
    forest_item = next(item for item in items if item.path.name == "forest.jpg")

    assert forest_item.source_metadata is None


def test_scan_zip(google_takeout_zip: Path):
    """Test scanning a Takeout ZIP file."""
    importer = GoogleTakeoutImporter()
    items = list(importer.scan(google_takeout_zip))

    # Should find both photos
    assert len(items) == 2


def test_skip_json_files(google_takeout_dir: Path):
    """Test that JSON sidecar files are not imported as photos."""
    importer = GoogleTakeoutImporter()
    items = list(importer.scan(google_takeout_dir))

    for item in items:
        assert not item.path.suffix.lower() == ".json"


def test_people_extraction(google_takeout_dir: Path):
    """Test that people tags are extracted."""
    importer = GoogleTakeoutImporter()
    items = list(importer.scan(google_takeout_dir))

    beach_item = next(item for item in items if item.path.name == "beach.jpg")

    assert "people" in beach_item.source_metadata
    assert beach_item.source_metadata["people"] == ["John Doe"]


def test_zero_coordinates_ignored(temp_dir: Path):
    """Test that 0.0 coordinates are ignored (Google's placeholder)."""
    from PIL import Image

    takeout_dir = temp_dir / "Takeout" / "Google Photos"
    takeout_dir.mkdir(parents=True)

    img = Image.new("RGB", (50, 50), color="red")
    photo_path = takeout_dir / "test.jpg"
    img.save(photo_path)

    sidecar = {
        "title": "Test",
        "geoData": {"latitude": 0.0, "longitude": 0.0, "altitude": 0.0},
    }
    (takeout_dir / "test.jpg.json").write_text(json.dumps(sidecar))

    importer = GoogleTakeoutImporter()
    items = list(importer.scan(takeout_dir))

    assert len(items) == 1
    # 0.0 coordinates should be ignored
    assert "latitude" not in items[0].source_metadata
    assert "longitude" not in items[0].source_metadata
