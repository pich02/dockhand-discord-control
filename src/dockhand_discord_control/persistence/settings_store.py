"""SQLite-backed implementation of the :class:`SettingsRepository` port."""

from __future__ import annotations

import logging
from typing import Final

from dockhand_discord_control.domain.ports import SettingsRepository

from .database import (
    SETTINGS_KEY_DISCORD_BOT_TOKEN,
    SETTINGS_KEY_DISCORD_GUILD_ID,
    SETTINGS_KEY_DOCKHAND_API_TOKEN,
    SETTINGS_KEY_DOCKHAND_BASE_URL,
    get_connection,
    init_db,
)

logger = logging.getLogger(__name__)

__all__ = ["SqliteSettingsRepository"]


class SqliteSettingsRepository(SettingsRepository):
    """Reads/writes dockhand and discord settings in the `app_settings` table."""

    def __init__(self, db_path: str = "./data/app.sqlite") -> None:
        self._db_path: Final = db_path
        self._conn = get_connection(db_path)
        init_db(self._conn)

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def get_dockhand_settings(self) -> tuple[str, str]:
        """Return the (base_url, token) for the Dockhand server."""
        base_url = self._setting(SETTINGS_KEY_DOCKHAND_BASE_URL)
        token = self._setting(SETTINGS_KEY_DOCKHAND_API_TOKEN)
        return base_url, token

    def get_discord_token(self) -> str | None:
        """Return the Discord bot token, if configured."""
        value = self._setting(SETTINGS_KEY_DISCORD_BOT_TOKEN)
        return value or None

    def get_discord_guild_id(self) -> str | None:
        """Return the Discord guild ID, if configured."""
        value = self._setting(SETTINGS_KEY_DISCORD_GUILD_ID)
        return value or None

    def set_dockhand_settings(self, base_url: str, token: str) -> None:
        """Persist the Dockhand base URL and API token."""
        logger.info(
            "writing the Dockhand settings to %s (base_url=%s)",
            self._db_path,
            base_url,
        )
        self._upsert(SETTINGS_KEY_DOCKHAND_BASE_URL, base_url)
        self._upsert(SETTINGS_KEY_DOCKHAND_API_TOKEN, token)

    def set_discord_token(self, token: str | None) -> None:
        """Persist (or clear, when ``None``) the Discord bot token."""
        if token is None:
            with self._conn:
                self._conn.execute(
                    "DELETE FROM app_settings WHERE key = ?",
                    (SETTINGS_KEY_DISCORD_BOT_TOKEN,),
                )
        else:
            self._upsert(SETTINGS_KEY_DISCORD_BOT_TOKEN, token)

    def set_discord_guild_id(self, guild_id: str | None) -> None:
        """Persist (or clear, when ``None``) the Discord guild ID."""
        if guild_id is None or not guild_id:
            with self._conn:
                self._conn.execute(
                    "DELETE FROM app_settings WHERE key = ?",
                    (SETTINGS_KEY_DISCORD_GUILD_ID,),
                )
        else:
            self._upsert(SETTINGS_KEY_DISCORD_GUILD_ID, guild_id)

    def _setting(self, key: str) -> str:
        row = self._conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        ).fetchone()
        return "" if row is None else row["value"]

    def _upsert(self, key: str, value: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                (key, value),
            )
