"""Root Reflex app entry point.

Imports :func:`build_app` from the UI package and exposes ``app`` so
``reflex run`` works from the repo root.
"""

from dockhand_discord_control.ui.app import build_app

app = build_app()
