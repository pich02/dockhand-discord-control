"""SQLite-backed implementation of the :class:`ChannelMappingRepository` port.

Invariant: one mapping per ``channel_id``. A Discord channel can be mapped to
at most one container. A container may have mappings from multiple channels.
"""

from __future__ import annotations

from typing import Final

from dockhand_discord_control.domain.models import ChannelMapping
from dockhand_discord_control.domain.ports import ChannelMappingRepository

from .database import get_connection, init_db

__all__ = ["SqliteChannelMappingRepository"]


class SqliteChannelMappingRepository(ChannelMappingRepository):
    """Reads/writes Discord channel <-> container mappings in SQLite."""

    def __init__(self, db_path: str = "./data/app.sqlite") -> None:
        self._db_path: Final = db_path
        self._conn = get_connection(db_path)
        init_db(self._conn)

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def get_mapping(self, channel_id: str) -> ChannelMapping | None:
        """Return the mapping for a channel, if any."""
        row = self._conn.execute(
            """
            SELECT container_name, channel_id, enabled
            FROM channel_mappings
            WHERE channel_id = ?
            """,
            (channel_id,),
        ).fetchone()
        return self._row_to_mapping(row) if row is not None else None

    def mappings_for_container(self, container_name: str) -> list[ChannelMapping]:
        """Return all mappings referencing a container name."""
        rows = self._conn.execute(
            """
            SELECT container_name, channel_id, enabled
            FROM channel_mappings
            WHERE container_name = ?
            ORDER BY channel_id
            """,
            (container_name,),
        ).fetchall()
        return [self._row_to_mapping(row) for row in rows]

    def add_mapping(self, mapping: ChannelMapping) -> None:
        """Insert or update a channel mapping.

        A channel can be mapped to at most one container. If the channel is
        already mapped to a different container, a :class:`ValueError` is
        raised.

        The read-check-write runs in an immediate write transaction so concurrent
        connections cannot silently bypass the conflict guard.
        """
        with self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            existing = self._conn.execute(
                "SELECT container_name FROM channel_mappings WHERE channel_id = ?",
                (mapping.channel_id,),
            ).fetchone()
            if (
                existing is not None
                and existing["container_name"] != mapping.container_name
            ):
                raise ValueError(
                    f"channel {mapping.channel_id!r} is already mapped to "
                    f"container {existing['container_name']!r}"
                )
            self._conn.execute(
                """
                INSERT INTO channel_mappings (channel_id, container_name, enabled)
                VALUES (?, ?, ?)
                ON CONFLICT(channel_id) DO UPDATE SET
                    container_name = excluded.container_name,
                    enabled = excluded.enabled
                """,
                (mapping.channel_id, mapping.container_name, int(mapping.enabled)),
            )

    def set_enabled(self, channel_id: str, enabled: bool) -> None:
        """Update the enabled flag of the mapping for *channel_id*."""
        with self._conn:
            self._conn.execute(
                "UPDATE channel_mappings SET enabled = ? WHERE channel_id = ?",
                (int(enabled), channel_id),
            )

    def remove_mapping(self, channel_id: str) -> None:
        """Delete the mapping for *channel_id*, if any."""
        with self._conn:
            self._conn.execute(
                "DELETE FROM channel_mappings WHERE channel_id = ?", (channel_id,)
            )

    @staticmethod
    def _row_to_mapping(row) -> ChannelMapping:
        return ChannelMapping(
            container_name=row["container_name"],
            channel_id=row["channel_id"],
            enabled=bool(row["enabled"]),
        )
