"""Tests for DockhandApiClient using a stub httpx transport (no network)."""

import httpx
import pytest

from dockhand_discord_control.dockhand import DockhandApiClient
from dockhand_discord_control.domain.exceptions import DockhandClientError
from dockhand_discord_control.domain.models import (
    ActionResult,
    ContainerStatus,
    DockerContainer,
    DockhandEnvironment,
    EnvironmentStatus,
)

_BASE_URL = "http://dockhand:8080"
_TOKEN = "token123"


def _make_client(handler):
    transport = httpx.MockTransport(handler)
    return DockhandApiClient(
        _BASE_URL, _TOKEN, client=httpx.Client(transport=transport)
    )


def _environments_handler(request):
    assert request.headers["authorization"] == f"Bearer {_TOKEN}"
    assert request.url.path == "/environments"
    return httpx.Response(
        200,
        json=[
            {
                "id": "e1",
                "name": "prod",
                "status": "running",
                "base_url": "http://host:8080",
            }
        ],
        request=request,
    )


def _containers_handler(request):
    assert request.headers["authorization"] == f"Bearer {_TOKEN}"
    assert request.url.path == "/environments/e1/containers"
    return httpx.Response(
        200,
        json=[
            {
                "id": "c1",
                "name": "web",
                "image": "nginx:latest",
                "status": "running",
                "environment_id": "e1",
            }
        ],
        request=request,
    )


def _start_handler(request):
    assert request.url.path == "/containers/c1/start"
    return httpx.Response(200, request=request)


def _stop_handler(request):
    assert request.url.path == "/containers/c1/stop"
    return httpx.Response(200, request=request)


def test_list_environments_happy_path():
    client = _make_client(_environments_handler)

    result = client.list_environments()

    assert result == [
        DockhandEnvironment(
            id="e1",
            name="prod",
            status=EnvironmentStatus.RUNNING,
            base_url="http://host:8080",
        )
    ]


def test_list_containers_happy_path():
    client = _make_client(_containers_handler)

    result = client.list_containers("e1")

    assert result == [
        DockerContainer(
            id="c1",
            name="web",
            image="nginx:latest",
            status=ContainerStatus.RUNNING,
            environment_id="e1",
        )
    ]


def test_start_container_happy_path():
    client = _make_client(_start_handler)

    result = client.start_container("c1")

    assert result == ActionResult(ok=True, message="started")


def test_stop_container_happy_path():
    client = _make_client(_stop_handler)

    result = client.stop_container("c1")

    assert result == ActionResult(ok=True, message="stopped")


def _error_handler(status_code):
    def handler(request):
        return httpx.Response(status_code, request=request)

    return handler


@pytest.mark.parametrize("status_code", [401, 404, 500])
def test_client_error_status_maps_to_failed_action_result(status_code):
    client = _make_client(_error_handler(status_code))

    result = client.start_container("c1")

    assert result.ok is False
    assert str(status_code) in result.message
    assert result.payload is None


@pytest.mark.parametrize("status_code", [401, 404, 500])
def test_stop_server_error_maps_to_failed_action_result(status_code):
    client = _make_client(_error_handler(status_code))

    result = client.stop_container("c1")

    assert result.ok is False
    assert str(status_code) in result.message


def test_network_error_maps_to_failed_action_result():
    def handler(request):
        raise httpx.ConnectError("connection refused")

    client = _make_client(handler)

    result = client.start_container("c1")

    assert result.ok is False
    assert "connection refused" in result.message


def test_timeout_maps_to_failed_action_result():
    def handler(request):
        raise httpx.TimeoutException("read timed out")

    client = _make_client(handler)

    result = client.stop_container("c1")

    assert result.ok is False
    assert "read timed out" in result.message


def test_list_environments_server_error_raises_domain_error():
    client = _make_client(_error_handler(500))

    with pytest.raises(DockhandClientError):
        client.list_environments()


def test_trailing_slash_base_url_is_normalized():
    def handler(request):
        assert request.url.path == "/environments"
        return httpx.Response(200, json=[], request=request)

    transport = httpx.MockTransport(handler)
    client = DockhandApiClient(
        "http://dockhand:8080/", _TOKEN, client=httpx.Client(transport=transport)
    )

    assert client.list_environments() == []
