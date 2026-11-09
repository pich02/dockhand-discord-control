"""Application use cases orchestrating domain ports and models.

No infrastructure, persistence, UI, or docker calls happen here.
"""

from .exceptions import DockhandClientError, MappingNotFoundError, UnauthorizedError
from .models import ActionResult, ChannelMapping, DockerContainer, Snapshot
from .ports import ChannelMappingRepository, DockhandClient


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
