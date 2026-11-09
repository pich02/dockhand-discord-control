"""Tests for the Settings model and database override loading."""

from __future__ import annotations

from dockhand_discord_control.persistence import (
    Settings,
    SqliteSettingsRepository,
    load_from_db,
)


def _clear_env(monkeypatch) -> None:
    for name in (
        "DOCKHAND_BASE_URL",
        "DOCKHAND_API_TOKEN",
        "DISCORD_BOT_TOKEN",
        "DISCORD_GUILD_ID",
        "DB_PATH",
    ):
        monkeypatch.delenv(name, raising=False)


def test_settings_defaults(monkeypatch) -> None:
    _clear_env(monkeypatch)
    settings = Settings()
    assert settings.dockhand_base_url == ""
    assert settings.dockhand_api_token == ""
    assert settings.discord_bot_token == ""
    assert settings.discord_guild_id == ""
    assert settings.db_path == "./data/app.sqlite"


def test_settings_reads_environment(monkeypatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("DOCKHAND_BASE_URL", "http://env-dockhand:8080")
    monkeypatch.setenv("DOCKHAND_API_TOKEN", "env-token")
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "env-bot-token")
    monkeypatch.setenv("DISCORD_GUILD_ID", "env-guild")
    monkeypatch.setenv("DB_PATH", "/tmp/custom/app.sqlite")
    settings = Settings()
    assert settings.dockhand_base_url == "http://env-dockhand:8080"
    assert settings.dockhand_api_token == "env-token"
    assert settings.discord_bot_token == "env-bot-token"
    assert settings.discord_guild_id == "env-guild"
    assert settings.db_path == "/tmp/custom/app.sqlite"


def test_load_from_db_applies_db_overrides(monkeypatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("DOCKHAND_BASE_URL", "http://env-dockhand:8080")
    monkeypatch.setenv("DOCKHAND_API_TOKEN", "env-token")
    repo = SqliteSettingsRepository(":memory:")
    try:
        repo.set_dockhand_settings("http://db-dockhand:9000", "db-token")
        settings = load_from_db(repo)
    finally:
        repo.close()
    assert settings.dockhand_base_url == "http://db-dockhand:9000"
    assert settings.dockhand_api_token == "db-token"


def test_load_from_db_applies_discord_token_override(monkeypatch) -> None:
    _clear_env(monkeypatch)
    repo = SqliteSettingsRepository(":memory:")
    try:
        repo.set_discord_token("db-bot-token")
        settings = load_from_db(repo)
    finally:
        repo.close()
    assert settings.discord_bot_token == "db-bot-token"


def test_load_from_db_keeps_env_when_db_is_empty(monkeypatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("DOCKHAND_BASE_URL", "http://env-dockhand:8080")
    repo = SqliteSettingsRepository(":memory:")
    try:
        settings = load_from_db(repo)
    finally:
        repo.close()
    assert settings.dockhand_base_url == "http://env-dockhand:8080"
    assert settings.discord_bot_token == ""
