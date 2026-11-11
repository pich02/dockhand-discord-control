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
        self.closed = False
        self._stop: asyncio.Event | None = None
        FakeBot.instances.append(self)

    async def start(self, token: str) -> None:
        self._stop = asyncio.Event()
        self.logged_in.set()
        assert self._stop is not None
        await self._stop.wait()

    async def close(self) -> None:
        self.closed = True
        if self._stop is not None:
            self._stop.set()


class FailingBot(FakeBot):
    """A bot whose login fails."""

    async def start(self, token: str) -> None:
        self.logged_in.set()
        raise RuntimeError("improper token format")


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


def test_bridge_start_is_idempotent_with_the_same_config(tmp_path: Path) -> None:
    bridge = DiscordBridge()
    kwargs = {
        "token": "bot-token",
        "guild_id": None,
        "base_url": "http://dockhand:8080",
        "api_token": "dockhand-secret",
        "db_path": str(tmp_path / "app.sqlite"),
    }

    started, _message = bridge.start(**kwargs)
    assert started
    assert FakeBot.instances[0].logged_in.wait(timeout=5)

    started, message = bridge.start(**kwargs)

    assert started
    assert "already running" in message
    assert len(FakeBot.instances) == 1
    bridge.stop()


def test_bridge_stop_closes_the_bot(tmp_path: Path) -> None:
    bridge = DiscordBridge()
    bridge.start(
        token="bot-token",
        guild_id=None,
        base_url="http://dockhand:8080",
        api_token="dockhand-secret",
        db_path=str(tmp_path / "app.sqlite"),
    )
    bot = FakeBot.instances[0]
    assert bot.logged_in.wait(timeout=5)

    bridge.stop()

    assert bot.closed
    assert not bridge.is_running()


def test_bridge_restarts_when_the_dockhand_url_changes(tmp_path: Path) -> None:
    bridge = DiscordBridge()
    common = {
        "token": "bot-token",
        "guild_id": None,
        "api_token": "dockhand-secret",
        "db_path": str(tmp_path / "app.sqlite"),
    }
    bridge.start(base_url="http://dockhand:8080", **common)
    assert FakeBot.instances[0].logged_in.wait(timeout=5)

    bridge.start(base_url="http://other:9000", **common)

    assert len(FakeBot.instances) == 2
    assert FakeBot.instances[0].closed
    assert FakeBot.instances[1].logged_in.wait(timeout=5)
    bridge.stop()


def test_bridge_reports_a_failed_login(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(bridge_module, "DiscordBot", FailingBot)
    bridge = DiscordBridge()

    bridge.start(
        token="bad-token",
        guild_id=None,
        base_url="http://dockhand:8080",
        api_token="dockhand-secret",
        db_path=str(tmp_path / "app.sqlite"),
    )
    assert FailingBot.instances[0].logged_in.wait(timeout=5)

    for _attempt in range(100):
        if bridge.error() is not None:
            break
        threading.Event().wait(0.05)

    assert bridge.error() is not None
    assert "improper token format" in bridge.status()
    assert "failed" in bridge.status()


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
