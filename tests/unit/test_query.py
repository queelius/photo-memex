"""Tests for the query module - flag-based query building."""

import json
from datetime import datetime, timezone

from photo_memex.query.builder import QueryBuilder
from photo_memex.query.executor import OutputFormat, QueryResult
from photo_memex.db.models import Photo


class TestQueryBuilder:
    """Tests for QueryBuilder."""

    def test_empty_query(self):
        """Empty query should return all photos."""
        builder = QueryBuilder()
        sql, params = builder.build()

        assert "SELECT DISTINCT p.* FROM photos p" in sql
        assert "ORDER BY p.date_taken DESC NULLS LAST" in sql
        assert params == {}

    def test_favorite_filter(self):
        """Filter by favorite status."""
        builder = QueryBuilder()
        builder.favorite()
        sql, params = builder.build()

        assert "p.is_favorite = :p1" in sql
        assert params["p1"] is True

    def test_favorite_false(self):
        """Filter for non-favorites."""
        builder = QueryBuilder()
        builder.favorite(False)
        sql, params = builder.build()

        assert "p.is_favorite = :p1" in sql
        assert params["p1"] is False

    def test_single_tag(self):
        """Filter by single tag."""
        builder = QueryBuilder()
        builder.tag("beach")
        sql, params = builder.build()

        assert "JOIN photo_tags pt0" in sql
        assert "JOIN tags t0" in sql
        assert "t0.name = :p1" in sql
        assert params["p1"] == "beach"

    def test_multiple_tags_and(self):
        """Multiple tags are ANDed together."""
        builder = QueryBuilder()
        builder.tag("beach").tag("sunset")
        sql, params = builder.build()

        assert "JOIN photo_tags pt0" in sql
        assert "JOIN photo_tags pt1" in sql
        assert "JOIN tags t0" in sql
        assert "JOIN tags t1" in sql
        assert "t0.name = :p1" in sql
        assert "t1.name = :p2" in sql
        assert params["p1"] == "beach"
        assert params["p2"] == "sunset"

    def test_album_filter(self):
        """Filter by album."""
        builder = QueryBuilder()
        builder.album("Summer 2020")
        sql, params = builder.build()

        assert "JOIN photo_albums pa0" in sql
        assert "JOIN albums a0" in sql
        assert "a0.name = :p1" in sql
        assert params["p1"] == "Summer 2020"

    def test_limit(self):
        """Limit results."""
        builder = QueryBuilder()
        builder.limit(10)
        sql, params = builder.build()

        assert "LIMIT 10" in sql

    def test_offset(self):
        """Offset results."""
        builder = QueryBuilder()
        builder.limit(10).offset(20)
        sql, params = builder.build()

        assert "LIMIT 10" in sql
        assert "OFFSET 20" in sql

    def test_combined_filters(self):
        """Combine multiple filter types."""
        builder = QueryBuilder()
        builder.favorite().tag("beach").limit(5)
        sql, params = builder.build()

        assert "p.is_favorite = :p1" in sql
        assert "t0.name = :p2" in sql
        assert "LIMIT 5" in sql
        assert params["p1"] is True
        assert params["p2"] == "beach"

    def test_chaining_returns_self(self):
        """All filter methods return self for chaining."""
        builder = QueryBuilder()
        result = builder.favorite().tag("x").album("y").limit(10)
        assert result is builder

class TestOutputFormat:
    """Tests for OutputFormat enum."""

    def test_output_formats_exist(self):
        """Verify all expected output formats exist."""
        assert OutputFormat.TABLE.value == "table"
        assert OutputFormat.JSON.value == "json"
        assert OutputFormat.IDS.value == "ids"
        assert OutputFormat.COUNT.value == "count"


class TestQueryResult:
    """Tests for QueryResult formatting."""

    def _make_photo(self, id: str, filename: str, date_taken=None, tags=None):
        """Create a mock Photo for testing."""
        photo = Photo(
            id=id,
            original_path=f"/photos/{filename}",
            filename=filename,
            file_size=1024,
            mime_type="image/jpeg",
            date_taken=date_taken,
            date_imported=datetime.now(timezone.utc),
            is_favorite=False,
        )
        photo.tags = tags or []
        return photo

    def test_count_format(self):
        """COUNT format returns count as string."""
        photos = [self._make_photo(f"abc{i}", f"photo{i}.jpg") for i in range(5)]
        result = QueryResult(photos=photos, sql="", params={})

        assert result.format(OutputFormat.COUNT) == "5"

    def test_ids_format(self):
        """IDS format returns newline-separated IDs."""
        photos = [
            self._make_photo("abc123", "a.jpg"),
            self._make_photo("def456", "b.jpg"),
        ]
        result = QueryResult(photos=photos, sql="", params={})

        output = result.format(OutputFormat.IDS)
        assert output == "abc123\ndef456"

    def test_json_format(self):
        """JSON format returns valid JSON."""
        photo = self._make_photo(
            "abc123", "test.jpg",
            date_taken=datetime(2023, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
        )
        result = QueryResult(photos=[photo], sql="", params={})

        output = result.format(OutputFormat.JSON)
        data = json.loads(output)

        assert len(data) == 1
        assert data[0]["id"] == "abc123"
        assert data[0]["filename"] == "test.jpg"
        assert "2023-07-15" in data[0]["date_taken"]

    def test_table_format_empty(self):
        """TABLE format with no photos."""
        result = QueryResult(photos=[], sql="", params={})
        output = result.format(OutputFormat.TABLE)

        assert "No photos found." in output

    def test_table_format_with_photos(self):
        """TABLE format with photos."""
        photo = self._make_photo(
            "abc123def456",
            "vacation.jpg",
            date_taken=datetime(2023, 7, 15, tzinfo=timezone.utc)
        )
        result = QueryResult(photos=[photo], sql="", params={})

        output = result.format(OutputFormat.TABLE)

        assert "abc123def456"[:12] in output
        assert "vacation.jpg" in output
        assert "2023-07-15" in output
        assert "1 photo(s)" in output

    def test_count_property(self):
        """Count property returns correct value."""
        photos = [self._make_photo(f"id{i}", f"p{i}.jpg") for i in range(3)]
        result = QueryResult(photos=photos, sql="SELECT *", params={"a": 1})

        assert result.count == 3
