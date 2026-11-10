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

from dockhand_discord_control.domain.models import ActionResult
from dockhand_discord_control.domain.ports import ChannelMappingRepository
from dockhand_discord_control.domain.use_cases import (
    SnapshotUseCase,
    StartContainerUseCase,
    StopContainerUseCase,
)

from . import rendering


class DiscordCommandHandlers:
    """Handle /dockhand_* slash commands through domain use cases."""

    def __init__(
        self,
        *,
        snapshot_use_case: SnapshotUseCase,
        start_use_case: StartContainerUseCase,
        stop_use_case: StopContainerUseCase,
        mapping_repo: ChannelMappingRepository,
    ) -> None:
        self._snapshot_use_case = snapshot_use_case
        self._start_use_case = start_use_case
        self._stop_use_case = stop_use_case
        self._mapping_repo = mapping_repo

    def handle_status(self, interaction: object, channel_id: str) -> str:
        """Render the status of all environments and containers."""
        del interaction  # owned by the Discord layer; the reply is returned as text
        snapshot = self._snapshot_use_case.execute()
        return rendering.render_snapshot(snapshot)

    def handle_list(self, interaction: object, channel_id: str) -> str:
        """Render the list of all containers."""
        del interaction  # owned by the Discord layer; the reply is returned as text
        snapshot = self._snapshot_use_case.execute()
        return rendering.render_container_list(snapshot.containers)

    def handle_start(
        self, interaction: object, channel_id: str, container_name: str
    ) -> str:
        """Authorize the channel for the container, then start it."""
        del interaction  # owned by the Discord layer; the reply is returned as text
        result = self._authorized_container_action(
            channel_id, container_name, self._start_use_case
        )
        return rendering.render_action_result(result, "start")

    def handle_stop(
        self, interaction: object, channel_id: str, container_name: str
    ) -> str:
        """Authorize the channel for the container, then stop it."""
        del interaction  # owned by the Discord layer; the reply is returned as text
        result = self._authorized_container_action(
            channel_id, container_name, self._stop_use_case
        )
        return rendering.render_action_result(result, "stop")

    def _authorized_container_action(
        self,
        channel_id: str,
        container_name: str,
        action: StartContainerUseCase | StopContainerUseCase,
    ) -> ActionResult:
        """Authorize the channel for the container, then perform the action.

        A channel is authorized when it has an enabled mapping for exactly
        this container name. Otherwise a failed :class:`ActionResult` is
        returned and no dockhand call is made.
        """
        mapping = self._mapping_repo.get_mapping(channel_id)
        if (
            mapping is None
            or not mapping.enabled
            or mapping.container_name != container_name
        ):
            return ActionResult(
                ok=False,
                message=(
                    f"not authorized: channel {channel_id!r} is not enabled "
                    f"for container {container_name!r}"
                ),
            )
        return action.execute(channel_id, container_name)
