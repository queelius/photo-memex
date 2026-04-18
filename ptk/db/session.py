"""Database session management for ptk."""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ptk.db.models import Base

# Module-level engine and session factory
_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record) -> None:
    """Enable foreign keys and WAL mode for SQLite."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def _setup_fts(engine: Engine) -> None:
    """Create FTS5 virtual table and sync triggers for photo captions.

    The index excludes archived photos: insert only fires for active rows,
    and the archive trigger removes/restores rows as archived_at toggles.
    Consumers can MATCH against photos_fts directly without joining for
    the archived filter.
    """
    with engine.connect() as conn:
        raw = conn.connection.dbapi_connection
        raw.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS photos_fts
            USING fts5(id UNINDEXED, caption, location_name);

            CREATE TRIGGER IF NOT EXISTS photos_fts_insert AFTER INSERT ON photos
            WHEN new.archived_at IS NULL
            BEGIN
                INSERT INTO photos_fts(id, caption, location_name)
                VALUES (new.id, new.caption, new.location_name);
            END;

            CREATE TRIGGER IF NOT EXISTS photos_fts_update AFTER UPDATE OF caption, location_name ON photos
            WHEN new.archived_at IS NULL
            BEGIN
                DELETE FROM photos_fts WHERE id = old.id;
                INSERT INTO photos_fts(id, caption, location_name)
                VALUES (new.id, new.caption, new.location_name);
            END;

            CREATE TRIGGER IF NOT EXISTS photos_fts_archive AFTER UPDATE OF archived_at ON photos BEGIN
                DELETE FROM photos_fts WHERE id = old.id;
                INSERT INTO photos_fts(id, caption, location_name)
                SELECT new.id, new.caption, new.location_name
                WHERE new.archived_at IS NULL;
            END;

            CREATE TRIGGER IF NOT EXISTS photos_fts_delete AFTER DELETE ON photos BEGIN
                DELETE FROM photos_fts WHERE id = old.id;
            END;
        """)
        # Backfill: ensure index matches active-photo set exactly.
        raw.executescript("""
            DELETE FROM photos_fts
            WHERE id IN (SELECT id FROM photos WHERE archived_at IS NOT NULL);

            INSERT OR IGNORE INTO photos_fts(id, caption, location_name)
            SELECT id, caption, location_name FROM photos
            WHERE archived_at IS NULL
              AND id NOT IN (SELECT id FROM photos_fts);
        """)


def init_db(db_path: Path, create_tables: bool = True) -> Engine:
    """Initialize the database connection.

    Args:
        db_path: Path to the SQLite database file
        create_tables: Whether to create tables if they don't exist

    Returns:
        SQLAlchemy engine
    """
    global _engine, _SessionLocal

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Create engine
    _engine = create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    # Create session factory
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

    # Create tables
    if create_tables:
        Base.metadata.create_all(bind=_engine)
        _setup_fts(_engine)

    return _engine


def get_engine() -> Engine:
    """Get the database engine.

    Raises:
        RuntimeError: If database not initialized
    """
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _engine


def get_session() -> Session:
    """Get a new database session.

    Raises:
        RuntimeError: If database not initialized
    """
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _SessionLocal()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations.

    Usage:
        with session_scope() as session:
            session.add(photo)
            # auto-committed on exit, rolled back on exception
    """
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def close_db() -> None:
    """Close the database connection."""
    global _engine, _SessionLocal

    if _engine is not None:
        _engine.dispose()
        _engine = None
        _SessionLocal = None
