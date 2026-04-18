"""Query executor - run queries and format results."""

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, List

from sqlalchemy import text
from sqlalchemy.orm import Session

from ptk.db.models import Photo
from ptk.query.builder import QueryBuilder


class OutputFormat(Enum):
    TABLE = "table"
    JSON = "json"
    IDS = "ids"
    COUNT = "count"
    PATHS = "paths"


@dataclass
class QueryResult:
    """Result of a query execution."""
    photos: List[Photo]
    sql: str
    params: dict[str, Any]

    @property
    def count(self) -> int:
        return len(self.photos)

    def format(self, fmt: OutputFormat) -> str:
        """Format the result for output."""
        if fmt == OutputFormat.COUNT:
            return str(self.count)
        elif fmt == OutputFormat.IDS:
            return "\n".join(p.id for p in self.photos)
        elif fmt == OutputFormat.PATHS:
            return self._format_paths()
        elif fmt == OutputFormat.JSON:
            return self._format_json()
        else:
            return self._format_table()

    def _format_paths(self) -> str:
        """Output as id|path pairs for batch processing."""
        lines = []
        for p in self.photos:
            # Use short ID (first 8 chars) for convenience
            lines.append(f"{p.id[:8]}|{p.original_path}")
        return "\n".join(lines)

    def _format_json(self) -> str:
        """Output as JSON."""
        data = []
        for p in self.photos:
            data.append({
                "id": p.id,
                "filename": p.filename,
                "path": p.original_path,
                "date_taken": p.date_taken.isoformat() if p.date_taken else None,
                "is_favorite": p.is_favorite,
                "caption": p.caption,
                "tags": [t.name for t in p.tags] if p.tags else [],
            })
        return json.dumps(data, indent=2)

    def _format_table(self) -> str:
        """Format as a simple text table."""
        if not self.photos:
            return "No photos found."

        lines = []
        lines.append(f"{'ID':<14} {'Filename':<30} {'Date':<12} {'Tags'}")
        lines.append("-" * 80)
        for p in self.photos:
            id_short = p.id[:12]
            date = p.date_taken.strftime("%Y-%m-%d") if p.date_taken else "-"
            tags = ", ".join(t.name for t in (p.tags or [])[:3])
            if len(p.tags or []) > 3:
                tags += "..."
            lines.append(f"{id_short:<14} {p.filename:<30} {date:<12} {tags}")

        lines.append(f"\n{self.count} photo(s)")
        return "\n".join(lines)


def execute_query(
    session: Session,
    builder: QueryBuilder,
) -> QueryResult:
    """Execute a query from a QueryBuilder.

    Args:
        session: SQLAlchemy session
        builder: QueryBuilder with filters set

    Returns:
        QueryResult with photos and metadata
    """
    sql, params = builder.build()

    # Execute
    result = session.execute(text(sql), params)
    rows = result.fetchall()

    # Get Photo objects with relationships
    photo_ids = [row[0] for row in rows]
    if not photo_ids:
        return QueryResult(photos=[], sql=sql, params=params)

    photos = session.query(Photo).filter(Photo.id.in_(photo_ids)).all()

    # Preserve order from SQL result
    id_to_photo = {p.id: p for p in photos}
    ordered_photos = [id_to_photo[pid] for pid in photo_ids if pid in id_to_photo]

    return QueryResult(
        photos=ordered_photos,
        sql=sql,
        params=params,
    )


def execute_sql(
    session: Session,
    sql: str,
    limit: Optional[int] = None,
) -> QueryResult:
    """Execute a raw SQL query.

    Args:
        session: SQLAlchemy session
        sql: Raw SQL query
        limit: Optional limit to apply

    Returns:
        QueryResult with photos and metadata
    """
    if limit:
        # Wrap in subquery with limit. Strip trailing ';' so the wrapped form
        # parses cleanly: SELECT * FROM (SELECT ...) LIMIT N
        sql = f"SELECT * FROM ({sql.rstrip().rstrip(';').rstrip()}) LIMIT {limit}"

    result = session.execute(text(sql))
    rows = result.fetchall()

    # Try to get Photo objects
    # Assume first column is photo ID
    photo_ids = []
    for row in rows:
        if row:
            photo_ids.append(row[0])

    if not photo_ids:
        return QueryResult(photos=[], sql=sql, params={})

    photos = session.query(Photo).filter(Photo.id.in_(photo_ids)).all()

    # Preserve order
    id_to_photo = {p.id: p for p in photos}
    ordered_photos = [id_to_photo.get(pid) for pid in photo_ids]
    ordered_photos = [p for p in ordered_photos if p is not None]

    return QueryResult(
        photos=ordered_photos,
        sql=sql,
        params={},
    )
