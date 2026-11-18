"""Reflex application wiring for the Dockhand Discord Control web UI.

:func:`build_app` creates the :class:`reflex.app.App`, registers the UI pages
and starts the Discord bridge as a best-effort background daemon thread.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import reflex as rx

from dockhand_discord_control.persistence import Settings, SqliteSettingsRepository

from .bridge import discord_bridge
from .pages import dashboard_page, mappings_page, settings_page
from .state import AppState

logger = logging.getLogger(__name__)


def build_app() -> rx.App:
    """Create the Reflex app and start the Discord bridge (best-effort).

    The bridge is started in a background daemon thread so the UI keeps
    responding even if Discord cannot be reached.
    """
    _configure_logging()
    app = rx.App(_state=AppState)
    app.add_page(
        dashboard_page,
        route="/",
        on_load=AppState.load_dashboard,  # type: ignore[arg-type]
    )
    app.add_page(
        settings_page,
        route="/settings",
        on_load=AppState.load_settings,  # type: ignore[arg-type]
    )
    app.add_page(
        mappings_page,
        route="/mappings",
        on_load=AppState.load_mappings_page,  # type: ignore[arg-type]
    )
    _trace_frontend_events(app)
    _log_runtime_info()
    _start_discord_bridge()
    return app


def _configure_logging() -> None:
    """Make the application logs visible in the console.

    Reflex does not configure the logging package, so without this the
    application logs (``logger.info``) are dropped: Python falls back to the
    ``lastResort`` handler, which only emits WARNING and above.  The save
    flow reports itself through INFO logs, so they have to be visible.
    """
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
    logging.getLogger("dockhand_discord_control").setLevel(logging.INFO)


def _trace_frontend_events(app: rx.App) -> None:
    """Log every frontend connection and event that reaches the backend.

    This distinguishes "the browser never talked to the backend" (wrong URL,
    stale frontend build) from "the event arrived but the handler failed".
    The Socket.IO handlers live on the event namespace, not on the app.
    """
    namespace = getattr(app, "_event_namespace", None)
    if namespace is None:  # pragma: no cover - depends on the Reflex version
        logger.warning("could not trace the frontend events: no event namespace")
        return
    original_connect = namespace.on_connect
    original_event = namespace.on_event

    async def on_connect(sid: str, environ: dict, auth: object = None) -> object:
        logger.info("frontend connected (sid=%s)", sid[:8])
        return await original_connect(sid, environ, auth)

    async def on_event(sid: str, data: object) -> object:
        name = ""
        if isinstance(data, dict):
            name = str(data.get("name", "")).rsplit(".", 1)[-1]
        logger.info("frontend event: %s", name or "<unknown>")
        return await original_event(sid, data)

    namespace.on_connect = on_connect  # type: ignore[method-assign]
    namespace.on_event = on_event  # type: ignore[method-assign]


def _log_runtime_info() -> None:
    """Log the runtime configuration, so an operator can see what is live.

    The database path and the commit the app was built from are the two facts
    that explain "the settings were not saved" (a wrong or unwritable database
    path) and "the fix does not work" (an older build).
    """
    db_path = Settings().db_path
    logger.info("database path: %s (exists: %s)", db_path, Path(db_path).exists())
    logger.info("commit: %s", _git_commit())
    logger.info(
        "open the UI on the frontend port: in dev mode the frontend dev server "
        "serves it (http://localhost:3000 by default) and the backend port alone "
        "does not serve the UI"
    )


def _git_commit() -> str:
    """Return the short commit the app runs from, or ``unknown``."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - no git
        return "unknown"
    commit = result.stdout.strip()
    return commit or "unknown"


def _start_discord_bridge() -> None:
    """Start the Discord bot in a background daemon thread, best-effort.

    Never raises: a missing token or any adapter failure is logged and the UI
    keeps running.  The bridge is the shared instance used by the settings
    page, so a token saved at runtime restarts the bot in place.
    """
    try:
        db_path = Settings().db_path
        settings_repo = SqliteSettingsRepository(db_path)
        base_url, api_token = settings_repo.get_dockhand_settings()
        token = settings_repo.get_discord_token()
        guild_id = settings_repo.get_discord_guild_id()
    except Exception as exc:  # pragma: no cover - infrastructure failure
        logger.warning("Discord bridge skipped: cannot read settings: %s", exc)
        return
    if not token:
        logger.info("Discord bridge skipped: no Discord bot token configured")
        return
    try:
        _started, message = discord_bridge.start(
            token=token,
            guild_id=guild_id,
            base_url=base_url,
            api_token=api_token,
            db_path=db_path,
        )
        logger.info(message)
    except Exception as exc:  # pragma: no cover - adapter failure
        logger.warning("Discord bridge failed to start: %s", exc)
