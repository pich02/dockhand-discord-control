"""Tests for the SQLite connection helper and schema initialization."""

from __future__ import annotations

from dockhand_discord_control.persistence.database import get_connection, init_db


def test_init_db_creates_app_settings_and_channel_mappings() -> None:
    conn = get_connection(":memory:")
    try:
        init_db(conn)
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "app_settings" in tables
        assert "channel_mappings" in tables
    finally:
        conn.close()


def test_init_db_is_idempotent() -> None:
    conn = get_connection(":memory:")
    try:
        init_db(conn)
        init_db(conn)
        row = conn.execute("SELECT COUNT(*) AS n FROM app_settings").fetchone()
        assert row["n"] == 0
    finally:
        conn.close()


def test_init_db_records_schema_version() -> None:
    conn = get_connection(":memory:")
    try:
        init_db(conn)
        from dockhand_discord_control.persistence.migrations import SCHEMA_VERSION

        row = conn.execute("SELECT version FROM schema_version").fetchone()
        assert row is not None and row["version"] == SCHEMA_VERSION
    finally:
        conn.close()


def test_get_connection_enables_row_factory() -> None:
    conn = get_connection(":memory:")
    try:
        init_db(conn)
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?)", ("key", "value")
        )
        conn.commit()
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", ("key",)
        ).fetchone()
        assert row["value"] == "value"
        assert row[0] == "value"
    finally:
        conn.close()
