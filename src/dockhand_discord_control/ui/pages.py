"""Reflex pages for the Dockhand Discord Control web UI."""

from __future__ import annotations

import reflex as rx

from dockhand_discord_control.ui.state import AppState


def dashboard_page() -> rx.Component:
    """Read-only status snapshot of Dockhand environments and containers."""
    return rx.container(
        rx.heading("Dashboard"),
        rx.text(
            "Environments and containers managed by the Dockhand server.",
        ),
        rx.hstack(
            rx.button(
                "Refresh",
                on_click=AppState.refresh_status,  # type: ignore[arg-type]
                variant="solid",
            ),
            rx.text(AppState.status_message),
            spacing="4",
            align="center",
            margin_bottom="1rem",
        ),
        rx.text("Environments", weight="bold", margin_bottom="0.5rem"),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Environment"),
                    rx.table.column_header_cell("Status"),
                    rx.table.column_header_cell("Base URL"),
                )
            ),
            rx.table.body(
                rx.foreach(
                    AppState.environments,
                    lambda environment: rx.table.row(
                        rx.table.cell(environment.name),
                        rx.table.cell(environment.status),
                        rx.table.cell(environment.base_url),
                    ),
                )
            ),
        ),
        rx.text("Containers", weight="bold", margin_top="1rem", margin_bottom="0.5rem"),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Container"),
                    rx.table.column_header_cell("Image"),
                    rx.table.column_header_cell("Status"),
                    rx.table.column_header_cell("Environment"),
                )
            ),
            rx.table.body(
                rx.foreach(
                    AppState.containers,
                    lambda container: rx.table.row(
                        rx.table.cell(container.name),
                        rx.table.cell(container.image),
                        rx.table.cell(container.status),
                        rx.table.cell(container.environment_id),
                    ),
                )
            ),
        ),
        padding="1rem",
        max_width="640px",
    )


def settings_page() -> rx.Component:
    """Edit and save Dockhand and Discord settings."""
    return rx.container(
        rx.heading("Settings"),
        rx.text(
            "Configure the Dockhand server and Discord bot connection.",
        ),
        rx.vstack(
            rx.input(
                value=AppState.dockhand_base_url,
                placeholder="http://dockhand:8080",
                on_change=AppState.set_dockhand_base_url,  # type: ignore[arg-type]
                width="100%",
            ),
            rx.input(
                value=AppState.dockhand_api_token,
                type="password",
                placeholder="Dockhand API token",
                on_change=AppState.set_dockhand_api_token,  # type: ignore[arg-type]
                width="100%",
            ),
            rx.input(
                value=AppState.discord_bot_token,
                placeholder="Discord bot token",
                on_change=AppState.set_discord_bot_token,  # type: ignore[arg-type]
                width="100%",
            ),
            rx.input(
                value=AppState.discord_guild_id,
                placeholder="Discord guild ID (optional)",
                on_change=AppState.set_discord_guild_id,  # type: ignore[arg-type]
                width="100%",
            ),
            rx.button(
                "Save settings",
                on_click=AppState.save_settings,  # type: ignore[arg-type]
                variant="solid",
                width="100%",
            ),
            rx.text(AppState.status_message),
            spacing="1",
            width="100%",
            max_width="400px",
        ),
        padding="1rem",
        max_width="640px",
    )


def mappings_page() -> rx.Component:
    """Per-container visibility and channel mapping."""
    return rx.container(
        rx.heading("Mappings"),
        rx.text(
            "Map containers to Discord channels and toggle their visibility.",
        ),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Container"),
                    rx.table.column_header_cell("Channel ID"),
                    rx.table.column_header_cell("Enabled"),
                    rx.table.column_header_cell("Save"),
                )
            ),
            rx.table.body(
                rx.foreach(
                    AppState.mappings,
                    lambda mapping: rx.table.row(
                        rx.table.cell(mapping["container_name"]),
                        rx.input(
                            value=mapping["channel_id"],
                            on_change=lambda value: AppState.save_mapping(  # type: ignore[arg-type]
                                mapping["container_name"], value, mapping["enabled"]
                            ),
                            width="100%",
                        ),
                        rx.switch(
                            is_checked=mapping["enabled"],
                            on_change=lambda value: AppState.toggle_mapping(  # type: ignore[arg-type]
                                mapping["container_name"], mapping["channel_id"]
                            ),
                        ),
                        rx.button(
                            "Save",
                            on_click=lambda: AppState.save_mapping(  # type: ignore[arg-type]
                                mapping["container_name"],
                                mapping["channel_id"],
                                mapping["enabled"],
                            ),
                        ),
                    ),
                )
            ),
        ),
        rx.button(
            "Refresh mappings",
            on_click=AppState.load_mappings,  # type: ignore[arg-type]
            variant="outline",
            margin_top="1rem",
        ),
        rx.text(AppState.status_message),
        padding="1rem",
        max_width="640px",
    )
