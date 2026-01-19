"""Tests for ptk.importers.apple_photos."""

import plistlib
import pytest
from pathlib import Path

from ptk.importers.apple_photos import ApplePhotosImporter


@pytest.fixture
def apple_export_dir(temp_dir: Path) -> Path:
    """Create a mock Apple Photos export directory."""
    from PIL import Image

    export_dir = temp_dir / "Photos Export"
    export_dir.mkdir()

    # Create HEIC-style photo (just a JPEG for testing)
    img = Image.new("RGB", (100, 100), color="purple")
    photo_path = export_dir / "IMG_0001.HEIC"
    # Save as JPEG but with HEIC extension (for testing purposes)
    img.save(photo_path, format="JPEG")

    # Create another photo
    img2 = Image.new("RGB", (100, 100), color="orange")
    img2.save(export_dir / "IMG_0002.jpg")

    return export_dir


@pytest.fixture
def apple_export_with_aae(temp_dir: Path) -> Path:
    """Create Apple Photos export with AAE sidecar."""
    from PIL import Image

    export_dir = temp_dir / "Photos Export"
    export_dir.mkdir()

    # Create photo
    img = Image.new("RGB", (100, 100), color="cyan")
    photo_path = export_dir / "IMG_0001.jpg"
    img.save(photo_path)

    # Create AAE sidecar (plist format)
    aae_data = {
        "adjustmentFormatIdentifier": "com.apple.photo",
        "adjustmentFormatVersion": "1.0",
        "adjustmentRenderTypes": 0,
    }
    aae_path = export_dir / "IMG_0001.AAE"
    with open(aae_path, "wb") as f:
        plistlib.dump(aae_data, f)

    return export_dir


@pytest.fixture
def photos_library(temp_dir: Path) -> Path:
    """Create a mock Photos Library bundle."""
    from PIL import Image

    library_path = temp_dir / "Photos Library.photoslibrary"
    library_path.mkdir()

    # Create originals folder
    originals_dir = library_path / "originals" / "A"
    originals_dir.mkdir(parents=True)

    # Create photos
    img = Image.new("RGB", (100, 100), color="magenta")
    img.save(originals_dir / "photo1.jpg")

    img2 = Image.new("RGB", (100, 100), color="yellow")
    img2.save(originals_dir / "photo2.jpg")

    return library_path


def test_importer_name():
    """Test importer name."""
    importer = ApplePhotosImporter()
    assert importer.name == "apple_photos"


def test_can_handle_export_dir(apple_export_dir: Path):
    """Test recognizing Apple Photos export directory."""
    importer = ApplePhotosImporter()
    assert importer.can_handle(apple_export_dir) is True


def test_can_handle_library(photos_library: Path):
    """Test recognizing Photos Library bundle."""
    importer = ApplePhotosImporter()
    assert importer.can_handle(photos_library) is True


def test_cannot_handle_regular_dir(temp_dir: Path):
    """Test that regular directories are rejected."""
    importer = ApplePhotosImporter()
    assert importer.can_handle(temp_dir) is False


def test_scan_export_dir(apple_export_dir: Path):
    """Test scanning an export directory."""
    importer = ApplePhotosImporter()
    items = list(importer.scan(apple_export_dir))

    # Should find both photos
    assert len(items) == 2

    filenames = {item.path.name for item in items}
    assert filenames == {"IMG_0001.HEIC", "IMG_0002.jpg"}


def test_scan_with_aae_metadata(apple_export_with_aae: Path):
    """Test that AAE metadata is extracted."""
    importer = ApplePhotosImporter()
    items = list(importer.scan(apple_export_with_aae))

    assert len(items) == 1
    item = items[0]

    assert item.source_metadata is not None
    assert item.source_metadata["source"] == "apple_photos"
    assert item.source_metadata["has_adjustments"] is True


def test_scan_library(photos_library: Path):
    """Test scanning a Photos Library bundle."""
    importer = ApplePhotosImporter()
    items = list(importer.scan(photos_library))

    # Should find both photos in originals
    assert len(items) == 2

    filenames = {item.path.name for item in items}
    assert filenames == {"photo1.jpg", "photo2.jpg"}


def test_skip_aae_files(apple_export_with_aae: Path):
    """Test that AAE files are not imported as photos."""
    importer = ApplePhotosImporter()
    items = list(importer.scan(apple_export_with_aae))

    for item in items:
        assert not item.path.suffix.upper() == ".AAE"


def test_skip_hidden_files(temp_dir: Path):
    """Test that hidden files are skipped by default."""
    from PIL import Image

    export_dir = temp_dir / "Photos Export"
    export_dir.mkdir()

    # Create visible file
    img = Image.new("RGB", (50, 50), color="red")
    img.save(export_dir / "visible.jpg")

    # Create hidden file
    img.save(export_dir / ".hidden.jpg")

    # Create HEIC to make it recognized as Apple export
    img.save(export_dir / "test.HEIC", format="JPEG")

    importer = ApplePhotosImporter(skip_hidden=True)
    items = list(importer.scan(export_dir))

    filenames = {item.path.name for item in items}
    assert ".hidden.jpg" not in filenames
    assert "visible.jpg" in filenames


def test_include_hidden_files(temp_dir: Path):
    """Test that hidden files can be included."""
    from PIL import Image

    export_dir = temp_dir / "Photos Export"
    export_dir.mkdir()

    # Create hidden HEIC file
    img = Image.new("RGB", (50, 50), color="red")
    hidden_path = export_dir / ".hidden.HEIC"
    img.save(hidden_path, format="JPEG")

    importer = ApplePhotosImporter(skip_hidden=False)
    items = list(importer.scan(export_dir))

    assert len(items) == 1
    assert items[0].path.name == ".hidden.HEIC"


def test_skip_database_files(photos_library: Path):
    """Test that SQLite database files are skipped."""
    # Create a mock database directory
    db_dir = photos_library / "database"
    db_dir.mkdir()
    (db_dir / "Photos.sqlite").write_text("mock database")
    (db_dir / "Photos.sqlite-wal").write_text("mock wal")

    importer = ApplePhotosImporter()
    items = list(importer.scan(photos_library))

    for item in items:
        assert not item.path.suffix.lower() in (".sqlite", ".sqlite-wal", ".db")
