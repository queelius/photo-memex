"""Claude Code skill installer for ptk.

Manages installation and removal of the ptk skill that teaches
Claude Code how to work with photo libraries.
"""

import shutil
from pathlib import Path

# Skill installation directory
SKILL_DIR = Path.home() / ".claude" / "skills" / "ptk"

# Template directory (bundled with package)
TEMPLATES_DIR = Path(__file__).parent / "templates"


def get_skill_dir() -> Path:
    """Get the skill installation directory.

    Returns:
        Path to ~/.claude/skills/ptk/
    """
    return SKILL_DIR


def is_installed() -> bool:
    """Check if the ptk skill is installed.

    Returns:
        True if SKILL.md exists in the skill directory.
    """
    return (SKILL_DIR / "SKILL.md").exists()


def install(force: bool = False) -> tuple[bool, str]:
    """Install the ptk skill for Claude Code.

    Copies skill templates from the package to ~/.claude/skills/ptk/

    Args:
        force: If True, overwrite existing installation.

    Returns:
        Tuple of (success, message)
    """
    if is_installed() and not force:
        return False, "Skill already installed. Use --force to overwrite."

    # Check if templates exist
    if not TEMPLATES_DIR.exists():
        return False, f"Template directory not found: {TEMPLATES_DIR}"

    skill_md = TEMPLATES_DIR / "SKILL.md"
    if not skill_md.exists():
        return False, f"SKILL.md template not found: {skill_md}"

    try:
        # Create skill directory
        SKILL_DIR.mkdir(parents=True, exist_ok=True)

        # Copy all template files
        files_copied = []
        for template in TEMPLATES_DIR.iterdir():
            if template.is_file():
                dest = SKILL_DIR / template.name
                shutil.copy2(template, dest)
                files_copied.append(template.name)

        return True, f"Installed {len(files_copied)} files to {SKILL_DIR}"

    except OSError as e:
        return False, f"Installation failed: {e}"


def uninstall() -> tuple[bool, str]:
    """Remove the ptk skill from Claude Code.

    Removes the entire ~/.claude/skills/ptk/ directory.

    Returns:
        Tuple of (success, message)
    """
    if not is_installed():
        return False, "Skill is not installed."

    try:
        shutil.rmtree(SKILL_DIR)
        return True, f"Removed skill from {SKILL_DIR}"
    except OSError as e:
        return False, f"Uninstallation failed: {e}"


def get_skill_content() -> str | None:
    """Get the content of the installed SKILL.md.

    Returns:
        The content of SKILL.md, or None if not installed.
    """
    skill_md = SKILL_DIR / "SKILL.md"
    if skill_md.exists():
        return skill_md.read_text()
    return None


def get_template_content() -> str | None:
    """Get the content of the template SKILL.md (bundled with package).

    Returns:
        The content of the template SKILL.md, or None if not found.
    """
    skill_md = TEMPLATES_DIR / "SKILL.md"
    if skill_md.exists():
        return skill_md.read_text()
    return None
