"""SQLite-backed implementation of the :class:`ChannelMappingRepository` port."""

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
        """Insert or replace a channel mapping."""
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO channel_mappings
                    (container_name, channel_id, enabled)
                VALUES (?, ?, ?)
                """,
                (mapping.container_name, mapping.channel_id, int(mapping.enabled)),
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
