"""Tests for arkiv export functionality.

Output shape (2026-04, workspace C5a contract):
- records.jsonl : one JSON record per photo + marginalia
- schema.yaml   : scheme/counts/kinds structure
- README.md     : ECHO frontmatter

Three bundle formats: directory, .zip, .tar.gz.
"""

import json
import tarfile
import zipfile
from pathlib import Path

import pytest
import yaml

from ptk.db.models import Marginalia, Photo, Tag


@pytest.fixture
def library_with_tagged_photo(populated_library, db_session):
    """Create a library with a photo that has tags and a caption."""
    photo = db_session.query(Photo).first()
    photo.caption = "A red test image"
    photo.is_favorite = True
    tag = Tag(name="test-tag")
    db_session.add(tag)
    photo.tags.append(tag)
    db_session.commit()
    return populated_library


def _read_records_dir(out_dir: Path) -> list[dict]:
    text = (out_dir / "records.jsonl").read_text()
    return [json.loads(ln) for ln in text.strip().split("\n") if ln.strip()]


def _read_records_zip(path: Path) -> list[dict]:
    with zipfile.ZipFile(path) as zf:
        text = zf.read("records.jsonl").decode()
    return [json.loads(ln) for ln in text.strip().split("\n") if ln.strip()]


def _read_records_tar_gz(path: Path) -> list[dict]:
    with tarfile.open(path, "r:gz") as tf:
        data = tf.extractfile("records.jsonl").read().decode()
    return [json.loads(ln) for ln in data.strip().split("\n") if ln.strip()]


class TestArkivExport:
    """Directory bundle shape."""

    def test_creates_output_directory(self, library_with_tagged_photo, tmp_path):
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "arkiv-out"
        export_arkiv(out)
        assert out.is_dir()

    def test_creates_readme(self, library_with_tagged_photo, tmp_path):
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "arkiv-out"
        export_arkiv(out)
        readme = out / "README.md"
        assert readme.exists()
        content = readme.read_text()
        assert content.startswith("---\n")
        parts = content.split("---\n", 2)
        assert len(parts) >= 3
        frontmatter = yaml.safe_load(parts[1])
        assert "generator" in frontmatter
        assert frontmatter["generator"].startswith("photo-memex")

    def test_readme_contains_photo_count(self, library_with_tagged_photo, tmp_path):
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "arkiv-out"
        count = export_arkiv(out)

        readme = out / "README.md"
        content = readme.read_text()
        parts = content.split("---\n", 2)
        frontmatter = yaml.safe_load(parts[1])
        assert f"{count} photos" in frontmatter["description"]

    def test_readme_contents_list(self, library_with_tagged_photo, tmp_path):
        """README frontmatter lists records.jsonl in contents."""
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "arkiv-out"
        export_arkiv(out)

        readme = out / "README.md"
        content = readme.read_text()
        parts = content.split("---\n", 2)
        frontmatter = yaml.safe_load(parts[1])
        assert "contents" in frontmatter
        paths = [c["path"] for c in frontmatter["contents"]]
        assert "records.jsonl" in paths

    def test_creates_records_jsonl(self, library_with_tagged_photo, tmp_path):
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "arkiv-out"
        export_arkiv(out)
        assert (out / "records.jsonl").exists()

    def test_jsonl_one_record_per_photo(
        self, library_with_tagged_photo, tmp_path, db_session
    ):
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "arkiv-out"
        count = export_arkiv(out)

        records = _read_records_dir(out)
        photo_records = [r for r in records if r["kind"] == "photo"]
        assert len(photo_records) == count

        total_photos = (
            db_session.query(Photo).filter(Photo.archived_at.is_(None)).count()
        )
        assert count == total_photos

    def test_jsonl_record_has_required_fields(
        self, library_with_tagged_photo, tmp_path
    ):
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "arkiv-out"
        export_arkiv(out)
        rec = next(r for r in _read_records_dir(out) if r["kind"] == "photo")
        assert "kind" in rec
        assert "uri" in rec
        assert "source_path" in rec
        assert "mimetype" in rec
        assert "metadata" in rec

    def test_jsonl_metadata_sha256(
        self, library_with_tagged_photo, tmp_path, db_session
    ):
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "arkiv-out"
        export_arkiv(out)
        rec = next(r for r in _read_records_dir(out) if r["kind"] == "photo")
        photo = db_session.query(Photo).first()
        assert rec["metadata"]["sha256"] == photo.id
        assert len(rec["metadata"]["sha256"]) == 64

    def test_jsonl_metadata_tags(self, library_with_tagged_photo, tmp_path):
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "arkiv-out"
        export_arkiv(out)
        rec = next(r for r in _read_records_dir(out) if r["kind"] == "photo")
        assert "tags" in rec["metadata"]
        assert "test-tag" in rec["metadata"]["tags"]

    def test_jsonl_metadata_caption(self, library_with_tagged_photo, tmp_path):
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "arkiv-out"
        export_arkiv(out)
        rec = next(r for r in _read_records_dir(out) if r["kind"] == "photo")
        assert rec["metadata"]["caption"] == "A red test image"

    def test_jsonl_source_path_starts_with_file(
        self, library_with_tagged_photo, tmp_path
    ):
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "arkiv-out"
        export_arkiv(out)
        rec = next(r for r in _read_records_dir(out) if r["kind"] == "photo")
        assert rec["source_path"].startswith("file:///")

    def test_jsonl_mimetype(
        self, library_with_tagged_photo, tmp_path, db_session
    ):
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "arkiv-out"
        export_arkiv(out)
        rec = next(r for r in _read_records_dir(out) if r["kind"] == "photo")
        photo = db_session.query(Photo).first()
        assert rec["mimetype"] == photo.mime_type

    def test_creates_schema_yaml(self, library_with_tagged_photo, tmp_path):
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "arkiv-out"
        export_arkiv(out)
        assert (out / "schema.yaml").exists()

    def test_schema_has_scheme_and_kinds(
        self, library_with_tagged_photo, tmp_path
    ):
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "arkiv-out"
        export_arkiv(out)
        schema = yaml.safe_load((out / "schema.yaml").read_text())
        assert schema["scheme"] == "photo-memex"
        assert "photo" in schema["kinds"]
        assert "marginalia" in schema["kinds"]
        assert "metadata_keys" in schema["kinds"]["photo"]

    def test_schema_metadata_keys_types(
        self, library_with_tagged_photo, tmp_path
    ):
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "arkiv-out"
        export_arkiv(out)
        schema = yaml.safe_load((out / "schema.yaml").read_text())
        photo_keys = schema["kinds"]["photo"]["metadata_keys"]
        assert "sha256" in photo_keys
        assert photo_keys["sha256"] == "string"

    def test_schema_counts_are_populated(
        self, library_with_tagged_photo, tmp_path, db_session
    ):
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "arkiv-out"
        export_arkiv(out)
        schema = yaml.safe_load((out / "schema.yaml").read_text())
        live_photos = (
            db_session.query(Photo).filter(Photo.archived_at.is_(None)).count()
        )
        assert schema["counts"]["photo"] == live_photos

    def test_null_fields_omitted(self, populated_library, db_session, tmp_path):
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "arkiv-out"
        export_arkiv(out)
        rec = next(r for r in _read_records_dir(out) if r["kind"] == "photo")
        assert "caption" not in rec["metadata"]
        assert "tags" not in rec["metadata"]

    def test_is_favorite_in_metadata(self, library_with_tagged_photo, tmp_path):
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "arkiv-out"
        export_arkiv(out)
        rec = next(r for r in _read_records_dir(out) if r["kind"] == "photo")
        assert rec["metadata"]["is_favorite"] is True

    def test_returns_photo_count(
        self, library_with_tagged_photo, tmp_path, db_session
    ):
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "arkiv-out"
        count = export_arkiv(out)
        total = (
            db_session.query(Photo).filter(Photo.archived_at.is_(None)).count()
        )
        assert count == total
        assert count > 0

    def test_custom_title(self, library_with_tagged_photo, tmp_path):
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "arkiv-out"
        export_arkiv(out, title="My Photo Archive")
        content = (out / "README.md").read_text()
        parts = content.split("---\n", 2)
        frontmatter = yaml.safe_load(parts[1])
        assert frontmatter["name"] == "My Photo Archive"

    def test_tags_are_sorted(self, populated_library, db_session, tmp_path):
        from ptk.exports.arkiv import export_arkiv

        photo = db_session.query(Photo).first()
        tag_z = Tag(name="zebra")
        tag_a = Tag(name="alpha")
        db_session.add_all([tag_z, tag_a])
        photo.tags.extend([tag_z, tag_a])
        db_session.commit()

        out = tmp_path / "arkiv-out"
        export_arkiv(out)
        rec = next(r for r in _read_records_dir(out) if r["kind"] == "photo")
        tags = rec["metadata"]["tags"]
        assert tags == sorted(tags)
        assert tags == ["alpha", "zebra"]

    def test_jsonl_record_has_kind(self, library_with_tagged_photo, tmp_path):
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "arkiv-out"
        export_arkiv(out)
        rec = next(r for r in _read_records_dir(out) if r["kind"] == "photo")
        assert rec["kind"] == "photo"

    def test_jsonl_record_uri(
        self, library_with_tagged_photo, tmp_path, db_session
    ):
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "arkiv-out"
        export_arkiv(out)
        rec = next(r for r in _read_records_dir(out) if r["kind"] == "photo")
        photo = db_session.query(Photo).first()
        assert rec["uri"] == f"photo-memex://photo/{photo.id}"


class TestArkivMarginalia:
    """Bundle must include active marginalia alongside photos."""

    def test_marginalia_records_included(
        self, populated_library, db_session, tmp_path
    ):
        from ptk.exports.arkiv import export_arkiv

        photo = db_session.query(Photo).first()
        note = Marginalia(
            photo_id=photo.id,
            body="follow up on this",
            created_at=datetime_utcnow(),
        )
        db_session.add(note)
        db_session.commit()

        out = tmp_path / "arkiv-out"
        export_arkiv(out)
        records = _read_records_dir(out)
        marginalia_records = [r for r in records if r["kind"] == "marginalia"]
        assert len(marginalia_records) == 1
        m = marginalia_records[0]
        assert m["uri"].startswith("photo-memex://marginalia/")
        assert m["metadata"]["body"] == "follow up on this"
        assert m["metadata"]["photo_uri"] == f"photo-memex://photo/{photo.id}"

    def test_archived_marginalia_excluded(
        self, populated_library, db_session, tmp_path
    ):
        from ptk.exports.arkiv import export_arkiv

        photo = db_session.query(Photo).first()
        note = Marginalia(
            photo_id=photo.id,
            body="to be archived",
            created_at=datetime_utcnow(),
        )
        db_session.add(note)
        db_session.flush()
        note.archived_at = datetime_utcnow()
        db_session.commit()

        out = tmp_path / "arkiv-out"
        export_arkiv(out)
        records = _read_records_dir(out)
        assert all(r.get("kind") != "marginalia" for r in records)

    def test_orphan_marginalia_roundtrip_shape(
        self, populated_library, db_session, tmp_path
    ):
        """A marginalia with photo_id=None emits photo_uri=null."""
        from ptk.exports.arkiv import export_arkiv

        note = Marginalia(
            photo_id=None,
            body="orphan note",
            created_at=datetime_utcnow(),
        )
        db_session.add(note)
        db_session.commit()

        out = tmp_path / "arkiv-out"
        export_arkiv(out)
        records = _read_records_dir(out)
        m = next(r for r in records if r["kind"] == "marginalia")
        assert m["metadata"]["photo_uri"] is None


class TestArkivBundles:
    """Bundle-format support (directory / .zip / .tar.gz)."""

    def test_detect_compression(self):
        from ptk.exports.arkiv import _detect_compression

        assert _detect_compression("out") == "dir"
        assert _detect_compression("out.zip") == "zip"
        assert _detect_compression("out.ZIP") == "zip"
        assert _detect_compression("out.tar.gz") == "tar.gz"
        assert _detect_compression("out.TAR.GZ") == "tar.gz"
        assert _detect_compression("out.tgz") == "tar.gz"

    def test_zip_bundle(self, library_with_tagged_photo, tmp_path):
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "bundle.zip"
        count = export_arkiv(out)
        assert out.is_file()
        with zipfile.ZipFile(out) as zf:
            names = set(zf.namelist())
        assert {"records.jsonl", "schema.yaml", "README.md"}.issubset(names)
        records = _read_records_zip(out)
        photo_records = [r for r in records if r["kind"] == "photo"]
        assert len(photo_records) == count

    def test_tar_gz_bundle(self, library_with_tagged_photo, tmp_path):
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "bundle.tar.gz"
        export_arkiv(out)
        with tarfile.open(out, "r:gz") as tf:
            names = set(tf.getnames())
        assert {"records.jsonl", "schema.yaml", "README.md"}.issubset(names)
        records = _read_records_tar_gz(out)
        assert any(r["kind"] == "photo" for r in records)

    def test_tgz_extension(self, library_with_tagged_photo, tmp_path):
        from ptk.exports.arkiv import export_arkiv

        out = tmp_path / "bundle.tgz"
        export_arkiv(out)
        with tarfile.open(out, "r:gz") as tf:
            assert "records.jsonl" in tf.getnames()

    def test_bundle_records_identical_across_formats(
        self, library_with_tagged_photo, tmp_path
    ):
        from ptk.exports.arkiv import export_arkiv

        dir_out = tmp_path / "dir"
        zip_out = tmp_path / "bundle.zip"
        tar_out = tmp_path / "bundle.tar.gz"
        export_arkiv(dir_out)
        export_arkiv(zip_out)
        export_arkiv(tar_out)

        dir_records = _read_records_dir(dir_out)
        zip_records = _read_records_zip(zip_out)
        tar_records = _read_records_tar_gz(tar_out)
        # Records in bundle formats are byte-identical (README differs
        # only in its datetime, but records + schema match).
        assert dir_records == zip_records == tar_records


# Small helper — Marginalia.created_at requires an aware datetime; the
# ORM column is ``DateTime(timezone=True)``.
def datetime_utcnow():
    from datetime import UTC, datetime
    return datetime.now(UTC)
