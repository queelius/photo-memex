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

    @property
    def ephemeral_root(self) -> Optional[Path]:
        """Directory whose contents do not outlive this import, if any.

        Importers that materialize scanned items into a temporary location
        (e.g. unzipping a Takeout archive) return that root here. Yielded
        ``ImportItem`` paths under it are valid only until ``cleanup()``
        runs, so the import service copies such files into a durable,
        library-managed location and records that durable path instead.

        Returns None when scanned paths already live in durable storage
        (the default, e.g. a plain filesystem import).
        """
        return None

    def cleanup(self) -> None:
        """Release any resources held for the duration of an import.

        Default is a no-op. Importers that extract to a temporary location
        (e.g. unzipping a Takeout archive) override this to delete it. The
        caller (ImportService) invokes it once item processing is complete,
        so yielded ``ImportItem`` paths stay valid until then — a generator
        that auto-deletes its temp dir on exhaustion breaks any consumer
        that materializes the items before reading them.
        """
        pass
