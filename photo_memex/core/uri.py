"""photo-memex URI builder and parser.

Public URI kinds:
    photo-memex://photo/<sha256>
    photo-memex://marginalia/<id>

Fragment support (positions inside a record):
    photo-memex://photo/<sha256>#region=x,y,w,h

The fragment is anything after the first ``#`` and is returned verbatim; it
addresses a position within a record (e.g. a cropped region), not a separate
record, so get_record resolves the base record and echoes the fragment.

This module intentionally has no SQLAlchemy dependency so it can be used by
both archive internals and external consumers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

SCHEME = "photo-memex"
KINDS: frozenset[str] = frozenset({"photo", "marginalia"})


class InvalidUriError(ValueError):
    """Raised when a URI string does not conform to the photo-memex scheme."""


@dataclass(frozen=True)
class ParsedUri:
    scheme: str
    kind: str
    id: str
    fragment: Optional[str]


# ---------------------------------------------------------------------------
# Public build helpers
# ---------------------------------------------------------------------------

def build_photo_uri(sha256: str) -> str:
    """Return ``photo-memex://photo/<sha256>``."""
    return _build("photo", sha256)


def build_marginalia_uri(note_id: int | str) -> str:
    """Return ``photo-memex://marginalia/<id>``."""
    return _build("marginalia", str(note_id))


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_uri(uri: str) -> ParsedUri:
    """Parse a photo-memex URI into its components.

    Raises :class:`InvalidUriError` on any structural problem.
    """
    if not isinstance(uri, str) or "://" not in uri:
        raise InvalidUriError(f"not a URI: {uri!r}")

    scheme, _, rest = uri.partition("://")
    if scheme != SCHEME:
        raise InvalidUriError(
            f"expected scheme {SCHEME!r}, got {scheme!r} in {uri!r}"
        )

    kind, _, tail = rest.partition("/")
    if kind not in KINDS:
        raise InvalidUriError(f"unknown kind {kind!r} in {uri!r}")

    ident, sep, fragment = tail.partition("#")
    if not ident:
        raise InvalidUriError(f"empty id in {uri!r}")

    return ParsedUri(
        scheme=scheme,
        kind=kind,
        id=ident,
        fragment=fragment if sep else None,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build(kind: str, ident: str) -> str:
    if not ident:
        raise ValueError(f"cannot build {kind} URI from empty id")
    if kind not in KINDS:
        raise ValueError(f"unknown URI kind: {kind}")
    return f"{SCHEME}://{kind}/{ident}"
