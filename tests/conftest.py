"""Shared test fixtures for ptk."""

import tempfile
from pathlib import Path
from typing import Generator

import pytest
from PIL import Image

from photo_memex.core.config import PtkConfig, set_config
from photo_memex.db.session import init_db, close_db, get_session


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_image(temp_dir: Path) -> Path:
    """Create a sample JPEG image for testing."""
    img = Image.new("RGB", (100, 100), color="red")
    path = temp_dir / "test_image.jpg"
    img.save(path, "JPEG")
    return path


@pytest.fixture
def sample_image_with_exif(temp_dir: Path) -> Path:
    """Create a sample JPEG with basic EXIF data."""
    from PIL.ExifTags import TAGS
    import piexif

    img = Image.new("RGB", (200, 150), color="blue")
    path = temp_dir / "test_exif.jpg"

    # Create basic EXIF data
    exif_dict = {
        "0th": {
            piexif.ImageIFD.Make: "TestCamera",
            piexif.ImageIFD.Model: "Model X",
        },
        "Exif": {
            piexif.ExifIFD.DateTimeOriginal: "2023:07:15 14:30:00",
        },
    }

    try:
        exif_bytes = piexif.dump(exif_dict)
        img.save(path, "JPEG", exif=exif_bytes)
    except Exception:
        # piexif might not be installed, just save without EXIF
        img.save(path, "JPEG")

    return path


@pytest.fixture
def sample_png(temp_dir: Path) -> Path:
    """Create a sample PNG image."""
    img = Image.new("RGBA", (50, 50), color=(0, 255, 0, 128))
    path = temp_dir / "test_image.png"
    img.save(path, "PNG")
    return path


@pytest.fixture
def test_library(temp_dir: Path) -> Generator[Path, None, None]:
    """Create a test library with initialized database."""
    library_path = temp_dir / "library"
    library_path.mkdir()

    config = PtkConfig(library_path=library_path)
    set_config(config)
    init_db(config.database_path, create_tables=True)

    yield library_path

    close_db()


@pytest.fixture
def db_session(test_library: Path):
    """Get a database session for the test library."""
    session = get_session()
    yield session
    session.close()


@pytest.fixture
def populated_library(test_library: Path, sample_image: Path):
    """Create a library with some sample photos."""
    from photo_memex.importers.filesystem import FilesystemImporter
    from photo_memex.services.import_service import ImportService
    from photo_memex.core.config import get_config

    session = get_session()
    config = get_config()

    importer = FilesystemImporter()
    service = ImportService(session, config)
    service.import_file(sample_image)

    yield test_library

    session.close()
