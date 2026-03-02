"""Tests for ptk MCP server logic."""

import pytest

from ptk.core.config import get_config
from ptk.mcp.server import PtkServer


@pytest.fixture
def server(populated_library):
    """Create a PtkServer against the test library's database."""
    db_path = get_config().database_path
    srv = PtkServer(str(db_path))
    yield srv
    srv.close()


# ── get_schema ──────────────────────────────────────────────────────────────


class TestGetSchema:
    def test_returns_create_table_statements(self, server):
        schema = server.get_schema()
        assert "CREATE TABLE" in schema

    def test_includes_photos_table(self, server):
        schema = server.get_schema()
        assert "photos" in schema

    def test_includes_tags_table(self, server):
        schema = server.get_schema()
        assert "tags" in schema

    def test_includes_albums_table(self, server):
        schema = server.get_schema()
        assert "albums" in schema


# ── get_stats ───────────────────────────────────────────────────────────────


class TestGetStats:
    def test_returns_photo_count(self, server):
        stats = server.get_stats()
        assert stats["photo_count"] >= 1

    def test_returns_tag_count(self, server):
        stats = server.get_stats()
        assert "tag_count" in stats
        assert isinstance(stats["tag_count"], int)

    def test_returns_album_count(self, server):
        stats = server.get_stats()
        assert "album_count" in stats
        assert isinstance(stats["album_count"], int)

    def test_returns_total_size_bytes(self, server):
        stats = server.get_stats()
        assert "total_size_bytes" in stats
        assert stats["total_size_bytes"] > 0

    def test_returns_favorites(self, server):
        stats = server.get_stats()
        assert "favorites" in stats
        assert isinstance(stats["favorites"], int)

    def test_returns_date_range(self, server):
        stats = server.get_stats()
        assert "earliest_date" in stats
        assert "latest_date" in stats


# ── run_sql ─────────────────────────────────────────────────────────────────


class TestRunSql:
    def test_select_returns_list_of_dicts(self, server):
        rows = server.run_sql("SELECT id, filename FROM photos")
        assert isinstance(rows, list)
        assert len(rows) >= 1
        assert isinstance(rows[0], dict)
        assert "id" in rows[0]
        assert "filename" in rows[0]

    def test_select_column_names_as_keys(self, server):
        rows = server.run_sql("SELECT id, file_size FROM photos LIMIT 1")
        row = rows[0]
        assert set(row.keys()) >= {"id", "file_size"}

    def test_empty_result(self, server):
        rows = server.run_sql("SELECT id FROM photos WHERE id = 'nonexistent'")
        assert rows == []

    def test_aggregate_query(self, server):
        rows = server.run_sql("SELECT count(*) AS cnt FROM photos")
        assert len(rows) == 1
        assert rows[0]["cnt"] >= 1

    @pytest.mark.parametrize(
        "statement",
        [
            "DELETE FROM photos",
            "DROP TABLE photos",
            "INSERT INTO photos (id) VALUES ('x')",
            "UPDATE photos SET filename='x'",
        ],
    )
    def test_rejects_non_select(self, server, statement):
        with pytest.raises(ValueError, match="Only SELECT"):
            server.run_sql(statement)

    def test_rejects_non_select_with_leading_whitespace(self, server):
        with pytest.raises(ValueError, match="Only SELECT"):
            server.run_sql("   DELETE FROM photos")

    def test_rejects_non_select_with_leading_comment(self, server):
        with pytest.raises(ValueError, match="Only SELECT"):
            server.run_sql("/* comment */ DELETE FROM photos")
