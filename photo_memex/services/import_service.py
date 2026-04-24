"""Import service for orchestrating photo imports."""

import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable

from sqlalchemy.orm import Session

from photo_memex.core.config import PtkConfig
from photo_memex.core.constants import SUPPORTED_VIDEO_FORMATS
from photo_memex.core.exif import extract_exif, ExifExtractionError
from photo_memex.core.hasher import hash_file
from photo_memex.core.thumbnails import generate_thumbnail, get_image_dimensions, ThumbnailError
from photo_memex.db.models import Photo
from photo_memex.importers.base import BaseImporter, ImportItem, ImportResult


# Progress callback type: (current, total, path)
ProgressCallback = Callable[[int, int, str], None]


class ImportService:
    """Service for importing photos into the library."""

    def __init__(self, session: Session, config: PtkConfig):
        """Initialize the import service.

        Args:
            session: Database session
            config: Application configuration
        """
        self.session = session
        self.config = config

    def import_from(
        self,
        importer: BaseImporter,
        path: Path,
        progress_callback: Optional[ProgressCallback] = None,
        dry_run: bool = False,
    ) -> ImportResult:
        """Import photos using the specified importer.

        Args:
            importer: The importer to use
            path: Path to import from
            progress_callback: Optional callback for progress updates
            dry_run: If True, don't actually import

        Returns:
            ImportResult with statistics
        """
        result = ImportResult()

        # Collect items first to get total count
        items = list(importer.scan(path))
        result.total_files = len(items)

        for i, item in enumerate(items):
            if progress_callback:
                progress_callback(i + 1, result.total_files, str(item.path))

            try:
                photo_id = self._import_item(item, importer.name, dry_run)
                if photo_id:
                    result.imported += 1
                    result.imported_ids.append(photo_id)
                else:
                    result.duplicates += 1
            except DuplicateError as e:
                result.duplicates += 1
                result.duplicate_ids.append(e.hash_id)
            except ImportError as e:
                result.errors += 1
                result.error_paths.append((str(item.path), str(e)))

        if not dry_run:
            self.session.commit()

        return result

    def import_file(
        self,
        path: Path,
        source: str = "filesystem",
        source_metadata: Optional[dict] = None,
    ) -> Optional[str]:
        """Import a single file.

        Args:
            path: Path to the file
            source: Import source identifier
            source_metadata: Optional source-specific metadata

        Returns:
            Photo ID if imported, None if duplicate
        """
        item = ImportItem(path=path, source_metadata=source_metadata)
        photo_id = self._import_item(item, source, dry_run=False)
        self.session.commit()
        return photo_id

    def _import_item(
        self,
        item: ImportItem,
        source: str,
        dry_run: bool,
    ) -> Optional[str]:
        """Import a single item.

        Args:
            item: The item to import
            source: Import source identifier
            dry_run: If True, don't actually import

        Returns:
            Photo ID if imported, None if duplicate
        """
        path = item.path

        # Hash the file
        file_hash = hash_file(path)

        # Check for duplicate
        existing = self.session.query(Photo).filter_by(id=file_hash).first()
        if existing:
            raise DuplicateError(file_hash, existing.original_path)

        if dry_run:
            return file_hash

        # Get file info
        file_size = path.stat().st_size
        mime_type = self._get_mime_type(path)
        is_video = path.suffix.lower() in SUPPORTED_VIDEO_FORMATS

        # Extract metadata
        width, height = None, None
        exif_data = None

        if not is_video:
            # Get dimensions
            dims = get_image_dimensions(path)
            if dims:
                width, height = dims

            # Extract EXIF
            try:
                exif_data = extract_exif(path)
                # EXIF might have better dimensions
                if exif_data.width and exif_data.height:
                    width, height = exif_data.width, exif_data.height
            except ExifExtractionError:
                pass  # EXIF extraction failed, continue without

        # Generate thumbnail
        thumbnail_data = None
        thumbnail_mime = None
        if not is_video:
            try:
                thumbnail_data, thumbnail_mime = generate_thumbnail(
                    path,
                    size=self.config.thumbnail_size,
                    format=self.config.thumbnail_format,
                    quality=self.config.thumbnail_quality,
                )
            except ThumbnailError:
                pass  # Thumbnail generation failed, continue without

        # Create photo record
        now = datetime.now(timezone.utc)
        photo = Photo(
            id=file_hash,
            original_path=str(path.resolve()),
            filename=path.name,
            file_size=file_size,
            mime_type=mime_type,
            width=width,
            height=height,
            date_imported=now,
            is_video=is_video,
            thumbnail_data=thumbnail_data,
            thumbnail_mime=thumbnail_mime,
            import_source=source,
            source_metadata=item.source_metadata,
        )

        # Add EXIF data if available
        if exif_data:
            photo.date_taken = exif_data.date_taken
            photo.camera_make = exif_data.camera_make
            photo.camera_model = exif_data.camera_model
            photo.lens = exif_data.lens
            photo.focal_length = exif_data.focal_length
            photo.aperture = exif_data.aperture
            photo.shutter_speed = exif_data.shutter_speed
            photo.iso = exif_data.iso

            if exif_data.gps:
                photo.latitude = exif_data.gps.latitude
                photo.longitude = exif_data.gps.longitude
                photo.altitude = exif_data.gps.altitude

        # Use source metadata as fallback (e.g., Google Takeout JSON, Apple Photos DB)
        if item.source_metadata:
            # Fallback for date_taken
            if not photo.date_taken and "date_taken" in item.source_metadata:
                date_value = item.source_metadata["date_taken"]
                # Handle both datetime objects and ISO strings
                if isinstance(date_value, str):
                    photo.date_taken = datetime.fromisoformat(date_value)
                elif isinstance(date_value, datetime):
                    photo.date_taken = date_value

            # Fallback for GPS coordinates
            if photo.latitude is None and "latitude" in item.source_metadata:
                photo.latitude = item.source_metadata["latitude"]
            if photo.longitude is None and "longitude" in item.source_metadata:
                photo.longitude = item.source_metadata["longitude"]
            if photo.altitude is None and "altitude" in item.source_metadata:
                photo.altitude = item.source_metadata["altitude"]

        self.session.add(photo)
        return file_hash

    def _get_mime_type(self, path: Path) -> str:
        """Get MIME type for a file."""
        mime_type, _ = mimetypes.guess_type(str(path))
        return mime_type or "application/octet-stream"


class DuplicateError(Exception):
    """Raised when a duplicate is detected."""

    def __init__(self, hash_id: str, existing_path: str):
        self.hash_id = hash_id
        self.existing_path = existing_path
        super().__init__(f"Duplicate: {hash_id}")


class ImportError(Exception):
    """Raised when import fails."""

    pass
