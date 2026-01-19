"""Apple Photos importer for exported libraries."""

import plistlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional, Any

from ptk.core.constants import SUPPORTED_FORMATS
from ptk.importers.base import BaseImporter, ImportItem


class ApplePhotosImporter(BaseImporter):
    """Import photos from Apple Photos exports.

    Supports:
    - Exported photo directories (via File > Export)
    - Photos Library packages (partial - reads metadata from SQLite)
    - Individual HEIC/HEIF files with Apple metadata

    Note: Full Photos Library support requires reading the Photos.sqlite
    database which may have privacy/encryption limitations.
    """

    # Apple Photos Library markers
    LIBRARY_MARKERS = [
        "Photos Library.photoslibrary",
        "photoslibrary",
    ]

    # Database paths within Photos Library
    DATABASE_PATHS = [
        "database/Photos.sqlite",
        "database/photos.db",
    ]

    # Originals folder in Photos Library
    ORIGINALS_PATHS = [
        "originals",
        "Masters",
    ]

    def __init__(self, skip_hidden: bool = True, include_edited: bool = True):
        """Initialize the Apple Photos importer.

        Args:
            skip_hidden: Whether to skip hidden files
            include_edited: Whether to include edited versions alongside originals
        """
        self.skip_hidden = skip_hidden
        self.include_edited = include_edited

    @property
    def name(self) -> str:
        return "apple_photos"

    def can_handle(self, path: Path) -> bool:
        """Check if path is an Apple Photos export or library."""
        if path.is_dir():
            # Check for Photos Library bundle
            if path.suffix.lower() == ".photoslibrary":
                return True

            # Check for exported photos directory
            if self._is_apple_export_dir(path):
                return True

            # Check for directory name markers
            for marker in self.LIBRARY_MARKERS:
                if marker.lower() in path.name.lower():
                    return True

        return False

    def _is_apple_export_dir(self, dir_path: Path) -> bool:
        """Check if directory contains Apple Photos exports."""
        # Look for HEIC files (common in Apple exports)
        heic_files = list(dir_path.glob("*.HEIC")) + list(dir_path.glob("*.heic"))
        if heic_files:
            return True

        # Look for Apple-specific sidecar files
        aae_files = list(dir_path.glob("*.AAE"))
        if aae_files:
            return True

        return False

    def scan(self, path: Path) -> Iterator[ImportItem]:
        """Scan Apple Photos export for photos.

        Args:
            path: Path to Photos Library or export directory

        Yields:
            ImportItem for each photo with Apple metadata
        """
        if path.suffix.lower() == ".photoslibrary":
            yield from self._scan_library(path)
        else:
            yield from self._scan_directory(path)

    def _scan_directory(self, dir_path: Path) -> Iterator[ImportItem]:
        """Scan an export directory."""
        for file_path in dir_path.rglob("*"):
            if not self._is_valid_media_file(file_path):
                continue

            # Load AAE sidecar if present
            metadata = self._load_aae_metadata(file_path)

            yield ImportItem(path=file_path, source_metadata=metadata)

    def _scan_library(self, library_path: Path) -> Iterator[ImportItem]:
        """Scan a Photos Library bundle.

        Photos Library structure:
        - originals/ or Masters/ - original photos
        - resources/renders/ - edited versions
        - database/Photos.sqlite - metadata database
        """
        # Find originals folder
        originals_path = None
        for orig_name in self.ORIGINALS_PATHS:
            candidate = library_path / orig_name
            if candidate.exists():
                originals_path = candidate
                break

        if not originals_path:
            # Fall back to scanning the whole library
            yield from self._scan_directory(library_path)
            return

        # Try to load database metadata
        db_metadata = self._load_library_database(library_path)

        # Scan originals
        for file_path in originals_path.rglob("*"):
            if not self._is_valid_media_file(file_path):
                continue

            # Look up metadata from database
            metadata = self._get_photo_metadata(file_path, db_metadata)

            yield ImportItem(path=file_path, source_metadata=metadata)

    def _is_valid_media_file(self, path: Path) -> bool:
        """Check if a file should be imported."""
        if not path.is_file():
            return False

        # Skip hidden files
        if self.skip_hidden and path.name.startswith("."):
            return False

        # Skip Apple adjustment files
        if path.suffix.lower() == ".aae":
            return False

        # Skip database files
        if path.suffix.lower() in (".sqlite", ".sqlite-wal", ".sqlite-shm", ".db"):
            return False

        # Check extension
        return path.suffix.lower() in SUPPORTED_FORMATS

    def _load_aae_metadata(self, media_path: Path) -> Optional[dict[str, Any]]:
        """Load metadata from Apple's AAE sidecar file.

        AAE files are XML plists containing adjustment data.
        """
        aae_path = media_path.with_suffix(".AAE")
        if not aae_path.exists():
            aae_path = media_path.with_suffix(".aae")
            if not aae_path.exists():
                return None

        try:
            with open(aae_path, "rb") as f:
                plist_data = plistlib.load(f)

            metadata: dict[str, Any] = {
                "source": "apple_photos",
                "has_adjustments": True,
            }

            # Extract adjustment info
            if "adjustmentFormatIdentifier" in plist_data:
                metadata["adjustment_format"] = plist_data["adjustmentFormatIdentifier"]

            if "adjustmentTimestamp" in plist_data:
                ts = plist_data["adjustmentTimestamp"]
                if isinstance(ts, datetime):
                    metadata["adjustment_date"] = ts
                elif isinstance(ts, (int, float)):
                    # Apple timestamps are seconds since 2001-01-01
                    apple_epoch = datetime(2001, 1, 1, tzinfo=timezone.utc)
                    metadata["adjustment_date"] = datetime.fromtimestamp(
                        apple_epoch.timestamp() + ts, tz=timezone.utc
                    )

            return metadata

        except (plistlib.InvalidFileException, OSError):
            return None

    def _load_library_database(self, library_path: Path) -> Optional[dict[str, Any]]:
        """Load metadata from Photos.sqlite database.

        Returns a dictionary mapping file paths to metadata.
        """
        db_path = None
        for db_rel_path in self.DATABASE_PATHS:
            candidate = library_path / db_rel_path
            if candidate.exists():
                db_path = candidate
                break

        if not db_path:
            return None

        try:
            # Connect read-only to avoid locks
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row

            metadata_map: dict[str, Any] = {}

            # Query for basic photo info
            # Note: Schema varies by Photos version, this handles common cases
            try:
                cursor = conn.execute("""
                    SELECT
                        ZORIGINALFILENAME as filename,
                        ZDATECREATED as date_created,
                        ZLATITUDE as latitude,
                        ZLONGITUDE as longitude,
                        ZHEIGHT as height,
                        ZWIDTH as width
                    FROM ZASSET
                    WHERE ZORIGINALFILENAME IS NOT NULL
                """)

                for row in cursor:
                    filename = row["filename"]
                    if filename:
                        metadata_map[filename] = {
                            "source": "apple_photos",
                            "from_database": True,
                            "date_created": self._apple_timestamp_to_datetime(
                                row["date_created"]
                            ),
                            "latitude": row["latitude"],
                            "longitude": row["longitude"],
                            "width": row["width"],
                            "height": row["height"],
                        }
            except sqlite3.OperationalError:
                # Schema doesn't match, continue without DB metadata
                pass

            conn.close()
            return metadata_map

        except (sqlite3.Error, OSError):
            return None

    def _apple_timestamp_to_datetime(
        self, timestamp: Optional[float]
    ) -> Optional[datetime]:
        """Convert Apple Core Data timestamp to datetime.

        Apple stores timestamps as seconds since 2001-01-01 00:00:00 UTC.
        """
        if timestamp is None:
            return None

        try:
            # Apple epoch: January 1, 2001
            apple_epoch = datetime(2001, 1, 1, tzinfo=timezone.utc)
            return datetime.fromtimestamp(
                apple_epoch.timestamp() + timestamp, tz=timezone.utc
            )
        except (ValueError, OSError):
            return None

    def _get_photo_metadata(
        self, file_path: Path, db_metadata: Optional[dict[str, Any]]
    ) -> Optional[dict[str, Any]]:
        """Get metadata for a photo, combining database and sidecar data."""
        metadata: dict[str, Any] = {"source": "apple_photos"}

        # Try database lookup
        if db_metadata:
            filename = file_path.name
            if filename in db_metadata:
                metadata.update(db_metadata[filename])

        # Add AAE metadata if present
        aae_metadata = self._load_aae_metadata(file_path)
        if aae_metadata:
            metadata.update(aae_metadata)

        return metadata if len(metadata) > 1 else None

    def extract_metadata(self, item: ImportItem) -> Optional[dict[str, Any]]:
        """Extract metadata for import item."""
        return item.source_metadata
