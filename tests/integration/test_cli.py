"""Integration tests for ptk CLI."""

import pytest
from pathlib import Path
from typer.testing import CliRunner

from photo_memex.cli import app
from photo_memex.core.constants import DEFAULT_DATABASE_NAME


runner = CliRunner()


def test_version():
    """Test --version flag."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "photo-memex version" in result.output


def test_help():
    """Test --help flag."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "photo-memex" in result.output


def test_init_creates_database(temp_dir: Path):
    """Test that init creates a database."""
    result = runner.invoke(app, ["init", str(temp_dir)])

    assert result.exit_code == 0
    assert "Initialized" in result.output
    assert (temp_dir / DEFAULT_DATABASE_NAME).exists()


def test_init_fails_if_exists(temp_dir: Path):
    """Test that init fails if library exists."""
    # First init
    runner.invoke(app, ["init", str(temp_dir)])

    # Second init should fail
    result = runner.invoke(app, ["init", str(temp_dir)])
    assert result.exit_code == 1
    assert "Library exists" in result.output or "already exists" in result.output


def test_init_force_overwrites(temp_dir: Path):
    """Test that init --force overwrites existing library."""
    runner.invoke(app, ["init", str(temp_dir)])
    result = runner.invoke(app, ["init", "--force", str(temp_dir)])

    assert result.exit_code == 0
    assert "Initialized" in result.output


def test_stats_empty_library(temp_dir: Path):
    """Test stats on empty library."""
    runner.invoke(app, ["init", str(temp_dir)])

    # Change to library directory for stats command
    import os
    original_cwd = os.getcwd()
    os.chdir(temp_dir)

    try:
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "Total photos" in result.output or "0" in result.output
    finally:
        os.chdir(original_cwd)


def test_query_empty_library(temp_dir: Path):
    """Test query on empty library."""
    runner.invoke(app, ["init", str(temp_dir)])

    import os
    original_cwd = os.getcwd()
    os.chdir(temp_dir)

    try:
        result = runner.invoke(app, ["q"])
        assert result.exit_code == 0
        assert "No photos found" in result.output
    finally:
        os.chdir(original_cwd)


def test_import_directory(temp_dir: Path, sample_image: Path):
    """Test importing from a directory."""
    import shutil

    # Setup library
    library_dir = temp_dir / "library"
    library_dir.mkdir()
    runner.invoke(app, ["init", str(library_dir)])

    # Setup photos directory
    photos_dir = temp_dir / "photos"
    photos_dir.mkdir()
    shutil.copy(sample_image, photos_dir / "photo1.jpg")

    import os
    original_cwd = os.getcwd()
    os.chdir(library_dir)

    try:
        result = runner.invoke(app, ["import", str(photos_dir)])
        assert result.exit_code == 0
        assert "Imported: 1" in result.output
    finally:
        os.chdir(original_cwd)


def test_import_dry_run(temp_dir: Path, sample_image: Path):
    """Test import --dry-run."""
    import shutil

    library_dir = temp_dir / "library"
    library_dir.mkdir()
    runner.invoke(app, ["init", str(library_dir)])

    photos_dir = temp_dir / "photos"
    photos_dir.mkdir()
    shutil.copy(sample_image, photos_dir / "photo1.jpg")

    import os
    original_cwd = os.getcwd()
    os.chdir(library_dir)

    try:
        result = runner.invoke(app, ["import", "--dry-run", str(photos_dir)])
        assert result.exit_code == 0
        assert "Dry run" in result.output

        # Check that nothing was actually imported
        query_result = runner.invoke(app, ["q"])
        assert "No photos found" in query_result.output
    finally:
        os.chdir(original_cwd)


def test_show_photo(temp_dir: Path, sample_image: Path):
    """Test showing photo details."""
    import shutil

    library_dir = temp_dir / "library"
    library_dir.mkdir()
    runner.invoke(app, ["init", str(library_dir)])

    photos_dir = temp_dir / "photos"
    photos_dir.mkdir()
    shutil.copy(sample_image, photos_dir / "photo1.jpg")

    import os
    original_cwd = os.getcwd()
    os.chdir(library_dir)

    try:
        # Import first
        runner.invoke(app, ["import", str(photos_dir)])

        # Query to get the IDs
        query_result = runner.invoke(app, ["q", "--format", "ids"])

        # Get the first ID
        photo_id = query_result.output.strip().split("\n")[0].strip()
        if not photo_id or photo_id == "No photos found.":
            pytest.fail("Could not find photo ID in query output")

        # Show the photo
        result = runner.invoke(app, ["show", photo_id])
        assert result.exit_code == 0
        assert "photo1.jpg" in result.output
    finally:
        os.chdir(original_cwd)


def test_query_with_format_json(temp_dir: Path, sample_image: Path):
    """Test query with JSON format."""
    import shutil
    import json

    library_dir = temp_dir / "library"
    library_dir.mkdir()
    runner.invoke(app, ["init", str(library_dir)])

    photos_dir = temp_dir / "photos"
    photos_dir.mkdir()
    shutil.copy(sample_image, photos_dir / "photo1.jpg")

    import os
    original_cwd = os.getcwd()
    os.chdir(library_dir)

    try:
        runner.invoke(app, ["import", str(photos_dir)])
        result = runner.invoke(app, ["q", "--format", "json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["filename"] == "photo1.jpg"
    finally:
        os.chdir(original_cwd)


def test_query_with_format_count(temp_dir: Path, sample_image: Path):
    """Test query with count format."""
    import shutil

    library_dir = temp_dir / "library"
    library_dir.mkdir()
    runner.invoke(app, ["init", str(library_dir)])

    photos_dir = temp_dir / "photos"
    photos_dir.mkdir()
    shutil.copy(sample_image, photos_dir / "photo1.jpg")

    import os
    original_cwd = os.getcwd()
    os.chdir(library_dir)

    try:
        runner.invoke(app, ["import", str(photos_dir)])
        result = runner.invoke(app, ["q", "--format", "count"])

        assert result.exit_code == 0
        assert "1" in result.output
    finally:
        os.chdir(original_cwd)


def test_set_favorite(temp_dir: Path, sample_image: Path):
    """Test setting a photo as favorite."""
    import shutil

    library_dir = temp_dir / "library"
    library_dir.mkdir()
    runner.invoke(app, ["init", str(library_dir)])

    photos_dir = temp_dir / "photos"
    photos_dir.mkdir()
    shutil.copy(sample_image, photos_dir / "photo1.jpg")

    import os
    original_cwd = os.getcwd()
    os.chdir(library_dir)

    try:
        runner.invoke(app, ["import", str(photos_dir)])

        # Get photo ID
        query_result = runner.invoke(app, ["q", "--format", "ids"])
        photo_id = query_result.output.strip().split("\n")[0].strip()

        # Set as favorite
        result = runner.invoke(app, ["set", photo_id, "--favorite"])
        assert result.exit_code == 0

        # Query favorites
        fav_result = runner.invoke(app, ["q", "--favorite", "--format", "count"])
        assert "1" in fav_result.output
    finally:
        os.chdir(original_cwd)


def test_set_tag(temp_dir: Path, sample_image: Path):
    """Test adding a tag to a photo."""
    import shutil

    library_dir = temp_dir / "library"
    library_dir.mkdir()
    runner.invoke(app, ["init", str(library_dir)])

    photos_dir = temp_dir / "photos"
    photos_dir.mkdir()
    shutil.copy(sample_image, photos_dir / "photo1.jpg")

    import os
    original_cwd = os.getcwd()
    os.chdir(library_dir)

    try:
        runner.invoke(app, ["import", str(photos_dir)])

        # Get photo ID
        query_result = runner.invoke(app, ["q", "--format", "ids"])
        photo_id = query_result.output.strip().split("\n")[0].strip()

        # Add tag
        result = runner.invoke(app, ["set", photo_id, "--tag", "beach"])
        assert result.exit_code == 0

        # Query by tag
        tag_result = runner.invoke(app, ["q", "--tag", "beach", "--format", "count"])
        assert "1" in tag_result.output
    finally:
        os.chdir(original_cwd)


# ---------------------------------------------------------------------------
# [R3] Hardened CLI photo resolution for show / set
# ---------------------------------------------------------------------------


def _init_library_with_photos(library_dir: Path, ids: list[str]) -> None:
    """Init a library in ``library_dir`` and insert photos with controlled IDs."""
    from datetime import UTC, datetime

    from photo_memex.core.config import PtkConfig, set_config
    from photo_memex.db.models import Photo
    from photo_memex.db.session import init_db, session_scope

    runner.invoke(app, ["init", str(library_dir)])
    config = PtkConfig(library_path=library_dir)
    set_config(config)
    init_db(config.database_path, create_tables=False)
    with session_scope() as session:
        for pid in ids:
            session.add(
                Photo(
                    id=pid,
                    original_path=f"/tmp/{pid[:8]}.jpg",
                    filename=f"{pid[:8]}.jpg",
                    file_size=10,
                    mime_type="image/jpeg",
                    date_imported=datetime.now(UTC),
                )
            )


def test_set_rejects_ambiguous_prefix(temp_dir: Path):
    """An ambiguous prefix must raise rather than mutate the first match."""
    import os

    from photo_memex.db.models import Photo
    from photo_memex.db.session import close_db, session_scope

    library_dir = temp_dir / "library"
    library_dir.mkdir()
    id_a = "abcd" + "1" * 60
    id_b = "abcd" + "2" * 60
    _init_library_with_photos(library_dir, [id_a, id_b])
    close_db()

    original_cwd = os.getcwd()
    os.chdir(library_dir)
    try:
        result = runner.invoke(app, ["set", "abcd", "--favorite"])
        assert result.exit_code != 0
        assert "ambiguous" in result.output.lower()

        # Neither photo was mutated.
        from photo_memex.core.config import PtkConfig, set_config
        from photo_memex.db.session import init_db

        set_config(PtkConfig(library_path=library_dir))
        init_db(library_dir / "photo-memex.db", create_tables=False)
        with session_scope() as session:
            favs = session.query(Photo).filter(Photo.is_favorite.is_(True)).count()
        assert favs == 0
    finally:
        os.chdir(original_cwd)
        close_db()


def test_set_rejects_short_prefix(temp_dir: Path):
    """A prefix shorter than 4 hex chars must raise, not mutate."""
    import os

    from photo_memex.db.session import close_db

    library_dir = temp_dir / "library"
    library_dir.mkdir()
    pid = "abcd" + "1" * 60
    _init_library_with_photos(library_dir, [pid])
    close_db()

    original_cwd = os.getcwd()
    os.chdir(library_dir)
    try:
        result = runner.invoke(app, ["set", "ab", "--favorite"])
        assert result.exit_code != 0
        assert "4" in result.output
    finally:
        os.chdir(original_cwd)
        close_db()


def test_set_rejects_wildcard_prefix(temp_dir: Path):
    """A LIKE-wildcard-bearing prefix must not match any photo."""
    import os

    from photo_memex.db.models import Photo
    from photo_memex.db.session import close_db, session_scope

    library_dir = temp_dir / "library"
    library_dir.mkdir()
    pid = "abcd" + "1" * 60
    _init_library_with_photos(library_dir, [pid])
    close_db()

    original_cwd = os.getcwd()
    os.chdir(library_dir)
    try:
        result = runner.invoke(app, ["set", "a_cd", "--favorite"])
        assert result.exit_code != 0

        from photo_memex.core.config import PtkConfig, set_config
        from photo_memex.db.session import init_db

        set_config(PtkConfig(library_path=library_dir))
        init_db(library_dir / "photo-memex.db", create_tables=False)
        with session_scope() as session:
            favs = session.query(Photo).filter(Photo.is_favorite.is_(True)).count()
        assert favs == 0
    finally:
        os.chdir(original_cwd)
        close_db()


def test_set_does_not_resolve_archived_photo(temp_dir: Path):
    """An archived photo must not be resolvable for mutation."""
    import os
    from datetime import UTC, datetime

    from photo_memex.core.config import PtkConfig, set_config
    from photo_memex.db.models import Photo
    from photo_memex.db.session import close_db, init_db, session_scope

    library_dir = temp_dir / "library"
    library_dir.mkdir()
    pid = "feed" + "1" * 60
    _init_library_with_photos(library_dir, [pid])
    # Archive it.
    with session_scope() as session:
        photo = session.query(Photo).filter(Photo.id == pid).one()
        photo.archived_at = datetime.now(UTC)
    close_db()

    original_cwd = os.getcwd()
    os.chdir(library_dir)
    try:
        result = runner.invoke(app, ["set", pid[:8], "--favorite"])
        assert result.exit_code != 0

        set_config(PtkConfig(library_path=library_dir))
        init_db(library_dir / "photo-memex.db", create_tables=False)
        with session_scope() as session:
            photo = session.query(Photo).filter(Photo.id == pid).one()
            assert photo.is_favorite is False
    finally:
        os.chdir(original_cwd)
        close_db()


def test_show_rejects_ambiguous_prefix(temp_dir: Path):
    """show must refuse an ambiguous prefix rather than silently pick one."""
    import os

    from photo_memex.db.session import close_db

    library_dir = temp_dir / "library"
    library_dir.mkdir()
    id_a = "abcd" + "1" * 60
    id_b = "abcd" + "2" * 60
    _init_library_with_photos(library_dir, [id_a, id_b])
    close_db()

    original_cwd = os.getcwd()
    os.chdir(library_dir)
    try:
        result = runner.invoke(app, ["show", "abcd"])
        assert result.exit_code != 0
        assert "ambiguous" in result.output.lower()
    finally:
        os.chdir(original_cwd)
        close_db()
