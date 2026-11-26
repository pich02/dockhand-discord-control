"""Database schema version tracking.

A single `schema_version` row records the current schema version so future
migrations can detect out-of-date databases.

Schema history:
- v1: initial app_settings + channel_mappings(container_name, channel_id) PK.
- v2: channel_mappings enforces one mapping per channel_id (channel_id PK).
  Migration resolves pre-existing conflicts per channel_id by keeping an
  enabled row when present, otherwise the lowest rowid (first inserted row).
"""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 2

__all__ = ["SCHEMA_VERSION", "ensure_schema_version", "get_schema_version"]


def ensure_schema_version(conn: sqlite3.Connection) -> None:
    """Create the `schema_version` table, seed it, and run pending migrations."""
    with conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
        )
        row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
            return

        version = int(row["version"])
        if version < 2:
            _migrate_v1_to_v2(conn)
            version = 2
        if version != int(row["version"]):
            conn.execute("UPDATE schema_version SET version = ?", (version,))


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Migrate channel_mappings from composite PK to channel_id PK.

    Invariant after migration: one mapping per channel_id. If legacy data
    contains conflicting rows for the same channel_id, keep the enabled row;
    when no enabled row exists, keep the row with the lowest rowid (first
    inserted) for deterministic behavior.
    """
    conn.execute("DROP TABLE IF EXISTS channel_mappings_v2")
    conn.execute(
        """
        CREATE TABLE channel_mappings_v2 (
            channel_id TEXT PRIMARY KEY,
            container_name TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        INSERT INTO channel_mappings_v2 (channel_id, container_name, enabled)
        SELECT m.channel_id, m.container_name, m.enabled
        FROM channel_mappings m
        WHERE m.rowid = (
            SELECT m2.rowid
            FROM channel_mappings m2
            WHERE m2.channel_id = m.channel_id
            ORDER BY m2.enabled DESC, m2.rowid ASC
            LIMIT 1
        )
        """
    )
    conn.execute("DROP TABLE channel_mappings")
    conn.execute("ALTER TABLE channel_mappings_v2 RENAME TO channel_mappings")


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the current schema version, or 0 if the table is empty."""
    row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    return int(row["version"]) if row is not None else 0
