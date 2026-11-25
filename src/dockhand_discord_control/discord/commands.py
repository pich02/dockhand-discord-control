"""Pure-Python command handlers for the Discord adapter.

The :class:`DiscordCommandHandlers` class implements the /dockhand_* slash
commands by delegating to domain use cases and rendering replies through
pure formatting functions. Every method takes an opaque ``interaction``
value (owned by the Discord layer) and returns a plain :class:`str`, so the
handlers are unit-testable without :mod:`discord.py` or a live Discord
connection.

The discord adapter layer depends only on the domain layer (plus
:mod:`discord.py` in the bot wiring), never on dockhand or persistence
directly.
"""

from __future__ import annotations

from dockhand_discord_control.domain.exceptions import DockhandClientError
from dockhand_discord_control.domain.use_cases import (
    RestartContainerUseCase,
    SnapshotUseCase,
    StartContainerUseCase,
    StopContainerUseCase,
)

from . import rendering

_SNAPSHOT_ERROR_MESSAGE = "Unable to reach Dockhand right now. Please try again later."


class DiscordCommandHandlers:
    """Handle /dockhand_* slash commands through domain use cases."""

    def __init__(
        self,
        *,
        snapshot_use_case: SnapshotUseCase,
        start_use_case: StartContainerUseCase,
        stop_use_case: StopContainerUseCase,
        restart_use_case: RestartContainerUseCase,
    ) -> None:
        self._snapshot_use_case = snapshot_use_case
        self._start_use_case = start_use_case
        self._stop_use_case = stop_use_case
        self._restart_use_case = restart_use_case

    def handle_status(self, interaction: object, channel_id: str) -> str:
        """Render the status of all environments and containers."""
        del interaction  # owned by the Discord layer; the reply is returned as text
        try:
            snapshot = self._snapshot_use_case.execute()
        except DockhandClientError:
            return _SNAPSHOT_ERROR_MESSAGE
        return rendering.render_snapshot(snapshot)

    def handle_list(self, interaction: object, channel_id: str) -> str:
        """Render the list of all containers."""
        del interaction  # owned by the Discord layer; the reply is returned as text
        try:
            snapshot = self._snapshot_use_case.execute()
        except DockhandClientError:
            return _SNAPSHOT_ERROR_MESSAGE
        return rendering.render_container_list(snapshot.containers)

    def handle_start(
        self, interaction: object, channel_id: str, container_name: str
    ) -> str:
        """Start a container authorized for this channel."""
        del interaction  # owned by the Discord layer; the reply is returned as text
        result = self._start_use_case.execute(channel_id, container_name)
        return rendering.render_action_result(result, "start")

    def handle_stop(
        self, interaction: object, channel_id: str, container_name: str
    ) -> str:
        """Stop a container authorized for this channel."""
        del interaction  # owned by the Discord layer; the reply is returned as text
        result = self._stop_use_case.execute(channel_id, container_name)
        return rendering.render_action_result(result, "stop")

    def handle_restart(
        self, interaction: object, channel_id: str, container_name: str
    ) -> str:
        """Restart a container authorized for this channel."""
        del interaction  # owned by the Discord layer; the reply is returned as text
        result = self._restart_use_case.execute(channel_id, container_name)
        return rendering.render_action_result(result, "restart")
