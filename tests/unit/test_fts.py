"""Tests for FTS5 full-text search over photo captions."""

import sqlite3
from datetime import UTC, datetime

from photo_memex.db.models import Photo
from photo_memex.db.session import get_engine


def _raw_conn() -> sqlite3.Connection:
    """Open a raw sqlite3 connection to the test database."""
    url = str(get_engine().url).replace("sqlite:///", "")
    return sqlite3.connect(url)


def _fts_search(term: str) -> list[tuple]:
    """Run an FTS5 MATCH query and return all matching rows."""
    conn = _raw_conn()
    results = conn.execute(
        "SELECT id FROM photos_fts WHERE photos_fts MATCH ?", (term,)
    ).fetchall()
    conn.close()
    return results


class TestFts5Setup:
    """Verify FTS5 virtual table is created and synced."""

    def test_fts_table_exists(self, test_library):
        conn = _raw_conn()
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        conn.close()
        assert "photos_fts" in tables

    def test_fts_search_finds_captioned_photo(self, populated_library, db_session):
        photo = db_session.query(Photo).first()
        photo.caption = "beautiful sunset over the ocean"
        db_session.commit()

        results = _fts_search("sunset")
        assert len(results) == 1
        assert results[0][0] == photo.id

    def test_fts_no_match(self, populated_library, db_session):
        photo = db_session.query(Photo).first()
        photo.caption = "a red test image"
        db_session.commit()

        results = _fts_search("sunset")
        assert len(results) == 0

    def test_fts_updates_on_caption_change(self, populated_library, db_session):
        photo = db_session.query(Photo).first()
        photo.caption = "old caption"
        db_session.commit()

        photo.caption = "new sunset caption"
        db_session.commit()

        results = _fts_search("sunset")
        assert len(results) == 1

    def test_fts_excludes_archived_photo(self, populated_library, db_session):
        """Archiving a photo should remove it from the FTS index."""
        photo = db_session.query(Photo).first()
        photo.caption = "archived sunset"
        db_session.commit()

        assert len(_fts_search("sunset")) == 1

        photo.archived_at = datetime.now(UTC)
        db_session.commit()

        assert len(_fts_search("sunset")) == 0

    def test_fts_restores_on_unarchive(self, populated_library, db_session):
        """Un-archiving a photo should restore it to the FTS index."""
        photo = db_session.query(Photo).first()
        photo.caption = "lighthouse at dusk"
        photo.archived_at = datetime.now(UTC)
        db_session.commit()

        assert len(_fts_search("lighthouse")) == 0

        photo.archived_at = None
        db_session.commit()

        assert len(_fts_search("lighthouse")) == 1
