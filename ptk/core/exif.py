"""EXIF metadata extraction using exifread."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
import re

import exifread
from dateutil import parser as date_parser

from ptk.core.exceptions import ExifExtractionError


@dataclass
class GpsCoordinates:
    """GPS coordinates extracted from EXIF."""

    latitude: float
    longitude: float
    altitude: Optional[float] = None


@dataclass
class ExifData:
    """Extracted EXIF metadata."""

    # Temporal
    date_taken: Optional[datetime] = None

    # Camera
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    lens: Optional[str] = None

    # Exposure
    focal_length: Optional[float] = None
    aperture: Optional[float] = None
    shutter_speed: Optional[str] = None
    iso: Optional[int] = None

    # Image
    width: Optional[int] = None
    height: Optional[int] = None
    orientation: Optional[int] = None

    # Location
    gps: Optional[GpsCoordinates] = None

    # Raw tags for debugging
    raw_tags: dict[str, Any] | None = None


def _convert_to_degrees(value: Any) -> float:
    """Convert GPS coordinates from exifread format to decimal degrees."""
    d = float(value.values[0].num) / float(value.values[0].den)
    m = float(value.values[1].num) / float(value.values[1].den)
    s = float(value.values[2].num) / float(value.values[2].den)
    return d + (m / 60.0) + (s / 3600.0)


def _parse_datetime(value: str) -> Optional[datetime]:
    """Parse EXIF datetime string."""
    # Common EXIF format: "2023:07:15 14:30:00"
    exif_pattern = r"(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})"
    match = re.match(exif_pattern, value)
    if match:
        try:
            return datetime(
                int(match.group(1)),  # year
                int(match.group(2)),  # month
                int(match.group(3)),  # day
                int(match.group(4)),  # hour
                int(match.group(5)),  # minute
                int(match.group(6)),  # second
            )
        except ValueError:
            pass

    # Fallback to dateutil parser
    try:
        return date_parser.parse(value)
    except (ValueError, TypeError):
        return None


def _get_tag_value(tags: dict, key: str) -> Optional[str]:
    """Safely get a tag value as string."""
    if key in tags:
        return str(tags[key])
    return None


def _get_tag_float(tags: dict, key: str) -> Optional[float]:
    """Safely get a tag value as float."""
    if key in tags:
        try:
            val = tags[key]
            if hasattr(val, "values") and len(val.values) > 0:
                v = val.values[0]
                if hasattr(v, "num") and hasattr(v, "den"):
                    return float(v.num) / float(v.den)
            return float(str(val))
        except (ValueError, TypeError, ZeroDivisionError):
            pass
    return None


def _get_tag_int(tags: dict, key: str) -> Optional[int]:
    """Safely get a tag value as int."""
    if key in tags:
        try:
            val = tags[key]
            if hasattr(val, "values") and len(val.values) > 0:
                return int(val.values[0])
            return int(str(val))
        except (ValueError, TypeError):
            pass
    return None


def _extract_gps(tags: dict) -> Optional[GpsCoordinates]:
    """Extract GPS coordinates from EXIF tags."""
    lat_key = "GPS GPSLatitude"
    lat_ref_key = "GPS GPSLatitudeRef"
    lon_key = "GPS GPSLongitude"
    lon_ref_key = "GPS GPSLongitudeRef"
    alt_key = "GPS GPSAltitude"

    if lat_key not in tags or lon_key not in tags:
        return None

    try:
        lat = _convert_to_degrees(tags[lat_key])
        lon = _convert_to_degrees(tags[lon_key])

        # Apply reference (N/S, E/W)
        if lat_ref_key in tags and str(tags[lat_ref_key]) == "S":
            lat = -lat
        if lon_ref_key in tags and str(tags[lon_ref_key]) == "W":
            lon = -lon

        alt = _get_tag_float(tags, alt_key)

        return GpsCoordinates(latitude=lat, longitude=lon, altitude=alt)
    except (ValueError, TypeError, IndexError, ZeroDivisionError):
        return None


def extract_exif(path: Path, include_raw: bool = False) -> ExifData:
    """Extract EXIF metadata from an image file.

    Args:
        path: Path to the image file
        include_raw: Whether to include raw tags in the result

    Returns:
        ExifData with extracted metadata

    Raises:
        ExifExtractionError: If extraction fails
    """
    import io
    import sys

    try:
        with open(path, "rb") as f:
            # Suppress exifread warnings (e.g., "PNG file does not have exif data")
            old_stderr = sys.stderr
            sys.stderr = io.StringIO()
            try:
                tags = exifread.process_file(f, details=False)
            finally:
                sys.stderr = old_stderr
    except Exception as e:
        raise ExifExtractionError(f"Failed to read EXIF from {path}: {e}") from e

    # Date taken (try multiple tags)
    date_taken = None
    for date_tag in [
        "EXIF DateTimeOriginal",
        "EXIF DateTimeDigitized",
        "Image DateTime",
    ]:
        if date_tag in tags:
            date_taken = _parse_datetime(str(tags[date_tag]))
            if date_taken:
                break

    # Build result
    result = ExifData(
        date_taken=date_taken,
        camera_make=_get_tag_value(tags, "Image Make"),
        camera_model=_get_tag_value(tags, "Image Model"),
        lens=_get_tag_value(tags, "EXIF LensModel"),
        focal_length=_get_tag_float(tags, "EXIF FocalLength"),
        aperture=_get_tag_float(tags, "EXIF FNumber"),
        shutter_speed=_get_tag_value(tags, "EXIF ExposureTime"),
        iso=_get_tag_int(tags, "EXIF ISOSpeedRatings"),
        width=_get_tag_int(tags, "EXIF ExifImageWidth"),
        height=_get_tag_int(tags, "EXIF ExifImageLength"),
        orientation=_get_tag_int(tags, "Image Orientation"),
        gps=_extract_gps(tags),
    )

    if include_raw:
        result.raw_tags = {k: str(v) for k, v in tags.items()}

    return result
