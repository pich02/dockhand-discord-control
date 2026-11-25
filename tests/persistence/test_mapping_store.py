"""Tests for SqliteChannelMappingRepository."""

from __future__ import annotations

import sqlite3

import pytest

from dockhand_discord_control.domain.models import ChannelMapping
from dockhand_discord_control.persistence import SqliteChannelMappingRepository
from dockhand_discord_control.persistence.migrations import get_schema_version

WEB = ChannelMapping(container_name="web", channel_id="ch-web-1", enabled=True)
WEB_DISABLED = ChannelMapping(
    container_name="web", channel_id="ch-web-2", enabled=False
)
DB = ChannelMapping(container_name="db", channel_id="ch-db-1", enabled=True)


def test_get_mapping_returns_none_when_empty() -> None:
    repo = SqliteChannelMappingRepository(":memory:")
    try:
        assert repo.get_mapping("ch-anything") is None
    finally:
        repo.close()


def test_mappings_for_container_returns_empty_list_when_empty() -> None:
    repo = SqliteChannelMappingRepository(":memory:")
    try:
        assert repo.mappings_for_container("web") == []
    finally:
        repo.close()


def test_add_and_get_mapping_defaults_enabled() -> None:
    repo = SqliteChannelMappingRepository(":memory:")
    try:
        repo.add_mapping(WEB)
        assert repo.get_mapping("ch-web-1") == WEB
    finally:
        repo.close()


def test_enabled_flag_is_stored_and_returned() -> None:
    repo = SqliteChannelMappingRepository(":memory:")
    try:
        repo.add_mapping(WEB_DISABLED)
        assert repo.get_mapping("ch-web-2") == WEB_DISABLED
    finally:
        repo.close()


def test_set_enabled_updates_in_place() -> None:
    repo = SqliteChannelMappingRepository(":memory:")
    try:
        repo.add_mapping(WEB)
        repo.set_enabled("ch-web-1", False)
        assert repo.get_mapping("ch-web-1") == ChannelMapping(
            container_name="web", channel_id="ch-web-1", enabled=False
        )
        repo.set_enabled("ch-web-1", True)
        assert repo.get_mapping("ch-web-1") == WEB
    finally:
        repo.close()


def test_mappings_for_container_filters_by_container() -> None:
    repo = SqliteChannelMappingRepository(":memory:")
    try:
        repo.add_mapping(WEB)
        repo.add_mapping(WEB_DISABLED)
        repo.add_mapping(DB)
        assert repo.mappings_for_container("web") == [WEB, WEB_DISABLED]
        assert repo.mappings_for_container("db") == [DB]
        assert repo.mappings_for_container("missing") == []
    finally:
        repo.close()


def test_remove_mapping_deletes_row() -> None:
    repo = SqliteChannelMappingRepository(":memory:")
    try:
        repo.add_mapping(WEB)
        repo.remove_mapping("ch-web-1")
        assert repo.get_mapping("ch-web-1") is None
        assert repo.mappings_for_container("web") == []
    finally:
        repo.close()


def test_mappings_persist_across_instances(tmp_path) -> None:
    db_path = str(tmp_path / "app.sqlite")
    repo1 = SqliteChannelMappingRepository(db_path)
    try:
        repo1.add_mapping(WEB)
    finally:
        repo1.close()
    repo2 = SqliteChannelMappingRepository(db_path)
    try:
        assert repo2.get_mapping("ch-web-1") == WEB
    finally:
        repo2.close()


def test_add_mapping_same_channel_same_container_is_idempotent() -> None:
    repo = SqliteChannelMappingRepository(":memory:")
    try:
        repo.add_mapping(WEB)
        repo.add_mapping(
            ChannelMapping(container_name="web", channel_id="ch-web-1", enabled=False)
        )
        assert repo.get_mapping("ch-web-1") == ChannelMapping(
            container_name="web", channel_id="ch-web-1", enabled=False
        )
        assert repo.mappings_for_container("web") == [
            ChannelMapping(container_name="web", channel_id="ch-web-1", enabled=False)
        ]
    finally:
        repo.close()


def test_add_mapping_rejects_conflicting_channel_assignment() -> None:
    repo = SqliteChannelMappingRepository(":memory:")
    try:
        repo.add_mapping(WEB)
        with pytest.raises(ValueError, match="already mapped"):
            repo.add_mapping(
                ChannelMapping(container_name="db", channel_id="ch-web-1", enabled=True)
            )
        assert repo.get_mapping("ch-web-1") == WEB
        assert repo.mappings_for_container("db") == []
    finally:
        repo.close()


def test_schema_enforces_single_mapping_per_channel() -> None:
    repo = SqliteChannelMappingRepository(":memory:")
    try:
        repo.add_mapping(WEB)
        with pytest.raises(sqlite3.IntegrityError):
            repo._conn.execute(
                """
                INSERT INTO channel_mappings (container_name, channel_id, enabled)
                VALUES (?, ?, ?)
                """,
                ("db", "ch-web-1", 1),
            )
    finally:
        repo.close()


def test_set_enabled_only_affects_target_channel() -> None:
    repo = SqliteChannelMappingRepository(":memory:")
    try:
        repo.add_mapping(WEB)
        repo.add_mapping(DB)
        repo.set_enabled("ch-web-1", False)
        assert repo.get_mapping("ch-web-1") == ChannelMapping(
            container_name="web", channel_id="ch-web-1", enabled=False
        )
        assert repo.get_mapping("ch-db-1") == DB
    finally:
        repo.close()


def test_remove_mapping_only_affects_target_channel() -> None:
    repo = SqliteChannelMappingRepository(":memory:")
    try:
        repo.add_mapping(WEB)
        repo.add_mapping(DB)
        repo.remove_mapping("ch-web-1")
        assert repo.get_mapping("ch-web-1") is None
        assert repo.get_mapping("ch-db-1") == DB
    finally:
        repo.close()


def _create_v1_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.executescript(
            """
            CREATE TABLE app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE channel_mappings (
                container_name TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (container_name, channel_id)
            );
            CREATE TABLE schema_version (version INTEGER NOT NULL);
            INSERT INTO schema_version (version) VALUES (1);
            """
        )
    conn.close()


def test_migration_v1_to_v2_enforces_channel_uniqueness(tmp_path) -> None:
    db_path = str(tmp_path / "app.sqlite")
    _create_v1_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.executemany(
            """
            INSERT INTO channel_mappings (container_name, channel_id, enabled)
            VALUES (?, ?, ?)
            """,
            [
                ("web", "ch-1", 1),
                ("db", "ch-2", 0),
            ],
        )
    conn.close()

    repo = SqliteChannelMappingRepository(db_path)
    try:
        assert get_schema_version(repo._conn) == 2
        assert repo.get_mapping("ch-1") == ChannelMapping(
            container_name="web", channel_id="ch-1", enabled=True
        )
        assert repo.get_mapping("ch-2") == ChannelMapping(
            container_name="db", channel_id="ch-2", enabled=False
        )
        with pytest.raises(ValueError, match="already mapped"):
            repo.add_mapping(
                ChannelMapping(container_name="db", channel_id="ch-1", enabled=True)
            )
    finally:
        repo.close()


def test_migration_v1_to_v2_resolves_conflicting_channel_rows(tmp_path) -> None:
    db_path = str(tmp_path / "app.sqlite")
    _create_v1_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.executemany(
            """
            INSERT INTO channel_mappings (container_name, channel_id, enabled)
            VALUES (?, ?, ?)
            """,
            [
                ("web", "ch-1", 0),
                ("api", "ch-1", 1),
                ("db", "ch-2", 0),
                ("cache", "ch-2", 0),
            ],
        )
    conn.close()

    repo = SqliteChannelMappingRepository(db_path)
    try:
        assert get_schema_version(repo._conn) == 2
        # Conflict resolution: keep enabled row when present.
        assert repo.get_mapping("ch-1") == ChannelMapping(
            container_name="api", channel_id="ch-1", enabled=True
        )
        # Conflict resolution: when none enabled, keep deterministic first row.
        assert repo.get_mapping("ch-2") == ChannelMapping(
            container_name="db", channel_id="ch-2", enabled=False
        )
    finally:
        repo.close()
