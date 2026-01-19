"""Filesystem importer for local directories."""

from pathlib import Path
from typing import Iterator

from ptk.core.constants import SUPPORTED_FORMATS
from ptk.importers.base import BaseImporter, ImportItem


class FilesystemImporter(BaseImporter):
    """Import photos from local filesystem directories."""

    def __init__(self, recursive: bool = True, skip_hidden: bool = True):
        """Initialize the filesystem importer.

        Args:
            recursive: Whether to scan subdirectories
            skip_hidden: Whether to skip hidden files (starting with .)
        """
        self.recursive = recursive
        self.skip_hidden = skip_hidden

    @property
    def name(self) -> str:
        return "filesystem"

    def can_handle(self, path: Path) -> bool:
        """Check if path is a directory or supported file."""
        if path.is_dir():
            return True
        if path.is_file():
            return path.suffix.lower() in SUPPORTED_FORMATS
        return False

    def scan(self, path: Path) -> Iterator[ImportItem]:
        """Scan directory for photos.

        Args:
            path: Directory or file to scan

        Yields:
            ImportItem for each found photo
        """
        if path.is_file():
            if self._is_valid_file(path):
                yield ImportItem(path=path)
            return

        if not path.is_dir():
            return

        if self.recursive:
            files = path.rglob("*")
        else:
            files = path.glob("*")

        for file_path in files:
            if self._is_valid_file(file_path):
                yield ImportItem(path=file_path)

    def _is_valid_file(self, path: Path) -> bool:
        """Check if a file should be imported."""
        if not path.is_file():
            return False

        # Skip hidden files
        if self.skip_hidden and path.name.startswith("."):
            return False

        # Check extension
        return path.suffix.lower() in SUPPORTED_FORMATS
