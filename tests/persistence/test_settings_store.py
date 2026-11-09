"""Tests for SqliteSettingsRepository."""

from __future__ import annotations

from dockhand_discord_control.persistence import SqliteSettingsRepository


def test_empty_db_returns_defaults() -> None:
    repo = SqliteSettingsRepository(":memory:")
    try:
        assert repo.get_dockhand_settings() == ("", "")
        assert repo.get_discord_token() is None
    finally:
        repo.close()


def test_dockhand_settings_round_trip() -> None:
    repo = SqliteSettingsRepository(":memory:")
    try:
        repo.set_dockhand_settings("http://dockhand:8080", "dockhand-secret")
        assert repo.get_dockhand_settings() == (
            "http://dockhand:8080",
            "dockhand-secret",
        )
        repo.set_dockhand_settings("http://other:9000", "other-token")
        assert repo.get_dockhand_settings() == ("http://other:9000", "other-token")
    finally:
        repo.close()


def test_discord_token_round_trip() -> None:
    repo = SqliteSettingsRepository(":memory:")
    try:
        assert repo.get_discord_token() is None
        repo.set_discord_token("bot-123")
        assert repo.get_discord_token() == "bot-123"
        repo.set_discord_token(None)
        assert repo.get_discord_token() is None
    finally:
        repo.close()


def test_settings_persist_across_instances(tmp_path) -> None:
    db_path = str(tmp_path / "app.sqlite")
    repo1 = SqliteSettingsRepository(db_path)
    try:
        repo1.set_dockhand_settings("http://dockhand:8080", "token-a")
        repo1.set_discord_token("bot-token-a")
    finally:
        repo1.close()
    repo2 = SqliteSettingsRepository(db_path)
    try:
        assert repo2.get_dockhand_settings() == ("http://dockhand:8080", "token-a")
        assert repo2.get_discord_token() == "bot-token-a"
    finally:
        repo2.close()
