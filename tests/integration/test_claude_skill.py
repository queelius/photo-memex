"""Integration tests for Claude Code skill management."""

import pytest
from pathlib import Path
import shutil
from typer.testing import CliRunner

from ptk.cli import app
from ptk.skills import install, uninstall, is_installed, get_skill_dir


runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_skill_installation():
    """Ensure clean skill state before and after each test."""
    skill_dir = get_skill_dir()

    # Clean up before test
    if skill_dir.exists():
        shutil.rmtree(skill_dir)

    yield

    # Clean up after test
    if skill_dir.exists():
        shutil.rmtree(skill_dir)


class TestSkillInstaller:
    """Tests for skill install/uninstall functions."""

    def test_is_installed_when_not_installed(self):
        """Should return False when skill is not installed."""
        assert is_installed() is False

    def test_install_creates_skill_dir(self):
        """Install should create skill directory with SKILL.md."""
        success, msg = install()
        assert success is True
        assert is_installed() is True
        assert (get_skill_dir() / "SKILL.md").exists()

    def test_install_creates_reference_md(self):
        """Install should create reference.md."""
        install()
        assert (get_skill_dir() / "reference.md").exists()

    def test_install_fails_if_already_installed(self):
        """Install without force should fail if already installed."""
        install()
        success, msg = install(force=False)
        assert success is False
        assert "already installed" in msg.lower()

    def test_install_force_overwrites(self):
        """Install with force should overwrite existing."""
        install()
        success, msg = install(force=True)
        assert success is True

    def test_uninstall_removes_skill(self):
        """Uninstall should remove skill directory."""
        install()
        assert is_installed() is True

        success, msg = uninstall()
        assert success is True
        assert is_installed() is False
        assert not get_skill_dir().exists()

    def test_uninstall_when_not_installed(self):
        """Uninstall should fail gracefully when not installed."""
        success, msg = uninstall()
        assert success is False
        assert "not installed" in msg.lower()


class TestClaudeCLI:
    """Tests for ptk claude CLI commands."""

    def test_claude_status_not_installed(self):
        """Status should indicate not installed."""
        result = runner.invoke(app, ["claude", "status"])
        assert result.exit_code == 0
        assert "not installed" in result.output.lower()

    def test_claude_install(self):
        """Install command should install skill."""
        result = runner.invoke(app, ["claude", "install"])
        assert result.exit_code == 0
        assert is_installed() is True

    def test_claude_status_installed(self):
        """Status should indicate installed after install."""
        runner.invoke(app, ["claude", "install"])
        result = runner.invoke(app, ["claude", "status"])
        assert result.exit_code == 0
        assert "installed" in result.output.lower()
        assert str(get_skill_dir()) in result.output

    def test_claude_install_force(self):
        """Install --force should work when already installed."""
        runner.invoke(app, ["claude", "install"])
        result = runner.invoke(app, ["claude", "install", "--force"])
        assert result.exit_code == 0

    def test_claude_uninstall(self):
        """Uninstall command should remove skill."""
        runner.invoke(app, ["claude", "install"])
        result = runner.invoke(app, ["claude", "uninstall"])
        assert result.exit_code == 0
        assert is_installed() is False

    def test_claude_show_not_installed(self):
        """Show should fail when not installed."""
        result = runner.invoke(app, ["claude", "show"])
        assert result.exit_code == 1
        assert "not installed" in result.output.lower()

    def test_claude_show_installed(self):
        """Show should display skill content when installed."""
        runner.invoke(app, ["claude", "install"])
        result = runner.invoke(app, ["claude", "show"])
        assert result.exit_code == 0
        assert "ptk-photo-toolkit" in result.output

    def test_claude_help(self):
        """Claude help should list all subcommands."""
        result = runner.invoke(app, ["claude", "--help"])
        assert result.exit_code == 0
        assert "install" in result.output
        assert "uninstall" in result.output
        assert "status" in result.output
        assert "show" in result.output
