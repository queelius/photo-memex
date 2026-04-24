"""Configuration management for photo-memex.

PtkConfig holds library location and import/thumbnail settings.
find_library() locates photo-memex.db by walking up from cwd.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from photo_memex.core.constants import (
    APP_NAME,
    DEFAULT_DATABASE_NAME,
    DEFAULT_THUMBNAIL_FORMAT,
    DEFAULT_THUMBNAIL_QUALITY,
    DEFAULT_THUMBNAIL_SIZE,
)


def _get_xdg_data_home() -> Path:
    """Get XDG_DATA_HOME or default."""
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


@dataclass
class PtkConfig:
    """Main configuration for ptk."""

    # Library location (where database and thumbnails are stored)
    library_path: Path | None = None

    # Database settings
    database_name: str = DEFAULT_DATABASE_NAME

    # Thumbnail settings
    thumbnail_size: int = DEFAULT_THUMBNAIL_SIZE
    thumbnail_format: str = DEFAULT_THUMBNAIL_FORMAT
    thumbnail_quality: int = DEFAULT_THUMBNAIL_QUALITY

    # Import settings
    skip_hidden: bool = True
    recursive: bool = True

    @property
    def database_path(self) -> Path:
        """Get the full path to the database file."""
        if self.library_path is None:
            raise ValueError("library_path not set")
        return self.library_path / self.database_name

    @property
    def thumbnails_path(self) -> Path:
        """Get the path to thumbnails directory."""
        if self.library_path is None:
            raise ValueError("library_path not set")
        return self.library_path / "thumbnails"

    @classmethod
    def default_library_path(cls) -> Path:
        """Get the default library path."""
        return _get_xdg_data_home() / APP_NAME


# Global config instance
_config: PtkConfig | None = None


def get_config() -> PtkConfig:
    """Get the global config instance, creating if needed."""
    global _config
    if _config is None:
        _config = PtkConfig()
    return _config


def set_config(config: PtkConfig) -> None:
    """Set the global config instance."""
    global _config
    _config = config


def find_library(start_path: Path | None = None) -> Path | None:
    """Find a photo-memex library by looking for photo-memex.db in current or parent directories.

    Args:
        start_path: Starting directory (defaults to cwd)

    Returns:
        Path to library directory if found, None otherwise
    """
    start = start_path or Path.cwd()
    current = start.resolve()

    while current != current.parent:
        db_path = current / DEFAULT_DATABASE_NAME
        if db_path.exists():
            return current
        current = current.parent

    # Check root last
    db_path = current / DEFAULT_DATABASE_NAME
    if db_path.exists():
        return current

    return None
