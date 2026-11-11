"""Lifecycle management for the Discord bridge.

The bridge runs the Discord bot in a background daemon thread inside the
Reflex process.  It must be startable and stoppable at runtime, because the
bot token and the Dockhand connection settings are configured through the web
UI and can change while the app is running.

This module also verifies a bot token against the Discord API so the UI can
report an authentication problem immediately instead of silently failing in a
background thread.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

import httpx

from dockhand_discord_control.discord import DiscordBot
from dockhand_discord_control.discord.commands import DiscordCommandHandlers
from dockhand_discord_control.dockhand.client import DockhandApiClient
from dockhand_discord_control.domain.use_cases import (
    RestartContainerUseCase,
    SnapshotUseCase,
    StartContainerUseCase,
    StopContainerUseCase,
)
from dockhand_discord_control.persistence import SqliteChannelMappingRepository

logger = logging.getLogger(__name__)

__all__ = ["DiscordBridge", "discord_bridge", "verify_discord_token"]

DISCORD_API_URL = "https://discord.com/api/v10/users/@me"


def verify_discord_token(
    token: str,
    client: httpx.Client | None = None,
) -> str | None:
    """Check a bot token against the Discord API.

    Returns ``None`` when the token is accepted, otherwise a human-readable
    error message describing the failure.
    """
    if not token.strip():
        return "no Discord bot token configured"
    http = client or httpx.Client(timeout=10.0)
    try:
        response = http.get(
            DISCORD_API_URL,
            headers={"Authorization": f"Bot {token.strip()}"},
        )
    except httpx.RequestError as exc:
        return f"could not reach the Discord API: {exc}"
    finally:
        if client is None:
            http.close()
    if response.status_code == 200:
        return None
    if response.status_code in (401, 403):
        return "the Discord bot token was rejected by Discord"
    return f"the Discord API returned HTTP {response.status_code}"


class DiscordBridge:
    """Owns the background Discord bot thread and its lifecycle."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._bot: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._token: str | None = None
        self._error: str | None = None

    # -- queries ----------------------------------------------------------

    def is_running(self) -> bool:
        """Return whether a bot thread is currently alive."""
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def error(self) -> str | None:
        """Return the last bot error, if any."""
        with self._lock:
            return self._error

    def status(self) -> str:
        """Return a one-line description of the bridge state."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                if self._error:
                    return f"Discord bot failed: {self._error}"
                return "Discord bot is running."
            if self._error:
                return f"Discord bot failed: {self._error}"
            return "Discord bot is not running."

    # -- lifecycle --------------------------------------------------------

    def start(
        self,
        *,
        token: str | None,
        guild_id: str | None,
        base_url: str,
        api_token: str,
        db_path: str,
    ) -> tuple[bool, str]:
        """Start (or restart) the bot thread.

        Returns ``(started, message)``.  When the bot is already running with
        the same token it is left untouched.
        """
        with self._lock:
            if not token or not token.strip():
                self._stop_locked()
                return False, "Discord bot not started: no bot token configured."
            token = token.strip()
            if self._thread is not None and self._thread.is_alive():
                if self._token == token:
                    return True, "Discord bot is already running."
                self._stop_locked()
            try:
                bot = DiscordBot(
                    token=token,
                    handlers=self._build_handlers(
                        base_url=base_url,
                        api_token=api_token,
                        db_path=db_path,
                    ),
                    guild_id=guild_id,
                )
            except Exception as exc:
                self._error = str(exc)
                logger.warning("Discord bridge failed to start: %s", exc)
                return False, f"Discord bot failed to start: {exc}"
            self._bot = bot
            self._token = token
            self._error = None
            thread = threading.Thread(
                target=self._run,
                args=(bot, token),
                daemon=True,
                name="discord-bridge",
            )
            self._thread = thread
            thread.start()
            return True, "Discord bot started."

    def stop(self) -> None:
        """Stop the bot thread if it is running."""
        with self._lock:
            self._stop_locked()

    # -- internals --------------------------------------------------------

    def _stop_locked(self) -> None:
        bot = self._bot
        loop = self._loop
        thread = self._thread
        if bot is not None and loop is not None and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(bot.close(), loop)
            try:
                future.result(timeout=10)
            except Exception as exc:  # pragma: no cover - shutdown best effort
                logger.warning("Discord bot did not close cleanly: %s", exc)
        if thread is not None and thread.is_alive():
            thread.join(timeout=10)
        self._bot = None
        self._loop = None
        self._thread = None
        self._token = None

    def _run(self, bot: Any, token: str) -> None:
        """Run the bot until it stops; record failures for the UI."""
        try:
            asyncio.run(self._run_bot(bot, token))
        except Exception as exc:
            with self._lock:
                self._error = str(exc)
            logger.warning("Discord bot stopped with an error: %s", exc)

    async def _run_bot(self, bot: Any, token: str) -> None:
        with self._lock:
            self._loop = asyncio.get_running_loop()
        await bot.start(token)

    @staticmethod
    def _build_handlers(
        *,
        base_url: str,
        api_token: str,
        db_path: str,
    ) -> DiscordCommandHandlers:
        """Build the command handlers used by the Discord slash commands."""
        client = DockhandApiClient(base_url=base_url, api_token=api_token)
        mapping_repo = SqliteChannelMappingRepository(db_path)
        return DiscordCommandHandlers(
            snapshot_use_case=SnapshotUseCase(client),
            start_use_case=StartContainerUseCase(client, mapping_repo),
            stop_use_case=StopContainerUseCase(client, mapping_repo),
            restart_use_case=RestartContainerUseCase(client, mapping_repo),
            mapping_repo=mapping_repo,
        )


discord_bridge = DiscordBridge()
