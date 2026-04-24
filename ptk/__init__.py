"""photo-memex - Personal photo library archive."""

# Read the installed-package version at runtime. This is robust to
# pytest configurations where a shadow package could hide the real one —
# importlib.metadata always consults dist-info.
try:
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("photo-memex")
except Exception:
    __version__ = "unknown"

__author__ = "spinoza"
