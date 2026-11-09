"""HTTP adapter for the Dockhand REST API.

Implements :class:`dockhand_discord_control.domain.ports.DockhandClient` on top
of :mod:`httpx`, using bearer-token authentication.
"""

from typing import Any

import httpx
from pydantic import TypeAdapter

from dockhand_discord_control.domain.exceptions import DockhandClientError
from dockhand_discord_control.domain.models import (
    ActionResult,
    DockerContainer,
    DockhandEnvironment,
)
from dockhand_discord_control.domain.ports import DockhandClient


class DockhandApiClient(DockhandClient):
    """DockhandClient backed by the Dockhand server's REST API.

    Every request carries ``Authorization: Bearer <api_token>``. Endpoint paths
    are joined to ``base_url``, so callers only need the server root URL.
    """

    # TODO: The exact Dockhand REST API surface is unconfirmed (research item,
    # see docs/ARCHITECTURE.md §10). Endpoint shapes below are reversible
    # implementation assumptions -- NOT a verified contract:
    #
    #     GET    /environments                              -> list[DockhandEnvironment]
    #     GET    /environments/{env_id}/containers          -> list[DockerContainer]
    #     POST   /containers/{container_id}/start           -> 2xx means started
    #     POST   /containers/{container_id}/stop            -> 2xx means stopped
    #
    # Auth scheme (bearer token) is likewise assumed. Verify these against the
    # real Dockhand server; if they differ, only the path strings here change.

    def __init__(
        self,
        base_url: str,
        api_token: str,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_token = api_token
        self._client = client or httpx.Client()

    def _url(self, path: str) -> str:
        """Join ``base_url`` with an endpoint path."""
        return f"{self._base_url}/{path.lstrip('/')}"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_token}"}

    # -- query endpoints (return domain models) --

    def list_environments(self) -> list[DockhandEnvironment]:
        """Return all known Dockhand environments."""
        response = self._get("/environments")
        return self._parse_list(response.content, list[DockhandEnvironment])

    def list_containers(self, environment_id: str) -> list[DockerContainer]:
        """Return the containers of the given environment."""
        response = self._get(f"/environments/{environment_id}/containers")
        return self._parse_list(response.content, list[DockerContainer])

    # -- control endpoints (return ActionResult) --

    def start_container(self, container_id: str) -> ActionResult:
        """Start the container with the given id."""
        return self._post(f"/containers/{container_id}/start", "started")

    def stop_container(self, container_id: str) -> ActionResult:
        """Stop the container with the given id."""
        return self._post(f"/containers/{container_id}/stop", "stopped")

    # -- transport --

    def _get(self, path: str) -> httpx.Response:
        try:
            response = self._client.get(self._url(path), headers=self._headers())
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            raise DockhandClientError(
                f"Dockhand API returned HTTP {exc.response.status_code}: {exc}"
            ) from exc
        except httpx.RequestError as exc:
            raise DockhandClientError(f"Dockhand API request failed: {exc}") from exc

    def _post(self, path: str, ok_message: str) -> ActionResult:
        try:
            response = self._client.post(self._url(path), headers=self._headers())
            response.raise_for_status()
            return ActionResult(ok=True, message=ok_message)
        except httpx.HTTPStatusError as exc:
            return ActionResult(
                ok=False,
                message=f"Dockhand API returned HTTP {exc.response.status_code}: {exc}",
            )
        except httpx.RequestError as exc:
            return ActionResult(
                ok=False,
                message=f"Dockhand API request failed: {exc}",
            )

    @staticmethod
    def _parse_list(content: bytes, model_type: Any) -> Any:
        try:
            return TypeAdapter(model_type).validate_json(content)
        except Exception as exc:  # pragma: no cover - defensive parse guard
            raise DockhandClientError(f"Dockhand API response invalid: {exc}") from exc
