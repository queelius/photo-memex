"""File hashing utilities for deduplication."""

import hashlib
from pathlib import Path

from photo_memex.core.constants import HASH_CHUNK_SIZE


def hash_file(path: Path) -> str:
    """Compute SHA256 hash of a file.

    Args:
        path: Path to the file to hash

    Returns:
        Lowercase hex digest of the SHA256 hash
    """
    hasher = hashlib.sha256()

    with open(path, "rb") as f:
        while chunk := f.read(HASH_CHUNK_SIZE):
            hasher.update(chunk)

    return hasher.hexdigest()


def hash_bytes(data: bytes) -> str:
    """Compute SHA256 hash of bytes.

    Args:
        data: Bytes to hash

    Returns:
        Lowercase hex digest of the SHA256 hash
    """
    return hashlib.sha256(data).hexdigest()
