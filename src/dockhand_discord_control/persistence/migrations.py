"""Database schema version tracking.

A single `schema_version` row records the current schema version so future
migrations can detect out-of-date databases.
"""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1

__all__ = ["SCHEMA_VERSION", "ensure_schema_version", "get_schema_version"]


def ensure_schema_version(conn: sqlite3.Connection) -> None:
    """Create the `schema_version` table and seed it when absent."""
    with conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
        )
        if conn.execute("SELECT 1 FROM schema_version LIMIT 1").fetchone() is None:
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the current schema version, or 0 if the table is empty."""
    row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    return int(row["version"]) if row is not None else 0
