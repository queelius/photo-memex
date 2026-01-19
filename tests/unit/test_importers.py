"""Tests for ptk.importers."""

import pytest
from pathlib import Path

from ptk.importers.filesystem import FilesystemImporter
from ptk.importers.base import ImportItem


def test_filesystem_importer_name():
    """Test importer name."""
    importer = FilesystemImporter()
    assert importer.name == "filesystem"


def test_filesystem_importer_can_handle_dir(temp_dir: Path):
    """Test that importer can handle directories."""
    importer = FilesystemImporter()
    assert importer.can_handle(temp_dir) is True


def test_filesystem_importer_can_handle_image(sample_image: Path):
    """Test that importer can handle image files."""
    importer = FilesystemImporter()
    assert importer.can_handle(sample_image) is True


def test_filesystem_importer_cannot_handle_text(temp_dir: Path):
    """Test that importer rejects unsupported files."""
    text_file = temp_dir / "test.txt"
    text_file.write_text("hello")

    importer = FilesystemImporter()
    assert importer.can_handle(text_file) is False


def test_filesystem_importer_scan_single_file(sample_image: Path):
    """Test scanning a single file."""
    importer = FilesystemImporter()
    items = list(importer.scan(sample_image))

    assert len(items) == 1
    assert items[0].path == sample_image


def test_filesystem_importer_scan_directory(temp_dir: Path):
    """Test scanning a directory."""
    from PIL import Image

    # Create a subdirectory with one image
    subdir = temp_dir / "photos"
    subdir.mkdir()

    img = Image.new("RGB", (10, 10), color="red")
    dest = subdir / "photo.jpg"
    img.save(dest)

    importer = FilesystemImporter()
    items = list(importer.scan(subdir))

    assert len(items) == 1
    assert items[0].path == dest


def test_filesystem_importer_skip_hidden(temp_dir: Path):
    """Test that hidden files are skipped by default."""
    from PIL import Image

    # Create hidden file
    hidden = temp_dir / ".hidden.jpg"
    img = Image.new("RGB", (10, 10), color="red")
    img.save(hidden)

    # Create visible file
    visible = temp_dir / "visible.jpg"
    img.save(visible)

    importer = FilesystemImporter(skip_hidden=True)
    items = list(importer.scan(temp_dir))

    assert len(items) == 1
    assert items[0].path == visible


def test_filesystem_importer_include_hidden(temp_dir: Path):
    """Test that hidden files can be included."""
    from PIL import Image

    hidden = temp_dir / ".hidden.jpg"
    img = Image.new("RGB", (10, 10), color="red")
    img.save(hidden)

    importer = FilesystemImporter(skip_hidden=False)
    items = list(importer.scan(temp_dir))

    assert len(items) == 1
    assert items[0].path == hidden


def test_filesystem_importer_recursive(temp_dir: Path):
    """Test recursive scanning."""
    from PIL import Image

    # Create nested structure
    subdir = temp_dir / "subdir"
    subdir.mkdir()

    img = Image.new("RGB", (10, 10), color="red")
    (temp_dir / "top.jpg").write_bytes(b"")
    img.save(temp_dir / "top.jpg")
    img.save(subdir / "nested.jpg")

    importer = FilesystemImporter(recursive=True)
    items = list(importer.scan(temp_dir))

    assert len(items) == 2
    paths = {item.path.name for item in items}
    assert paths == {"top.jpg", "nested.jpg"}


def test_filesystem_importer_non_recursive(temp_dir: Path):
    """Test non-recursive scanning."""
    from PIL import Image

    subdir = temp_dir / "subdir"
    subdir.mkdir()

    img = Image.new("RGB", (10, 10), color="red")
    img.save(temp_dir / "top.jpg")
    img.save(subdir / "nested.jpg")

    importer = FilesystemImporter(recursive=False)
    items = list(importer.scan(temp_dir))

    assert len(items) == 1
    assert items[0].path.name == "top.jpg"
