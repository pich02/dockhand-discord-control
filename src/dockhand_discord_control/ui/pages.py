"""Reflex pages for the Dockhand Discord Control web UI."""

from __future__ import annotations

import reflex as rx

from dockhand_discord_control.ui.state import AppState


def _navbar() -> rx.Component:
    return rx.hstack(
        rx.link("Dashboard", href="/"),
        rx.link("Settings", href="/settings"),
        rx.link("Mappings", href="/mappings"),
        spacing="4",
    )


def dashboard_page() -> rx.Component:
    """Read-only status snapshot of Dockhand environments and containers."""
    return rx.container(
        _navbar(),
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
        rx.text(AppState.discord_bot_status, margin_bottom="1rem"),
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
        _navbar(),
        rx.heading("Settings"),
        rx.text(
            "Configure the Dockhand server and Discord bot connection.",
        ),
        rx.vstack(
            rx.input(
                value=AppState.dockhand_base_url,
                placeholder="http://dockhand:8080",
                on_change=AppState.set_dockhand_base_url,  # type: ignore[arg-type]
                debounce_timeout=0,
                width="100%",
            ),
            rx.input(
                value=AppState.dockhand_api_token,
                type="password",
                placeholder="Dockhand API token",
                on_change=AppState.set_dockhand_api_token,  # type: ignore[arg-type]
                debounce_timeout=0,
                width="100%",
            ),
            rx.input(
                value=AppState.discord_bot_token,
                placeholder="Discord bot token",
                on_change=AppState.set_discord_bot_token,  # type: ignore[arg-type]
                debounce_timeout=0,
                width="100%",
            ),
            rx.input(
                value=AppState.discord_guild_id,
                placeholder="Discord guild ID (optional)",
                on_change=AppState.set_discord_guild_id,  # type: ignore[arg-type]
                debounce_timeout=0,
                width="100%",
            ),
            rx.button(
                "Save settings",
                type="button",
                on_click=AppState.save_settings,  # type: ignore[arg-type]
                variant="solid",
                width="100%",
            ),
            rx.text(AppState.status_message),
            rx.text(AppState.discord_bot_status),
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
        _navbar(),
        rx.heading("Mappings"),
        rx.text(
            "Map containers to Discord channels and toggle their visibility.",
        ),
        rx.box(
            rx.text("Add mapping", weight="bold", margin_bottom="0.5rem"),
            rx.cond(
                AppState.container_names.length() > 0,  # type: ignore[attr-defined]
                rx.vstack(
                    rx.select(
                        AppState.container_names,
                        value=AppState.new_mapping_container_name,
                        on_change=AppState.set_new_mapping_container_name,  # type: ignore[arg-type]
                        placeholder="Select container",
                        width="100%",
                    ),
                    rx.input(
                        value=AppState.new_mapping_channel_id,
                        placeholder="Discord channel ID",
                        on_change=AppState.set_new_mapping_channel_id,  # type: ignore[arg-type]
                        debounce_timeout=0,
                        width="100%",
                    ),
                    rx.hstack(
                        rx.switch(
                            is_checked=AppState.new_mapping_enabled,
                            on_change=AppState.set_new_mapping_enabled,  # type: ignore[arg-type]
                        ),
                        rx.text("Enabled"),
                        spacing="2",
                        align="center",
                    ),
                    rx.button(
                        "Add mapping",
                        on_click=AppState.add_mapping,  # type: ignore[arg-type]
                        variant="solid",
                    ),
                    spacing="2",
                    align="stretch",
                    width="100%",
                ),
                rx.text(
                    "No known containers. Configure Dockhand settings and refresh "
                    "the dashboard to load containers before adding mappings.",
                ),
            ),
            padding="1rem",
            border="1px solid #ddd",
            border_radius="8px",
            margin_bottom="1rem",
            width="100%",
        ),
        rx.cond(
            AppState.mappings.length() > 0,  # type: ignore[attr-defined]
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
                        lambda mapping, idx: rx.table.row(
                            rx.table.cell(mapping["container_name"]),
                            rx.table.cell(
                                rx.input(
                                    value=mapping["channel_id"],
                                    on_change=lambda value: (
                                        AppState.update_mapping_channel_id(  # type: ignore[arg-type]
                                            idx, value
                                        )
                                    ),
                                    width="100%",
                                )
                            ),
                            rx.table.cell(
                                rx.switch(
                                    checked=mapping["enabled"],
                                    on_change=lambda value: (
                                        AppState.update_mapping_enabled(  # type: ignore[arg-type]
                                            idx, value
                                        )
                                    ),
                                )
                            ),
                            rx.table.cell(
                                rx.button(
                                    "Save",
                                    on_click=lambda: AppState.save_mapping(  # type: ignore[arg-type]
                                        mapping["container_name"],
                                        mapping["channel_id"],
                                        mapping["enabled"],
                                        mapping["original_channel_id"],
                                    ),
                                )
                            ),
                        ),
                    )
                ),
            ),
            rx.text(
                "No mappings yet. Use the form above to add a channel mapping "
                "for a known container.",
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
