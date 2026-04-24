"""Tests for the arkiv importer (photo_memex.importers.arkiv).

Covers the full workspace C5b contract: five bundle shapes auto-detected,
round-trip through the exporter, idempotent re-imports, orphan
marginalia, and tag/album merge-on-duplicate.
"""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from photo_memex.db.models import Album, Marginalia, Photo, Tag


@pytest.fixture
def library_with_photo_and_marginalia(populated_library, db_session):
    """Populated library enriched with tags, albums, and a marginalia note."""
    photo = db_session.query(Photo).first()
    photo.caption = "A red test image"
    photo.is_favorite = True

    now = datetime.now(UTC)
    tag = Tag(name="holiday")
    album = Album(name="Summer 2026", created_at=now, updated_at=now)
    db_session.add_all([tag, album])
    photo.tags.append(tag)
    photo.albums.append(album)

    note = Marginalia(
        photo_id=photo.id,
        body="follow up on this",
        created_at=datetime.now(UTC),
    )
    db_session.add(note)
    db_session.commit()

    return populated_library


def _export_bundle(out_path: Path) -> int:
    from photo_memex.exports.arkiv import export_arkiv

    return export_arkiv(out_path)


# ---------------------------------------------------------------------------
# Small unit helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_parse_timestamp_iso(self):
        from photo_memex.importers.arkiv import _parse_timestamp

        ts = _parse_timestamp("2026-04-24T12:34:56+00:00")
        assert ts is not None
        assert ts.hour == 12

    def test_parse_timestamp_none(self):
        from photo_memex.importers.arkiv import _parse_timestamp

        assert _parse_timestamp(None) is None
        assert _parse_timestamp("") is None

    def test_sha256_from_photo_uri(self):
        from photo_memex.importers.arkiv import _sha256_from_photo_uri

        sha = "a" * 64
        assert _sha256_from_photo_uri(f"photo-memex://photo/{sha}") == sha

    def test_sha256_from_photo_uri_wrong_scheme(self):
        from photo_memex.importers.arkiv import _sha256_from_photo_uri

        assert _sha256_from_photo_uri("file:///tmp/foo") is None

    def test_is_record_accepts_photo(self):
        from photo_memex.importers.arkiv import _is_photo_memex_record

        assert _is_photo_memex_record(
            {
                "kind": "photo",
                "uri": "photo-memex://photo/" + "a" * 64,
                "metadata": {"sha256": "a" * 64},
            }
        )

    def test_is_record_rejects_unknown_kind(self):
        from photo_memex.importers.arkiv import _is_photo_memex_record

        assert not _is_photo_memex_record({"kind": "email", "uri": "x"})


# ---------------------------------------------------------------------------
# detect(): every bundle shape
# ---------------------------------------------------------------------------


class TestDetect:
    def test_detect_directory(self, library_with_photo_and_marginalia, tmp_path):
        from photo_memex.importers.arkiv import detect

        out = tmp_path / "bundle"
        _export_bundle(out)
        assert detect(out) is True

    def test_detect_zip(self, library_with_photo_and_marginalia, tmp_path):
        from photo_memex.importers.arkiv import detect

        out = tmp_path / "bundle.zip"
        _export_bundle(out)
        assert detect(out) is True

    def test_detect_tar_gz(self, library_with_photo_and_marginalia, tmp_path):
        from photo_memex.importers.arkiv import detect

        out = tmp_path / "bundle.tar.gz"
        _export_bundle(out)
        assert detect(out) is True

    def test_detect_tgz(self, library_with_photo_and_marginalia, tmp_path):
        from photo_memex.importers.arkiv import detect

        out = tmp_path / "bundle.tgz"
        _export_bundle(out)
        assert detect(out) is True

    def test_detect_bare_jsonl(self, library_with_photo_and_marginalia, tmp_path):
        from photo_memex.importers.arkiv import detect

        dir_out = tmp_path / "d"
        _export_bundle(dir_out)
        bare = tmp_path / "records.jsonl"
        bare.write_bytes((dir_out / "records.jsonl").read_bytes())
        assert detect(bare) is True

    def test_detect_bare_jsonl_gz(self, library_with_photo_and_marginalia, tmp_path):
        from photo_memex.importers.arkiv import detect

        dir_out = tmp_path / "d"
        _export_bundle(dir_out)
        bare_gz = tmp_path / "records.jsonl.gz"
        with gzip.open(bare_gz, "wb") as f:
            f.write((dir_out / "records.jsonl").read_bytes())
        assert detect(bare_gz) is True

    def test_detect_rejects_missing_path(self, tmp_path):
        from photo_memex.importers.arkiv import detect

        assert detect(tmp_path / "does-not-exist") is False

    def test_detect_rejects_foreign_arkiv(self, tmp_path):
        from photo_memex.importers.arkiv import detect

        foreign = tmp_path / "foreign.jsonl"
        foreign.write_text(
            json.dumps(
                {"kind": "book", "uri": "book-memex://book/abc"}
            )
            + "\n"
        )
        assert detect(foreign) is False


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


class TestImportRoundTrip:
    """Export from one archive, wipe, import fresh — state must reconstruct."""

    def test_import_directory_reconstructs_photo(
        self, library_with_photo_and_marginalia, db_session, tmp_path
    ):
        from photo_memex.importers.arkiv import import_arkiv

        out = tmp_path / "bundle"
        _export_bundle(out)

        # Record identifying info inside the session.
        original_sha = db_session.query(Photo).first().id
        original_note_body = db_session.query(Marginalia).first().body

        # Clear the local archive and re-import.
        for m in db_session.query(Marginalia).all():
            db_session.delete(m)
        for p in db_session.query(Photo).all():
            db_session.delete(p)
        db_session.commit()

        stats = import_arkiv(out)
        assert stats["photos_added"] == 1
        assert stats["photos_seen"] == 1
        assert stats["marginalia_added"] == 1

        restored = db_session.query(Photo).filter(Photo.id == original_sha).one_or_none()
        assert restored is not None
        assert restored.caption == "A red test image"
        assert restored.is_favorite is True
        assert "holiday" in {t.name for t in restored.tags}
        assert "Summer 2026" in {a.name for a in restored.albums}

        notes = db_session.query(Marginalia).all()
        assert len(notes) == 1
        assert notes[0].body == original_note_body
        assert notes[0].photo_id == original_sha

    def test_import_zip_bundle(
        self, library_with_photo_and_marginalia, db_session, tmp_path
    ):
        from photo_memex.importers.arkiv import import_arkiv

        out = tmp_path / "bundle.zip"
        _export_bundle(out)

        # Clear marginalia only so we can observe the import adding it.
        for m in db_session.query(Marginalia).all():
            db_session.delete(m)
        db_session.commit()

        stats = import_arkiv(out)
        # Photo is already present (skip), marginalia is new.
        assert stats["photos_skipped_existing"] == 1
        assert stats["marginalia_added"] == 1

    def test_import_tar_gz_bundle(
        self, library_with_photo_and_marginalia, db_session, tmp_path
    ):
        from photo_memex.importers.arkiv import import_arkiv

        out = tmp_path / "bundle.tar.gz"
        _export_bundle(out)
        stats = import_arkiv(out)
        # Original photo + marginalia already there, so everything is skipped.
        assert stats["photos_skipped_existing"] == 1
        assert stats["marginalia_skipped_existing"] == 1

    def test_import_bare_jsonl_gz(
        self, library_with_photo_and_marginalia, db_session, tmp_path
    ):
        """The SPA round-trip shape: bare .jsonl.gz."""
        from photo_memex.importers.arkiv import import_arkiv

        dir_out = tmp_path / "d"
        _export_bundle(dir_out)
        bare_gz = tmp_path / "records.jsonl.gz"
        with gzip.open(bare_gz, "wb") as f:
            f.write((dir_out / "records.jsonl").read_bytes())

        stats = import_arkiv(bare_gz)
        assert stats["photos_seen"] == 1

    def test_re_import_is_idempotent(
        self, library_with_photo_and_marginalia, db_session, tmp_path
    ):
        from photo_memex.importers.arkiv import import_arkiv

        out = tmp_path / "bundle"
        _export_bundle(out)

        import_arkiv(out)  # first pass
        db_session.expire_all()
        photo_count_a = db_session.query(Photo).count()
        margin_count_a = db_session.query(Marginalia).count()

        second = import_arkiv(out)
        assert second["photos_added"] == 0
        assert second["photos_skipped_existing"] == 1
        assert second["marginalia_added"] == 0
        assert second["marginalia_skipped_existing"] == 1

        db_session.expire_all()
        assert db_session.query(Photo).count() == photo_count_a
        assert db_session.query(Marginalia).count() == margin_count_a

    def test_merge_flag_accepted(
        self, library_with_photo_and_marginalia, tmp_path
    ):
        from photo_memex.importers.arkiv import import_arkiv

        out = tmp_path / "bundle"
        _export_bundle(out)
        stats = import_arkiv(out, merge=True)
        # --merge is a no-op today — same outcome.
        assert stats["photos_seen"] == 1

    def test_orphan_marginalia_created_with_null_photo_id(
        self, populated_library, db_session, tmp_path
    ):
        """A marginalia record referencing a missing photo lands as an orphan."""
        from photo_memex.importers.arkiv import import_arkiv

        bundle = tmp_path / "orphan.jsonl"
        orphan = {
            "kind": "marginalia",
            "uri": "photo-memex://marginalia/1",
            "mimetype": "text/plain",
            "content": "orphan note body",
            "metadata": {
                "id": 1,
                "photo_uri": "photo-memex://photo/" + "f" * 64,
                "body": "orphan note body",
                "created_at": "2026-04-24T12:00:00+00:00",
                "updated_at": None,
            },
        }
        bundle.write_text(json.dumps(orphan) + "\n")

        stats = import_arkiv(bundle)
        assert stats["marginalia_orphaned"] == 1
        assert stats["marginalia_added"] == 1

        rows = db_session.query(Marginalia).all()
        note = next(n for n in rows if n.body == "orphan note body")
        assert note.photo_id is None


class TestMergeSemantics:
    """Tag and album names in the bundle are merged additively into an existing row."""

    def test_reimport_adds_new_tag_to_existing_photo(
        self, library_with_photo_and_marginalia, db_session, tmp_path
    ):
        from photo_memex.importers.arkiv import import_arkiv

        out = tmp_path / "bundle"
        _export_bundle(out)

        # The original photo has "holiday" tag. Add a new tag "portfolio"
        # only in the bundle-derived copy — we simulate this by reading
        # records.jsonl, mutating it, and re-writing.
        records_file = out / "records.jsonl"
        lines = records_file.read_text().strip().split("\n")
        edited = []
        for ln in lines:
            rec = json.loads(ln)
            if rec.get("kind") == "photo":
                rec["metadata"].setdefault("tags", []).append("portfolio")
            edited.append(json.dumps(rec))
        records_file.write_text("\n".join(edited) + "\n")

        import_arkiv(out)

        db_session.expire_all()
        photo = db_session.query(Photo).first()
        tag_names = {t.name for t in photo.tags}
        assert "holiday" in tag_names, "original tag preserved"
        assert "portfolio" in tag_names, "bundle-only tag merged in"
