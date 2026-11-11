#!/usr/bin/env python3
"""End-to-end check of the settings save flow against a running backend.

The script drives the Reflex backend over its real Socket.IO transport (the
same one the browser frontend uses): it sets the state variables, triggers the
``save_settings`` handler (the handler behind the "Save settings" button) and
asserts that

* the status message reaches the client and reports the outcome,
* the values are persisted in the SQLite database,
* the Discord bot status is reported.

The script is destructive for the database it writes to, so it defaults to a
dedicated database (``.data/e2e-app.sqlite``) and restores the rows of the
``app_settings`` table when it is done.

Usage:

    # terminal 1: the backend (use the dedicated database, not the real one)
    DB_PATH=./data/e2e-app.sqlite reflex run --env dev --backend-only \
        --backend-port 8000 --backend-host 127.0.0.1

    # terminal 2: this script
    uv run python scripts/e2e_settings_save.py

The browser itself cannot be driven in every environment (a headless browser
needs system libraries that are often missing), so this script covers the
backend half of the flow.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

import socketio

NAMESPACE = "/_event"
STATE_NAME = (
    "reflex___state____state.dockhand_discord_control___ui___state____app_state"
)
#: How long the script waits for the status message of the save.
STATUS_TIMEOUT = 60.0


def read_settings(db_path: str) -> dict[str, str]:
    """Return the ``app_settings`` rows of *db_path* (empty when absent)."""
    if not Path(db_path).exists():
        return {}
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute("SELECT key, value FROM app_settings").fetchall()
    except sqlite3.Error:
        return {}
    finally:
        connection.close()
    return {str(key): str(value) for key, value in rows}


def write_settings(db_path: str, rows: dict[str, str]) -> None:
    """Replace the ``app_settings`` rows of *db_path* with *rows*."""
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute("DELETE FROM app_settings")
            connection.executemany(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                list(rows.items()),
            )
    finally:
        connection.close()


async def wait_for_status(deltas: list[dict[str, Any]]) -> str:
    """Wait until a status message arrives and return it."""
    deadline = asyncio.get_running_loop().time() + STATUS_TIMEOUT
    while asyncio.get_running_loop().time() < deadline:
        status = _latest_status(deltas)
        if status:
            return status
        await asyncio.sleep(0.2)
    return _latest_status(deltas)


def _latest_status(deltas: list[dict[str, Any]]) -> str:
    state: dict[str, Any] = {}
    for delta in deltas:
        chunk = delta.get("delta", {}).get(STATE_NAME)
        if isinstance(chunk, dict):
            state.update(chunk)
    return str(state.get("status_message_rx_state_", ""))


def _latest_state(deltas: list[dict[str, Any]]) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for delta in deltas:
        chunk = delta.get("delta", {}).get(STATE_NAME)
        if isinstance(chunk, dict):
            state.update(chunk)
    return state


async def run(backend: str, db_path: str, base_url: str, clear_token: bool) -> int:
    """Drive the save flow and report the result."""
    token = str(uuid.uuid4())
    client = socketio.AsyncClient()
    deltas: list[dict[str, Any]] = []

    @client.on("event", namespace=NAMESPACE)
    async def on_event(data: Any) -> None:  # noqa: ANN401
        deltas.append(data)

    await client.connect(
        f"{backend}/?token={token}",
        socketio_path="/_event",
        namespaces=[NAMESPACE],
        transports=["websocket"],
        auth={},
    )

    async def emit(name: str, payload: dict[str, Any]) -> None:
        await client.emit(
            "event",
            {
                "name": name,
                "payload": payload,
                "router_data": {
                    "token": token,
                    "pathname": "/settings",
                    "asPath": "/settings",
                    "query": {},
                    "cookie": {},
                },
            },
            namespace=NAMESPACE,
        )

    prefix = f"{STATE_NAME}."
    await emit(f"{prefix}set_dockhand_base_url", {"value": base_url})
    await emit(f"{prefix}set_dockhand_api_token", {"value": "e2e-secret"})
    if clear_token:
        await emit(f"{prefix}set_discord_bot_token", {"value": ""})
    await emit(f"{prefix}set_discord_guild_id", {"value": ""})
    await asyncio.sleep(1)
    await emit(f"{prefix}save_settings", {})

    status = await wait_for_status(deltas)
    state = _latest_state(deltas)
    bot_status = str(state.get("discord_bot_status_rx_state_", ""))
    print("STATUS:", status)
    print("BOT STATUS:", bot_status)

    try:
        rows = read_settings(db_path)
    except sqlite3.Error as exc:
        print("PERSISTED ROWS: unavailable:", exc)
        rows = {}
    print("PERSISTED ROWS:", json.dumps(rows))
    persisted = rows.get("dockhand_base_url") == base_url

    await client.disconnect()

    ok = (
        "Settings saved." in status
        and persisted
        and "Dockhand connection failed" in status
        and bool(bot_status)
    )
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--db-path",
        default="./data/e2e-app.sqlite",
        help=(
            "Database the backend writes to. Use a dedicated database: the "
            "settings it contains are replaced during the check."
        ),
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:9",
        help="Dockhand URL used in the test; the default port is closed on purpose.",
    )
    parser.add_argument(
        "--clear-token",
        action="store_true",
        help="Also clear the stored Discord bot token (it is not set otherwise).",
    )
    parser.add_argument(
        "--keep-settings",
        action="store_true",
        help="Do not restore the settings rows of the database when the check ends.",
    )
    args = parser.parse_args()
    db_path = str(Path(args.db_path))
    original = read_settings(db_path)
    try:
        return asyncio.run(run(args.backend, db_path, args.base_url, args.clear_token))
    finally:
        if not args.keep_settings:
            write_settings(db_path, original)


if __name__ == "__main__":
    sys.exit(main())
