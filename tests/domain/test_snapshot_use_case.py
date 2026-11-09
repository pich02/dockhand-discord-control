"""Tests for SnapshotUseCase."""

import pytest

from dockhand_discord_control.domain.exceptions import DockhandClientError
from dockhand_discord_control.domain.models import (
    ContainerStatus,
    DockerContainer,
    DockhandEnvironment,
    EnvironmentStatus,
    Snapshot,
)
from dockhand_discord_control.domain.use_cases import SnapshotUseCase


class _FailingClient:
    def list_environments(self) -> list[DockhandEnvironment]:
        raise DockhandClientError("server down")

    def list_containers(self, environment_id: str) -> list[DockerContainer]:
        raise AssertionError("list_containers must not be called")

    def start_container(self, container_id: str):
        raise AssertionError("start_container must not be called")

    def stop_container(self, container_id: str):
        raise AssertionError("stop_container must not be called")


class _SnapshotClient:
    def __init__(
        self,
        environments: list[DockhandEnvironment],
        containers: list[DockerContainer],
    ) -> None:
        self._environments = environments
        self._containers = containers

    def list_environments(self) -> list[DockhandEnvironment]:
        return list(self._environments)

    def list_containers(self, environment_id: str) -> list[DockerContainer]:
        return [
            container
            for container in self._containers
            if container.environment_id == environment_id
        ]

    def start_container(self, container_id: str):
        raise AssertionError("start_container must not be called")

    def stop_container(self, container_id: str):
        raise AssertionError("stop_container must not be called")


def _environment(environment_id: str, name: str) -> DockhandEnvironment:
    return DockhandEnvironment(
        id=environment_id,
        name=name,
        status=EnvironmentStatus.RUNNING,
        base_url=f"http://{name}:8000",
    )


def _container(container_id: str, name: str, environment_id: str) -> DockerContainer:
    return DockerContainer(
        id=container_id,
        name=name,
        image="nginx:latest",
        status=ContainerStatus.STOPPED,
        environment_id=environment_id,
    )


def test_execute_returns_snapshot_of_all_environments_and_containers() -> None:
    env_a = _environment("e1", "prod")
    env_b = _environment("e2", "stage")
    containers = [
        _container("c1", "web", "e1"),
        _container("c2", "api", "e1"),
        _container("c3", "web", "e2"),
    ]
    client = _SnapshotClient(environments=[env_a, env_b], containers=containers)

    snapshot = SnapshotUseCase(client).execute()

    assert snapshot == Snapshot(environments=[env_a, env_b], containers=containers)


def test_execute_propagates_client_errors() -> None:
    with pytest.raises(DockhandClientError):
        SnapshotUseCase(_FailingClient()).execute()
