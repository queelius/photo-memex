"""MCP server for ptk photo library.

Exposes the SQLite photo library over stdio using FastMCP.
Provides three tools: get_schema, get_stats, run_sql.
"""

import json
import re
import sqlite3
from typing import Any


class PtkServer:
    """Core server logic for the ptk MCP interface.

    Uses a direct sqlite3 connection (not SQLAlchemy) for read-only
    raw SQL access to the photo library.
    """

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row

    def get_schema(self) -> str:
        """Return CREATE TABLE statements for all tables in the database."""
        cursor = self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL "
            "ORDER BY name"
        )
        statements = [row[0] for row in cursor.fetchall()]
        return "\n\n".join(statements)

    def get_stats(self) -> dict[str, Any]:
        """Return library statistics as a dict."""
        cur = self._conn.cursor()

        photo_count = cur.execute("SELECT count(*) FROM photos").fetchone()[0]
        tag_count = cur.execute("SELECT count(*) FROM tags").fetchone()[0]
        album_count = cur.execute("SELECT count(*) FROM albums").fetchone()[0]
        favorites = cur.execute(
            "SELECT count(*) FROM photos WHERE is_favorite = 1"
        ).fetchone()[0]
        total_size = cur.execute(
            "SELECT coalesce(sum(file_size), 0) FROM photos"
        ).fetchone()[0]
        earliest = cur.execute(
            "SELECT min(date_taken) FROM photos WHERE date_taken IS NOT NULL"
        ).fetchone()[0]
        latest = cur.execute(
            "SELECT max(date_taken) FROM photos WHERE date_taken IS NOT NULL"
        ).fetchone()[0]

        return {
            "photo_count": photo_count,
            "tag_count": tag_count,
            "album_count": album_count,
            "favorites": favorites,
            "total_size_bytes": total_size,
            "earliest_date": earliest,
            "latest_date": latest,
        }

    def run_sql(self, query: str) -> list[dict[str, Any]]:
        """Execute a read-only SQL query and return results as list of dicts.

        Only SELECT statements are allowed. Raises ValueError for
        DELETE, DROP, INSERT, UPDATE, or any other non-SELECT statement.
        """
        # Strip whitespace and leading SQL comments to find the real statement
        cleaned = _strip_sql_comments(query).strip()
        if not cleaned.upper().startswith("SELECT"):
            raise ValueError("Only SELECT statements are allowed.")

        cursor = self._conn.execute(query)
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()


def _strip_sql_comments(sql: str) -> str:
    """Strip leading SQL comments (block and line) from a query string."""
    # Remove leading block comments /* ... */
    result = sql.strip()
    while result.startswith("/*"):
        end = result.find("*/")
        if end == -1:
            break
        result = result[end + 2 :].strip()
    # Remove leading line comments -- ...
    while result.startswith("--"):
        newline = result.find("\n")
        if newline == -1:
            result = ""
            break
        result = result[newline + 1 :].strip()
    return result


def run_mcp_server(db_path: str) -> None:
    """Run the ptk MCP server over stdio."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        raise ImportError(
            "MCP server requires 'mcp' package. Install with: pip install ptk[mcp]"
        )

    mcp = FastMCP("ptk")
    server = PtkServer(db_path)

    @mcp.tool()
    def get_schema() -> str:
        """Get the database schema (CREATE TABLE statements). Call this first to understand the data model before writing SQL queries."""
        return server.get_schema()

    @mcp.tool()
    def get_stats() -> str:
        """Get library statistics: photo count, tag count, album count, date range, total size, favorites."""
        return json.dumps(server.get_stats(), indent=2, default=str)

    @mcp.tool()
    def run_sql(query: str) -> str:
        """Run a read-only SQL query against the photo library. Only SELECT statements are allowed. Tables: photos, tags, albums, photo_tags, photo_albums. Use JOIN for relationships."""
        results = server.run_sql(query)
        return json.dumps(results, indent=2, default=str)

    mcp.run(transport="stdio")
