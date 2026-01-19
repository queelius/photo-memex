"""Tests for ptk.core.config."""

import pytest
from pathlib import Path

from ptk.core.config import PtkConfig, find_library
from ptk.core.constants import DEFAULT_DATABASE_NAME


def test_default_config():
    """Test default configuration values."""
    config = PtkConfig()

    assert config.library_path is None
    assert config.database_name == DEFAULT_DATABASE_NAME
    assert config.thumbnail_size == 256
    assert config.skip_hidden is True
    assert config.recursive is True


def test_config_with_library_path(temp_dir: Path):
    """Test config with library path set."""
    config = PtkConfig(library_path=temp_dir)

    assert config.database_path == temp_dir / DEFAULT_DATABASE_NAME
    assert config.thumbnails_path == temp_dir / "thumbnails"


def test_config_database_path_raises_without_library():
    """Test that database_path raises without library_path."""
    config = PtkConfig()

    with pytest.raises(ValueError, match="library_path not set"):
        _ = config.database_path


def test_find_library_in_current_dir(temp_dir: Path):
    """Test finding library in current directory."""
    db_path = temp_dir / DEFAULT_DATABASE_NAME
    db_path.touch()

    result = find_library(temp_dir)
    assert result == temp_dir


def test_find_library_in_parent_dir(temp_dir: Path):
    """Test finding library in parent directory."""
    db_path = temp_dir / DEFAULT_DATABASE_NAME
    db_path.touch()

    subdir = temp_dir / "subdir"
    subdir.mkdir()

    result = find_library(subdir)
    assert result == temp_dir


def test_find_library_not_found(temp_dir: Path):
    """Test that find_library returns None when not found."""
    result = find_library(temp_dir)
    assert result is None


def test_xdg_paths():
    """Test XDG path methods exist and return paths."""
    config_dir = PtkConfig.config_dir()
    assert isinstance(config_dir, Path)
    assert "ptk" in str(config_dir)

    default_lib = PtkConfig.default_library_path()
    assert isinstance(default_lib, Path)

    cache_dir = PtkConfig.cache_dir()
    assert isinstance(cache_dir, Path)
