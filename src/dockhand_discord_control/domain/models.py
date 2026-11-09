"""Pure domain models for dockhand-discord-control.

Contains only pydantic models and str enums. No dependencies on other
layers of the application.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class ContainerStatus(StrEnum):
    """Lifecycle status of a Docker container."""

    RUNNING = "running"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


class EnvironmentStatus(StrEnum):
    """Lifecycle status of a Dockhand environment."""

    RUNNING = "running"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


class DockerContainer(BaseModel):
    """A Docker container managed by a Dockhand environment."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    image: str
    status: ContainerStatus
    environment_id: str


class DockhandEnvironment(BaseModel):
    """A Dockhand environment (a Docker host)."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    status: EnvironmentStatus
    base_url: str


class ChannelMapping(BaseModel):
    """Maps a Discord channel to a container, with an enable flag."""

    model_config = ConfigDict(frozen=True)

    container_name: str
    channel_id: str
    enabled: bool = True


class ActionResult(BaseModel):
    """Result of a domain action, carrying success/failure and an optional payload."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    message: str
    payload: Any | None = None


class Snapshot(BaseModel):
    """A point-in-time snapshot of environments and their containers."""

    model_config = ConfigDict(frozen=True)

    environments: list[DockhandEnvironment]
    containers: list[DockerContainer]
