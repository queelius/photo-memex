"""Custom exceptions for ptk."""


class PtkError(Exception):
    """Base exception for ptk."""
    pass


class LibraryNotFoundError(PtkError):
    """Raised when no ptk library is found in the expected location."""
    pass


class LibraryExistsError(PtkError):
    """Raised when trying to initialize a library that already exists."""
    pass


class DuplicatePhotoError(PtkError):
    """Raised when a duplicate photo is detected during import."""

    def __init__(self, hash_id: str, existing_path: str, new_path: str):
        self.hash_id = hash_id
        self.existing_path = existing_path
        self.new_path = new_path
        super().__init__(
            f"Duplicate photo detected: {new_path} matches existing {existing_path}"
        )


class UnsupportedFormatError(PtkError):
    """Raised when an unsupported file format is encountered."""

    def __init__(self, path: str, extension: str):
        self.path = path
        self.extension = extension
        super().__init__(f"Unsupported format '{extension}': {path}")


class ExifExtractionError(PtkError):
    """Raised when EXIF extraction fails."""
    pass


class ThumbnailError(PtkError):
    """Raised when thumbnail generation fails."""
    pass


class AIFeatureNotAvailable(PtkError):
    """Raised when an AI feature is requested but dependencies are not installed."""

    def __init__(self, feature: str, install_hint: str):
        self.feature = feature
        self.install_hint = install_hint
        super().__init__(
            f"{feature} requires additional dependencies. Install with: {install_hint}"
        )
