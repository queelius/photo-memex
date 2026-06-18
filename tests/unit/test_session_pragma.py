"""F11: the SQLite PRAGMA hook must be registered on photo-memex's own
engine, not on the SQLAlchemy Engine class (which would force
foreign_keys/WAL onto every other engine in the process)."""

from __future__ import annotations

from sqlalchemy import create_engine, text


def test_pragma_listener_not_registered_on_engine_class():
    # Import the module so its (former) class-level listener would have been
    # registered at import time if the regression were present.
    import photo_memex.db.session  # noqa: F401

    # A fresh, unrelated SQLite engine must NOT inherit photo-memex's PRAGMAs.
    other = create_engine("sqlite://")
    try:
        with other.connect() as conn:
            fk = conn.execute(text("PRAGMA foreign_keys")).scalar()
            journal = conn.execute(text("PRAGMA journal_mode")).scalar()
        # SQLite defaults: foreign_keys OFF (0), in-memory journal "memory".
        assert fk == 0, "photo-memex forced foreign_keys ON a foreign engine"
        assert str(journal).lower() != "wal", "photo-memex forced WAL on a foreign engine"
    finally:
        other.dispose()


def test_photo_memex_engine_still_sets_pragmas(tmp_path):
    """The library's own engine must still get foreign_keys ON."""
    from photo_memex.db.session import close_db, init_db

    engine = init_db(tmp_path / "photo-memex.db")
    try:
        with engine.connect() as conn:
            fk = conn.execute(text("PRAGMA foreign_keys")).scalar()
        assert fk == 1
    finally:
        close_db()
