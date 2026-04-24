"""photo-memex - Personal photo library archive."""

# Read the installed-package version at runtime. This is robust to
# pytest configurations where a shadow package could hide the real one —
# importlib.metadata always consults dist-info.
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("photo-memex")
except PackageNotFoundError:
    __version__ = "unknown"

__author__ = "spinoza"
