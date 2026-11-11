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

    #: How long ``start`` waits for the bot thread to publish its event loop.
    STARTUP_TIMEOUT = 5.0
    #: How long ``stop`` waits for the bot thread to finish.
    STOP_TIMEOUT = 10.0

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # Guards the values published by the bot thread.  It is separate from
        # ``_lock`` because the stopping thread holds ``_lock`` while it
        # joins the bot thread, which would deadlock on a shared lock.
        self._data_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._bot: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._token: str | None = None
        self._config: tuple[str, str | None, str, str] | None = None
        self._error: str | None = None

    # -- queries ----------------------------------------------------------

    def is_running(self) -> bool:
        """Return whether a bot thread is currently alive."""
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def error(self) -> str | None:
        """Return the last bot error, if any."""
        with self._data_lock:
            return self._error

    def status(self) -> str:
        """Return a one-line description of the bridge state."""
        error = self.error()
        with self._lock:
            running = self._thread is not None and self._thread.is_alive()
        if running:
            if error:
                return f"Discord bot failed: {error}"
            return "Discord bot is running."
        if error:
            return f"Discord bot failed: {error}"
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

        Returns ``(started, message)``.  The bot is left untouched when it is
        already running with the same configuration; a changed token, guild
        id, Dockhand URL or Dockhand token restarts it so the bot always
        talks to the configured server.
        """
        ready = threading.Event()
        with self._lock:
            if not token or not token.strip():
                self._stop_locked()
                return False, "Discord bot not started: no bot token configured."
            token = token.strip()
            config = (token, guild_id, base_url, api_token)
            if self._thread is not None and self._thread.is_alive():
                if self._config == config:
                    return True, "Discord bot is already running."
                self._stop_locked()
                if self._thread is not None:
                    return False, (
                        "The previous Discord bot did not stop cleanly; "
                        "restart the app to replace it."
                    )
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
                self._set_error(str(exc))
                logger.warning("Discord bridge failed to start: %s", exc)
                return False, f"Discord bot failed to start: {exc}"
            self._token = token
            self._config = config
            with self._data_lock:
                self._bot = bot
            self._set_error(None)
            thread = threading.Thread(
                target=self._run,
                args=(bot, token, ready),
                daemon=True,
                name="discord-bridge",
            )
            self._thread = thread
            thread.start()
        # Wait for the bot thread to publish its event loop, so that a
        # following ``stop`` can close the bot instead of orphaning it.
        if not ready.wait(timeout=self.STARTUP_TIMEOUT):
            return True, "Discord bot is starting; it was not ready yet."
        return True, "Discord bot started."

    def stop(self) -> None:
        """Stop the bot thread if it is running."""
        with self._lock:
            self._stop_locked()

    # -- internals --------------------------------------------------------

    def _set_error(self, message: str | None) -> None:
        with self._data_lock:
            self._error = message

    def _stop_locked(self) -> None:
        with self._data_lock:
            bot = self._bot
            loop = self._loop
        thread = self._thread
        if bot is not None and loop is not None and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(bot.close(), loop)
            try:
                future.result(timeout=self.STOP_TIMEOUT)
            except Exception as exc:  # pragma: no cover - shutdown best effort
                logger.warning("Discord bot did not close cleanly: %s", exc)
        if thread is not None and thread.is_alive():
            thread.join(timeout=self.STOP_TIMEOUT)
            if thread.is_alive():
                # Keep the reference: dropping it would orphan a live bot.
                self._set_error("the Discord bot did not stop cleanly")
                logger.error(
                    "Discord bot thread did not stop within %ss", self.STOP_TIMEOUT
                )
                return
        with self._data_lock:
            self._bot = None
            self._loop = None
        self._thread = None
        self._token = None
        self._config = None
        self._set_error(None)

    def _run(self, bot: Any, token: str, ready: threading.Event) -> None:
        """Run the bot until it stops; record failures for the UI."""
        try:
            asyncio.run(self._run_bot(bot, token, ready))
        except Exception as exc:
            self._set_error(str(exc))
            logger.warning("Discord bot stopped with an error: %s", exc)
            ready.set()

    async def _run_bot(self, bot: Any, token: str, ready: threading.Event) -> None:
        loop = asyncio.get_running_loop()
        # Only the data lock is taken here: the stopping thread holds the
        # lifecycle lock while it joins this thread, so taking it here would
        # deadlock.
        with self._data_lock:
            current = self._bot is bot
            if current:
                self._loop = loop
        ready.set()
        if not current:
            # The bot was replaced or stopped before it came up.
            await bot.close()
            return
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
