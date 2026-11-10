"""Application use cases orchestrating domain ports and models.

No infrastructure, persistence, UI, or docker calls happen here.
"""

from typing import Protocol, runtime_checkable

from .exceptions import DockhandClientError, MappingNotFoundError, UnauthorizedError
from .models import ActionResult, ChannelMapping, DockerContainer, Snapshot
from .ports import ChannelMappingRepository, DockhandClient


@runtime_checkable
class ContainerActionUseCase(Protocol):
    """Contract for use cases that act on a container on behalf of a channel.

    Every container action use case authorizes the calling channel and then
    performs the action, so adapters can treat them interchangeably.
    """

    def execute(self, channel_id: str, container_name: str) -> ActionResult:
        """Perform the action for an authorized channel."""
        raise NotImplementedError


class SnapshotUseCase:
    """Build a snapshot of all environments and their containers."""

    def __init__(self, client: DockhandClient) -> None:
        self._client = client

    def execute(self) -> Snapshot:
        environments = self._client.list_environments()
        containers: list[DockerContainer] = []
        for environment in environments:
            containers.extend(self._client.list_containers(environment.id))
        return Snapshot(environments=environments, containers=containers)


class StartContainerUseCase:
    """Start a container when the calling channel is authorized."""

    def __init__(
        self,
        client: DockhandClient,
        mappings: ChannelMappingRepository,
    ) -> None:
        self._client = client
        self._mappings = mappings

    def execute(self, channel_id: str, container_name: str) -> ActionResult:
        try:
            mapping = self._authorize(channel_id, container_name)
        except (MappingNotFoundError, UnauthorizedError) as exc:
            return ActionResult(ok=False, message=str(exc))
        try:
            return self._client.start_container(mapping.container_name)
        except DockhandClientError as exc:
            return ActionResult(ok=False, message=str(exc) or "dockhand client error")

    def _authorize(self, channel_id: str, container_name: str) -> ChannelMapping:
        mapping = self._mappings.get_mapping(channel_id)
        if mapping is None:
            raise MappingNotFoundError(f"no mapping for channel {channel_id!r}")
        if not mapping.enabled or mapping.container_name != container_name:
            raise UnauthorizedError(
                f"channel {channel_id!r} not authorized for {container_name!r}"
            )
        return mapping


class StopContainerUseCase:
    """Stop a container when the calling channel is authorized."""

    def __init__(
        self,
        client: DockhandClient,
        mappings: ChannelMappingRepository,
    ) -> None:
        self._client = client
        self._mappings = mappings

    def execute(self, channel_id: str, container_name: str) -> ActionResult:
        try:
            mapping = self._authorize(channel_id, container_name)
        except (MappingNotFoundError, UnauthorizedError) as exc:
            return ActionResult(ok=False, message=str(exc))
        try:
            return self._client.stop_container(mapping.container_name)
        except DockhandClientError as exc:
            return ActionResult(ok=False, message=str(exc) or "dockhand client error")

    def _authorize(self, channel_id: str, container_name: str) -> ChannelMapping:
        mapping = self._mappings.get_mapping(channel_id)
        if mapping is None:
            raise MappingNotFoundError(f"no mapping for channel {channel_id!r}")
        if not mapping.enabled or mapping.container_name != container_name:
            raise UnauthorizedError(
                f"channel {channel_id!r} not authorized for {container_name!r}"
            )
        return mapping


class RestartContainerUseCase:
    """Restart a container when the calling channel is authorized.

    Stops the container first, then starts it again. The stop is a
    precondition: when it fails the start is not attempted, so the container
    is never left in a half-restarted state.
    """

    def __init__(
        self,
        client: DockhandClient,
        mappings: ChannelMappingRepository,
    ) -> None:
        self._client = client
        self._mappings = mappings

    def execute(self, channel_id: str, container_name: str) -> ActionResult:
        """Stop then start the container authorized for this channel.

        Returns a failed :class:`ActionResult` when the channel is not
        authorized, when the stop fails, or when the start fails after a
        successful stop.
        """
        try:
            mapping = self._authorize(channel_id, container_name)
        except (MappingNotFoundError, UnauthorizedError) as exc:
            return ActionResult(ok=False, message=str(exc))
        try:
            stop_result = self._client.stop_container(mapping.container_name)
        except DockhandClientError as exc:
            return ActionResult(
                ok=False,
                message=(
                    f"could not stop the container: "
                    f"{str(exc) or 'dockhand client error'}"
                ),
            )
        if not stop_result.ok:
            return ActionResult(
                ok=False,
                message=f"could not stop the container: {stop_result.message}",
            )
        try:
            start_result = self._client.start_container(mapping.container_name)
        except DockhandClientError as exc:
            return ActionResult(
                ok=False,
                message=(
                    f"could not start the container after stopping it: "
                    f"{str(exc) or 'dockhand client error'}"
                ),
            )
        if not start_result.ok:
            return ActionResult(
                ok=False,
                message=(
                    f"could not start the container after stopping it: "
                    f"{start_result.message}"
                ),
            )
        return ActionResult(
            ok=True,
            message=f"stopped then started container {mapping.container_name}",
        )

    def _authorize(self, channel_id: str, container_name: str) -> ChannelMapping:
        mapping = self._mappings.get_mapping(channel_id)
        if mapping is None:
            raise MappingNotFoundError(f"no mapping for channel {channel_id!r}")
        if not mapping.enabled or mapping.container_name != container_name:
            raise UnauthorizedError(
                f"channel {channel_id!r} not authorized for {container_name!r}"
            )
        return mapping
