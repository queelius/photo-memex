"""Tests for photo_memex.core.thumbnails."""

import pytest
from pathlib import Path
from io import BytesIO

from PIL import Image

from photo_memex.core.thumbnails import (
    generate_thumbnail,
    get_image_dimensions,
    ThumbnailError,
)


def test_generate_thumbnail_jpeg(sample_image: Path):
    """Test generating a JPEG thumbnail."""
    data, mime = generate_thumbnail(sample_image, size=64, format="jpeg")

    assert isinstance(data, bytes)
    assert len(data) > 0
    assert mime == "image/jpeg"

    # Verify it's a valid image
    img = Image.open(BytesIO(data))
    assert max(img.size) <= 64


def test_generate_thumbnail_webp(sample_image: Path):
    """Test generating a WebP thumbnail."""
    data, mime = generate_thumbnail(sample_image, size=64, format="webp")

    assert isinstance(data, bytes)
    assert mime == "image/webp"


def test_generate_thumbnail_png(sample_png: Path):
    """Test generating a PNG thumbnail from RGBA image."""
    data, mime = generate_thumbnail(sample_png, size=32, format="png")

    assert isinstance(data, bytes)
    assert mime == "image/png"


def test_generate_thumbnail_maintains_aspect_ratio(temp_dir: Path):
    """Test that thumbnail maintains aspect ratio."""
    # Create a wide image
    img = Image.new("RGB", (200, 100), color="green")
    path = temp_dir / "wide.jpg"
    img.save(path)

    data, _ = generate_thumbnail(path, size=50)
    thumb = Image.open(BytesIO(data))

    # Should be 50x25 (maintaining 2:1 ratio)
    assert thumb.width <= 50
    assert thumb.height <= 50
    assert abs(thumb.width / thumb.height - 2.0) < 0.1


def test_get_image_dimensions(sample_image: Path):
    """Test getting image dimensions."""
    dims = get_image_dimensions(sample_image)

    assert dims is not None
    assert dims == (100, 100)


def test_get_image_dimensions_nonexistent():
    """Test getting dimensions of nonexistent file."""
    dims = get_image_dimensions(Path("/nonexistent/file.jpg"))
    assert dims is None


def test_generate_thumbnail_nonexistent_file():
    """Test thumbnail generation with nonexistent file."""
    from photo_memex.core.exceptions import ThumbnailError

    with pytest.raises(ThumbnailError):
        generate_thumbnail(Path("/nonexistent/file.jpg"))
