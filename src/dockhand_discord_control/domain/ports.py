"""Ports (interfaces) for the domain layer.

Adapters implement these protocols. The domain layer depends only on its
own models, never on adapters.
"""

from typing import Protocol, runtime_checkable

from .models import (
    ActionResult,
    ChannelMapping,
    DockerContainer,
    DockhandEnvironment,
)


@runtime_checkable
class DockhandClient(Protocol):
    """Port for querying and controlling the Dockhand server."""

    def list_environments(self) -> list[DockhandEnvironment]:
        """Return all known Dockhand environments."""
        raise NotImplementedError

    def list_containers(self, environment_id: str) -> list[DockerContainer]:
        """Return the containers of the given environment."""
        raise NotImplementedError

    def start_container(self, container_id: str) -> ActionResult:
        """Start the container with the given id."""
        raise NotImplementedError

    def stop_container(self, container_id: str) -> ActionResult:
        """Stop the container with the given id."""
        raise NotImplementedError


@runtime_checkable
class ChannelMappingRepository(Protocol):
    """Port for Discord channel to container mappings."""

    def get_mapping(self, channel_id: str) -> ChannelMapping | None:
        """Return the mapping for a channel, if any."""
        raise NotImplementedError

    def mappings_for_container(self, container_name: str) -> list[ChannelMapping]:
        """Return all mappings referencing a container name."""
        raise NotImplementedError


@runtime_checkable
class SettingsRepository(Protocol):
    """Port for configuration settings."""

    def get_dockhand_settings(self) -> tuple[str, str]:
        """Return the (base_url, token) for the Dockhand server."""
        raise NotImplementedError

    def get_discord_token(self) -> str | None:
        """Return the Discord bot token, if configured."""
        raise NotImplementedError
