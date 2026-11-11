"""SQLite connection helper and schema initialization.

The persistence layer owns the SQLite file.  `get_connection` returns a
connection with ``row_factory`` enabled so rows can be accessed by column
name, and `init_db` creates the application tables (idempotently).
"""

from __future__ import annotations

import sqlite3

from .migrations import ensure_schema_version

__all__ = ["get_connection", "init_db"]

SETTINGS_KEY_DOCKHAND_BASE_URL = "dockhand_base_url"
SETTINGS_KEY_DOCKHAND_API_TOKEN = "dockhand_api_token"
SETTINGS_KEY_DISCORD_BOT_TOKEN = "discord_bot_token"
SETTINGS_KEY_DISCORD_GUILD_ID = "discord_guild_id"


def get_connection(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection to *db_path* with row factory enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create the `app_settings` and `channel_mappings` tables if missing."""
    with conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS channel_mappings (
                container_name TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (container_name, channel_id)
            );
            """
        )
    ensure_schema_version(conn)
