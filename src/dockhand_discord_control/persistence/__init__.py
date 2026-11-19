"""Persistence adapter: SQLite-backed repositories and configuration."""

from .config import Settings
from .database import get_connection, init_db
from .mapping_store import SqliteChannelMappingRepository
from .migrations import SCHEMA_VERSION, ensure_schema_version, get_schema_version
from .settings_store import SqliteSettingsRepository

__all__ = [
    "Settings",
    "SqliteChannelMappingRepository",
    "SqliteSettingsRepository",
    "ensure_schema_version",
    "get_connection",
    "get_schema_version",
    "init_db",
    "SCHEMA_VERSION",
]
