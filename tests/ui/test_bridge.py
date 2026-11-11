"""Tests for the Discord bridge lifecycle and token verification."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import httpx
import pytest

from dockhand_discord_control.ui import bridge as bridge_module
from dockhand_discord_control.ui.bridge import DiscordBridge, verify_discord_token


class FakeBot:
    """Minimal stand-in for a discord.py bot."""

    instances: list[FakeBot] = []

    def __init__(self, *, token: str, handlers: object, guild_id: str | None = None):
        self.token = token
        self.handlers = handlers
        self.guild_id = guild_id
        self.logged_in = threading.Event()
        self._stop: asyncio.Event | None = None
        FakeBot.instances.append(self)

    async def start(self, token: str) -> None:
        self._stop = asyncio.Event()
        self.logged_in.set()
        assert self._stop is not None
        await self._stop.wait()

    async def close(self) -> None:
        if self._stop is not None:
            self._stop.set()


@pytest.fixture(autouse=True)
def _fake_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeBot.instances = []
    monkeypatch.setattr(bridge_module, "DiscordBot", FakeBot)


def _client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


def test_verify_discord_token_accepts_valid_token() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json={"id": "1"})
    )
    assert verify_discord_token("good-token", _client(transport)) is None


def test_verify_discord_token_rejects_invalid_token() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(401, json={}))
    error = verify_discord_token("bad-token", _client(transport))
    assert error is not None
    assert "rejected" in error


def test_verify_discord_token_reports_transport_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no network")

    transport = httpx.MockTransport(handler)
    error = verify_discord_token("good-token", _client(transport))
    assert error is not None
    assert "could not reach the Discord API" in error


def test_verify_discord_token_requires_a_token() -> None:
    assert verify_discord_token("  ") is not None


def test_bridge_start_and_stop(tmp_path: Path) -> None:
    bridge = DiscordBridge()

    started, message = bridge.start(
        token="bot-token",
        guild_id=None,
        base_url="http://dockhand:8080",
        api_token="dockhand-secret",
        db_path=str(tmp_path / "app.sqlite"),
    )

    assert started
    assert "started" in message
    assert FakeBot.instances
    bot = FakeBot.instances[0]
    assert bot.logged_in.wait(timeout=5)
    assert bridge.is_running()
    assert "running" in bridge.status()

    bridge.stop()

    assert not bridge.is_running()
    assert "not running" in bridge.status()


def test_bridge_without_token_does_not_start(tmp_path: Path) -> None:
    bridge = DiscordBridge()

    started, message = bridge.start(
        token="",
        guild_id=None,
        base_url="http://dockhand:8080",
        api_token="dockhand-secret",
        db_path=str(tmp_path / "app.sqlite"),
    )

    assert not started
    assert "no bot token configured" in message
    assert not bridge.is_running()


def test_bridge_restarts_with_a_new_token(tmp_path: Path) -> None:
    bridge = DiscordBridge()

    bridge.start(
        token="first-token",
        guild_id=None,
        base_url="http://dockhand:8080",
        api_token="dockhand-secret",
        db_path=str(tmp_path / "app.sqlite"),
    )
    assert FakeBot.instances[0].logged_in.wait(timeout=5)

    bridge.start(
        token="second-token",
        guild_id="guild-1",
        base_url="http://dockhand:8080",
        api_token="dockhand-secret",
        db_path=str(tmp_path / "app.sqlite"),
    )

    assert len(FakeBot.instances) == 2
    assert FakeBot.instances[1].logged_in.wait(timeout=5)
    assert FakeBot.instances[1].token == "second-token"
    bridge.stop()
