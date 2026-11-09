"""Application configuration: environment variables with SQLite DB overrides.

`Settings` is a pydantic-settings model whose fields are populated from
environment variables.  `load_from_db` builds a `Settings` from the
environment and then applies any overrides stored in the SQLite-backed
settings repository (database wins over environment).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from dockhand_discord_control.domain.ports import SettingsRepository

__all__ = ["Settings", "load_from_db"]


class Settings(BaseSettings):
    """Runtime configuration.

    Fields default to empty strings except `db_path`, which defaults to
    ``./data/app.sqlite`` relative to the current working directory.
    """

    model_config = SettingsConfigDict(env_file=None)

    dockhand_base_url: str = ""
    dockhand_api_token: str = ""
    discord_bot_token: str = ""
    discord_guild_id: str = ""
    db_path: str = "./data/app.sqlite"


def load_from_db(settings_repo: SettingsRepository) -> Settings:
    """Build `Settings` from env, then apply overrides from *settings_repo*."""
    settings = Settings()
    base_url, token = settings_repo.get_dockhand_settings()
    if base_url:
        settings.dockhand_base_url = base_url
    if token:
        settings.dockhand_api_token = token
    discord_token = settings_repo.get_discord_token()
    if discord_token:
        settings.discord_bot_token = discord_token
    return settings
