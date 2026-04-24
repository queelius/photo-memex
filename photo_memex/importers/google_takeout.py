"""Google Takeout importer for Google Photos exports."""

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional, Any

from photo_memex.core.constants import SUPPORTED_FORMATS
from photo_memex.importers.base import BaseImporter, ImportItem


class GoogleTakeoutImporter(BaseImporter):
    """Import photos from Google Takeout exports.

    Google Takeout exports photos with JSON sidecar files containing metadata
    like creation time, geo data, descriptions, and original filenames.

    Supports both:
    - Extracted directories (Takeout/Google Photos/...)
    - ZIP archives directly
    """

    # Known Google Photos directory markers
    GOOGLE_PHOTOS_MARKERS = [
        "Google Photos",
        "Photos from",
        "Takeout",
    ]

    def __init__(self, skip_hidden: bool = True):
        """Initialize the Google Takeout importer.

        Args:
            skip_hidden: Whether to skip hidden files
        """
        self.skip_hidden = skip_hidden
        self._temp_extract_dir: Optional[Path] = None

    @property
    def name(self) -> str:
        return "google_takeout"

    def can_handle(self, path: Path) -> bool:
        """Check if path is a Google Takeout export.

        Recognizes:
        - ZIP files with Google Photos structure
        - Directories containing Google Photos folders
        """
        if path.is_file() and path.suffix.lower() == ".zip":
            return self._is_google_takeout_zip(path)

        if path.is_dir():
            return self._is_google_takeout_dir(path)

        return False

    def _is_google_takeout_zip(self, zip_path: Path) -> bool:
        """Check if a ZIP file contains Google Takeout structure."""
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                # Look for Google Photos markers in paths
                for name in names[:100]:  # Check first 100 entries
                    for marker in self.GOOGLE_PHOTOS_MARKERS:
                        if marker in name:
                            return True
        except (zipfile.BadZipFile, OSError):
            pass
        return False

    def _is_google_takeout_dir(self, dir_path: Path) -> bool:
        """Check if a directory contains Google Takeout structure."""
        # Look for Google Photos subdirectory or marker files
        for marker in self.GOOGLE_PHOTOS_MARKERS:
            if (dir_path / marker).exists():
                return True
            # Check if current directory name matches
            if marker.lower() in dir_path.name.lower():
                return True

        # Look for characteristic JSON sidecar files
        for json_file in dir_path.rglob("*.json"):
            if self._is_google_sidecar(json_file):
                return True
            # Only check a few files
            break

        return False

    def _is_google_sidecar(self, json_path: Path) -> bool:
        """Check if a JSON file is a Google Photos sidecar."""
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Google sidecar files have these characteristic keys
                return any(
                    key in data for key in ["photoTakenTime", "creationTime", "geoData", "title"]
                )
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return False

    def scan(self, path: Path) -> Iterator[ImportItem]:
        """Scan Google Takeout export for photos.

        Args:
            path: Path to Takeout directory or ZIP file

        Yields:
            ImportItem for each photo with Google metadata
        """
        if path.is_file() and path.suffix.lower() == ".zip":
            yield from self._scan_zip(path)
        elif path.is_dir():
            yield from self._scan_directory(path)

    def _scan_directory(self, dir_path: Path) -> Iterator[ImportItem]:
        """Scan an extracted Takeout directory."""
        for file_path in dir_path.rglob("*"):
            if not self._is_valid_media_file(file_path):
                continue

            # Look for JSON sidecar
            metadata = self._load_sidecar_metadata(file_path)

            yield ImportItem(path=file_path, source_metadata=metadata)

    def _scan_zip(self, zip_path: Path) -> Iterator[ImportItem]:
        """Scan a Takeout ZIP file.

        Extracts files to a temporary directory for processing.
        """
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ptk_takeout_") as temp_dir:
            temp_path = Path(temp_dir)

            # Extract ZIP
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(temp_path)

            # Scan extracted directory
            yield from self._scan_directory(temp_path)

    def _is_valid_media_file(self, path: Path) -> bool:
        """Check if a file should be imported."""
        if not path.is_file():
            return False

        # Skip hidden files
        if self.skip_hidden and path.name.startswith("."):
            return False

        # Skip JSON metadata files
        if path.suffix.lower() == ".json":
            return False

        # Check extension
        return path.suffix.lower() in SUPPORTED_FORMATS

    def _load_sidecar_metadata(self, media_path: Path) -> Optional[dict[str, Any]]:
        """Load metadata from Google's JSON sidecar file.

        Google creates sidecar files with various naming patterns:
        - photo.jpg.json (most common)
        - photo.json (sometimes)
        - photo(1).jpg.json (for duplicates)
        """
        # Try common sidecar naming patterns
        candidates = [
            media_path.with_suffix(media_path.suffix + ".json"),  # photo.jpg.json
            media_path.with_suffix(".json"),  # photo.json
        ]

        # Handle edited versions (photo-edited.jpg -> photo.jpg.json)
        if "-edited" in media_path.stem:
            base_name = media_path.stem.replace("-edited", "")
            candidates.append(media_path.parent / f"{base_name}{media_path.suffix}.json")

        for sidecar_path in candidates:
            if sidecar_path.exists():
                return self._parse_google_json(sidecar_path)

        return None

    def _parse_google_json(self, json_path: Path) -> Optional[dict[str, Any]]:
        """Parse Google's JSON sidecar format into our metadata format."""
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return None

        metadata: dict[str, Any] = {
            "source": "google_takeout",
            "raw": data,
        }

        # Extract title/description
        if "title" in data:
            metadata["title"] = data["title"]
        if "description" in data:
            metadata["description"] = data["description"]

        # Extract timestamp - prefer photoTakenTime, fallback to creationTime
        timestamp = data.get("photoTakenTime") or data.get("creationTime")
        if timestamp and "timestamp" in timestamp:
            try:
                ts = int(timestamp["timestamp"])
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                # Store as ISO string for JSON serialization
                metadata["date_taken"] = dt.isoformat()
            except (ValueError, OSError):
                pass

        # Extract geo data
        geo_data = data.get("geoData") or data.get("geoDataExif")
        if geo_data:
            lat = geo_data.get("latitude")
            lng = geo_data.get("longitude")
            alt = geo_data.get("altitude")

            if lat is not None and lng is not None:
                # Google sometimes stores 0.0 for missing coordinates
                if lat != 0.0 or lng != 0.0:
                    metadata["latitude"] = lat
                    metadata["longitude"] = lng
                    if alt is not None and alt != 0.0:
                        metadata["altitude"] = alt

        # Extract people tags
        if "people" in data:
            people = []
            for person in data["people"]:
                if "name" in person:
                    people.append(person["name"])
            if people:
                metadata["people"] = people

        # Extract URL if present (for archived photos)
        if "url" in data:
            metadata["original_url"] = data["url"]

        # Google Photos specific
        if "googlePhotosOrigin" in data:
            origin = data["googlePhotosOrigin"]
            if "mobileUpload" in origin:
                metadata["upload_source"] = "mobile"
            elif "fromPartnerSharing" in origin:
                metadata["upload_source"] = "partner_sharing"

        return metadata

    def extract_metadata(self, item: ImportItem) -> Optional[dict[str, Any]]:
        """Extract metadata for import item."""
        return item.source_metadata
