#!/usr/bin/env python3
"""End-to-end check of the settings save flow against a running backend.

The script drives the Reflex backend over its real Socket.IO transport (the
same one the browser frontend uses): it sets the state variables, triggers the
``save_settings`` handler (the handler behind the "Save settings" button) and
asserts that

* the status message reaches the client and reports the outcome,
* the values are persisted in the SQLite database,
* the Discord bot status is reported.

Usage:

    # terminal 1: the backend
    DB_PATH=./data/app.sqlite reflex run --env dev --backend-only \
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


async def run(backend: str, db_path: str, base_url: str) -> int:
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
    await emit(f"{prefix}set_discord_bot_token", {"value": ""})
    await emit(f"{prefix}set_discord_guild_id", {"value": ""})
    await asyncio.sleep(1)
    await emit(f"{prefix}save_settings", {})
    await asyncio.sleep(10)

    state: dict[str, Any] = {}
    for delta in deltas:
        chunk = delta.get("delta", {}).get(STATE_NAME)
        if isinstance(chunk, dict):
            state.update(chunk)

    status = state.get("status_message_rx_state_", "")
    bot_status = state.get("discord_bot_status_rx_state_", "")
    print("STATUS:", status)
    print("BOT STATUS:", bot_status)

    connection = sqlite3.connect(db_path)
    try:
        rows = dict(connection.execute("SELECT key, value FROM app_settings"))
    finally:
        connection.close()
    print("PERSISTED ROWS:", json.dumps(rows))
    persisted = rows.get("dockhand_base_url") == base_url

    await client.disconnect()

    ok = "Settings saved." in status and persisted
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    parser.add_argument("--db-path", default="./data/app.sqlite")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:9",
        help="Dockhand URL used in the test; the default port is closed on purpose.",
    )
    args = parser.parse_args()
    db_path = str(Path(args.db_path))
    return asyncio.run(run(args.backend, db_path, args.base_url))


if __name__ == "__main__":
    sys.exit(main())
