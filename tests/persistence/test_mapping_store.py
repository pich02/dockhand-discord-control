"""Tests for SqliteChannelMappingRepository."""

from __future__ import annotations

from dockhand_discord_control.domain.models import ChannelMapping
from dockhand_discord_control.persistence import SqliteChannelMappingRepository

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
