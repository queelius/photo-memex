"""Base importer interface for photo-memex."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional, Any


@dataclass
class ImportItem:
    """A single item to be imported."""

    path: Path
    source_metadata: Optional[dict[str, Any]] = None


@dataclass
class ImportResult:
    """Result of an import operation."""

    total_files: int = 0
    imported: int = 0
    duplicates: int = 0
    errors: int = 0
    skipped: int = 0

    imported_ids: list[str] = field(default_factory=list)
    duplicate_ids: list[str] = field(default_factory=list)
    error_paths: list[tuple[str, str]] = field(default_factory=list)  # (path, error_msg)

    def __str__(self) -> str:
        parts = [f"Imported: {self.imported}"]
        if self.duplicates:
            parts.append(f"Duplicates: {self.duplicates}")
        if self.errors:
            parts.append(f"Errors: {self.errors}")
        if self.skipped:
            parts.append(f"Skipped: {self.skipped}")
        return ", ".join(parts)


class BaseImporter(ABC):
    """Abstract base class for photo importers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the importer."""
        pass

    @abstractmethod
    def can_handle(self, path: Path) -> bool:
        """Check if this importer can handle the given path.

        Args:
            path: Path to check (file or directory)

        Returns:
            True if this importer can handle the path
        """
        pass

    @abstractmethod
    def scan(self, path: Path) -> Iterator[ImportItem]:
        """Scan a path and yield items to import.

        Args:
            path: Path to scan

        Yields:
            ImportItem instances for each file to import
        """
        pass

    def extract_metadata(self, item: ImportItem) -> Optional[dict[str, Any]]:
        """Extract source-specific metadata for an item.

        Override in subclasses to provide source-specific metadata extraction.

        Args:
            item: The import item

        Returns:
            Dictionary of metadata or None
        """
        return item.source_metadata
