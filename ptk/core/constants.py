"""Constants and defaults for ptk."""

from typing import Final

# Supported image formats (lowercase extensions)
SUPPORTED_IMAGE_FORMATS: Final[frozenset[str]] = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".tiff", ".tif", ".bmp",
    ".heic", ".heif",  # Apple formats
    ".raw", ".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2",  # RAW formats
})

# Supported video formats (lowercase extensions)
SUPPORTED_VIDEO_FORMATS: Final[frozenset[str]] = frozenset({
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".3gp",
})

# All supported media formats
SUPPORTED_FORMATS: Final[frozenset[str]] = SUPPORTED_IMAGE_FORMATS | SUPPORTED_VIDEO_FORMATS

# Default thumbnail settings
DEFAULT_THUMBNAIL_SIZE: Final[int] = 256
DEFAULT_THUMBNAIL_FORMAT: Final[str] = "webp"
DEFAULT_THUMBNAIL_QUALITY: Final[int] = 85

# Database
DEFAULT_DATABASE_NAME: Final[str] = "ptk.db"

# XDG paths
APP_NAME: Final[str] = "ptk"
CONFIG_FILENAME: Final[str] = "config.toml"

# Hashing
HASH_CHUNK_SIZE: Final[int] = 65536  # 64KB chunks for file hashing
