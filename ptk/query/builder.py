"""Build SQL queries from flag-based filters.

This provides a simple, flag-based interface for common queries.
For complex queries, use raw SQL.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class QueryBuilder:
    """Build SQL queries from filter flags.

    Example:
        builder = QueryBuilder()
        builder.favorite()
        builder.tag("beach")
        builder.tag("sunset")
        sql, params = builder.build()
    """
    # Filter state
    _favorite: Optional[bool] = None
    _uncaptioned: bool = False
    _tags: list[str] = field(default_factory=list)
    _albums: list[str] = field(default_factory=list)
    _limit: Optional[int] = None
    _offset: Optional[int] = None

    # SQL building state
    _params: dict[str, Any] = field(default_factory=dict)
    _param_count: int = 0

    def favorite(self, value: bool = True) -> "QueryBuilder":
        """Filter by favorite status."""
        self._favorite = value
        return self

    def uncaptioned(self, value: bool = True) -> "QueryBuilder":
        """Filter to photos without captions."""
        self._uncaptioned = value
        return self

    def tag(self, name: str) -> "QueryBuilder":
        """Filter by tag (multiple calls = AND)."""
        self._tags.append(name)
        return self

    def album(self, name: str) -> "QueryBuilder":
        """Filter by album."""
        self._albums.append(name)
        return self

    def limit(self, n: int) -> "QueryBuilder":
        """Limit results."""
        self._limit = n
        return self

    def offset(self, n: int) -> "QueryBuilder":
        """Offset results."""
        self._offset = n
        return self

    def build(self) -> tuple[str, dict[str, Any]]:
        """Build the SQL query.

        Returns:
            Tuple of (sql, params)
        """
        self._params = {}
        self._param_count = 0

        # Start with base query
        sql = "SELECT DISTINCT p.* FROM photos p"
        joins = []
        where = []

        # Favorite filter
        if self._favorite is not None:
            param = self._add_param(self._favorite)
            where.append(f"p.is_favorite = :{param}")

        # Uncaptioned filter
        if self._uncaptioned:
            where.append("(p.caption IS NULL OR p.caption = '')")

        # Tag filters (AND)
        for i, tag in enumerate(self._tags):
            alias = f"pt{i}"
            alias_t = f"t{i}"
            joins.append(
                f"JOIN photo_tags {alias} ON p.id = {alias}.photo_id "
                f"JOIN tags {alias_t} ON {alias}.tag_id = {alias_t}.id"
            )
            param = self._add_param(tag)
            where.append(f"{alias_t}.name = :{param}")

        # Album filters
        for i, album in enumerate(self._albums):
            alias = f"pa{i}"
            alias_a = f"a{i}"
            joins.append(
                f"JOIN photo_albums {alias} ON p.id = {alias}.photo_id "
                f"JOIN albums {alias_a} ON {alias}.album_id = {alias_a}.id"
            )
            param = self._add_param(album)
            where.append(f"{alias_a}.name = :{param}")

        # Assemble SQL
        if joins:
            sql += "\n" + "\n".join(joins)
        if where:
            sql += "\nWHERE " + " AND ".join(where)

        sql += "\nORDER BY p.date_taken DESC NULLS LAST"

        if self._limit:
            sql += f"\nLIMIT {self._limit}"
        if self._offset:
            sql += f"\nOFFSET {self._offset}"

        return sql, self._params

    def _add_param(self, value: Any) -> str:
        """Add a parameter and return its name."""
        self._param_count += 1
        name = f"p{self._param_count}"
        self._params[name] = value
        return name
