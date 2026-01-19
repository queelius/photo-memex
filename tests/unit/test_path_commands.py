"""Tests for path management commands: verify, relocate, rescan."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from ptk.cli import app
from ptk.db.models import Photo, Tag


runner = CliRunner()


@pytest.fixture
def mock_session():
    """Create a mock session with test photos."""
    session = MagicMock()
    return session


class TestVerifyCommand:
    """Tests for ptk verify command."""

    def test_verify_help(self):
        """Test verify --help works."""
        result = runner.invoke(app, ["verify", "--help"])
        assert result.exit_code == 0
        assert "Verify all photo paths exist on disk" in result.output

    @patch("ptk.cli._require_library")
    @patch("ptk.cli.session_scope")
    def test_verify_all_found(self, mock_scope, mock_require):
        """Test verify when all photos exist."""
        # Create a temp file that exists
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            temp_path = f.name

        try:
            mock_photo = MagicMock()
            mock_photo.id = "abc123" * 10 + "abcd"
            mock_photo.original_path = temp_path

            mock_session = MagicMock()
            mock_session.query.return_value.all.return_value = [mock_photo]
            mock_scope.return_value.__enter__.return_value = mock_session

            result = runner.invoke(app, ["verify"])

            assert result.exit_code == 0
            assert "Found: 1" in result.output
            assert "Missing: 0" in result.output
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @patch("ptk.cli._require_library")
    @patch("ptk.cli.session_scope")
    def test_verify_missing_photo(self, mock_scope, mock_require):
        """Test verify when a photo is missing."""
        mock_photo = MagicMock()
        mock_photo.id = "abc123" * 10 + "abcd"
        mock_photo.original_path = "/nonexistent/path/photo.jpg"

        mock_session = MagicMock()
        mock_session.query.return_value.all.return_value = [mock_photo]
        mock_scope.return_value.__enter__.return_value = mock_session

        result = runner.invoke(app, ["verify"])

        assert result.exit_code == 0
        assert "Found: 0" in result.output
        assert "Missing: 1" in result.output

    @patch("ptk.cli._require_library")
    @patch("ptk.cli.session_scope")
    def test_verify_empty_library(self, mock_scope, mock_require):
        """Test verify with no photos."""
        mock_session = MagicMock()
        mock_session.query.return_value.all.return_value = []
        mock_scope.return_value.__enter__.return_value = mock_session

        result = runner.invoke(app, ["verify"])

        assert result.exit_code == 0
        assert "No photos in library" in result.output


class TestRelocateCommand:
    """Tests for ptk relocate command."""

    def test_relocate_help(self):
        """Test relocate --help works."""
        result = runner.invoke(app, ["relocate", "--help"])
        assert result.exit_code == 0
        assert "Bulk update path prefixes" in result.output

    @patch("ptk.cli._require_library")
    @patch("ptk.cli.session_scope")
    def test_relocate_dry_run(self, mock_scope, mock_require):
        """Test relocate with --dry-run."""
        mock_photo = MagicMock()
        mock_photo.original_path = "/old/path/photo.jpg"

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = [mock_photo]
        mock_scope.return_value.__enter__.return_value = mock_session

        result = runner.invoke(app, ["relocate", "/old/path", "/new/path", "--dry-run"])

        assert result.exit_code == 0
        assert "Dry run: would update 1 paths" in result.output
        # Path should NOT be changed in dry run
        assert mock_photo.original_path == "/old/path/photo.jpg"

    @patch("ptk.cli._require_library")
    @patch("ptk.cli.session_scope")
    def test_relocate_updates_path(self, mock_scope, mock_require):
        """Test relocate actually updates paths."""
        mock_photo = MagicMock()
        mock_photo.original_path = "/old/path/photo.jpg"

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = [mock_photo]
        mock_scope.return_value.__enter__.return_value = mock_session

        result = runner.invoke(app, ["relocate", "/old/path", "/new/path"])

        assert result.exit_code == 0
        assert "Updated: 1" in result.output
        assert mock_photo.original_path == "/new/path/photo.jpg"

    @patch("ptk.cli._require_library")
    @patch("ptk.cli.session_scope")
    def test_relocate_no_matches(self, mock_scope, mock_require):
        """Test relocate when no paths match."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        mock_scope.return_value.__enter__.return_value = mock_session

        result = runner.invoke(app, ["relocate", "/nonexistent", "/new"])

        assert result.exit_code == 0
        assert "No photos found with prefix" in result.output


class TestRescanCommand:
    """Tests for ptk rescan command."""

    def test_rescan_help(self):
        """Test rescan --help works."""
        result = runner.invoke(app, ["rescan", "--help"])
        assert result.exit_code == 0
        assert "Find moved photos by content hash" in result.output

    @patch("ptk.cli._require_library")
    def test_rescan_nonexistent_directory(self, mock_require):
        """Test rescan with nonexistent directory."""
        result = runner.invoke(app, ["rescan", "/nonexistent/directory"])

        assert result.exit_code == 1
        assert "Directory not found" in result.output

    @patch("ptk.cli._require_library")
    @patch("ptk.cli.session_scope")
    def test_rescan_empty_library(self, mock_scope, mock_require):
        """Test rescan with no photos in library."""
        mock_session = MagicMock()
        mock_session.query.return_value.all.return_value = []
        mock_scope.return_value.__enter__.return_value = mock_session

        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(app, ["rescan", tmpdir])

        assert result.exit_code == 0
        assert "No photos to search for" in result.output

    @patch("ptk.cli._require_library")
    @patch("ptk.cli.session_scope")
    @patch("ptk.core.hasher.hash_file")
    def test_rescan_finds_moved_photo(self, mock_hash, mock_scope, mock_require):
        """Test rescan finds and updates a moved photo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = Path(tmpdir) / "photo.jpg"
            test_file.write_bytes(b"fake image data")

            # Mock the hash
            file_hash = "abc123" * 10 + "abcd"
            mock_hash.return_value = file_hash

            # Mock photo with old path
            mock_photo = MagicMock()
            mock_photo.id = file_hash
            mock_photo.original_path = "/old/location/photo.jpg"

            mock_session = MagicMock()
            mock_session.query.return_value.all.return_value = [mock_photo]
            mock_scope.return_value.__enter__.return_value = mock_session

            result = runner.invoke(app, ["rescan", tmpdir])

            assert result.exit_code == 0
            assert "Found: 1 photos" in result.output
            assert "Updated paths: 1" in result.output

    @patch("ptk.cli._require_library")
    @patch("ptk.cli.session_scope")
    @patch("ptk.core.hasher.hash_file")
    def test_rescan_dry_run(self, mock_hash, mock_scope, mock_require):
        """Test rescan --dry-run doesn't modify."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = Path(tmpdir) / "photo.jpg"
            test_file.write_bytes(b"fake image data")

            file_hash = "abc123" * 10 + "abcd"
            mock_hash.return_value = file_hash

            mock_photo = MagicMock()
            mock_photo.id = file_hash
            mock_photo.original_path = "/old/location/photo.jpg"

            mock_session = MagicMock()
            mock_session.query.return_value.all.return_value = [mock_photo]
            mock_scope.return_value.__enter__.return_value = mock_session

            result = runner.invoke(app, ["rescan", tmpdir, "--dry-run"])

            assert result.exit_code == 0
            assert "Dry run: no changes made" in result.output
            # Path should NOT be changed
            assert mock_photo.original_path == "/old/location/photo.jpg"
