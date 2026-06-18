"""F7: a single unreadable/corrupt file must not abort the whole import.

import_from used to catch only a module-local ImportError that nothing
raises; real per-file errors (OSError from hashing/stat/open, including
Pillow's UnidentifiedImageError, or a ValueError from a bad source-metadata
date) propagated out, rolling back a multi-thousand-photo import. They are
now caught per item, recorded in result.error_paths, and skipped.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from photo_memex.core.config import get_config
from photo_memex.db.session import get_session
from photo_memex.importers.filesystem import FilesystemImporter
from photo_memex.services.import_service import ImportService


def test_unreadable_file_does_not_abort_batch(
    test_library, tmp_path, sample_image, monkeypatch
):
    src = tmp_path / "src"
    src.mkdir()
    shutil.copy(sample_image, src / "good.jpg")
    shutil.copy(sample_image, src / "bad.jpg")

    # Make exactly one file raise OSError at hash time (the first thing
    # _import_item does), simulating an unreadable/corrupt file.
    import photo_memex.services.import_service as svc_mod

    real_hash = svc_mod.hash_file

    def flaky_hash(path: Path) -> str:
        if Path(path).name == "bad.jpg":
            raise OSError("simulated unreadable file")
        return real_hash(path)

    monkeypatch.setattr(svc_mod, "hash_file", flaky_hash)

    svc = ImportService(get_session(), get_config())
    result = svc.import_from(FilesystemImporter(), src)

    # The good file imported; the bad one was recorded, not fatal.
    assert result.imported == 1
    assert result.errors == 1
    assert any("bad.jpg" in path for path, _ in result.error_paths)
