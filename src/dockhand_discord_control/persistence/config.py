"""Application configuration: database path.

Only the SQLite database path is read from the environment. All Dockhand and
Discord settings are configured through the web UI at ``/settings`` and persisted
in SQLite.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings"]


class Settings(BaseSettings):
    """Runtime configuration.

    Only ``db_path`` is populated from the environment (``DB_PATH``); it
    defaults to ``./data/app.sqlite`` relative to the current working directory.
    """

    model_config = SettingsConfigDict(env_file=None)

    db_path: str = "./data/app.sqlite"
