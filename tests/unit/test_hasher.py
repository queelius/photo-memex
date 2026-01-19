"""Tests for ptk.core.hasher."""

import pytest
from pathlib import Path

from ptk.core.hasher import hash_file, hash_bytes


def test_hash_bytes():
    """Test hashing bytes."""
    data = b"hello world"
    result = hash_bytes(data)

    assert isinstance(result, str)
    assert len(result) == 64  # SHA256 hex digest is 64 chars
    assert result == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"


def test_hash_bytes_empty():
    """Test hashing empty bytes."""
    result = hash_bytes(b"")
    assert len(result) == 64
    # SHA256 of empty string
    assert result == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_hash_file(sample_image: Path):
    """Test hashing a file."""
    result = hash_file(sample_image)

    assert isinstance(result, str)
    assert len(result) == 64


def test_hash_file_deterministic(sample_image: Path):
    """Test that hashing the same file gives the same result."""
    result1 = hash_file(sample_image)
    result2 = hash_file(sample_image)

    assert result1 == result2


def test_hash_file_different_content(temp_dir: Path):
    """Test that different content gives different hashes."""
    from PIL import Image

    img1 = Image.new("RGB", (10, 10), color="red")
    path1 = temp_dir / "img1.jpg"
    img1.save(path1)

    img2 = Image.new("RGB", (10, 10), color="blue")
    path2 = temp_dir / "img2.jpg"
    img2.save(path2)

    hash1 = hash_file(path1)
    hash2 = hash_file(path2)

    assert hash1 != hash2
