"""Кэш вычислений и внешних данных поверх таблицы ephemeris_cache."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from database.db_manager import DatabaseManager


class CacheManager:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def get(self, key: str, max_age: timedelta | None = None) -> Any | None:
        """Значение из кэша либо None, если записи нет или она старше max_age."""
        entry = self.db.cache_get(key)
        if entry is None:
            return None
        value, computed_at = entry
        if max_age is not None:
            computed = datetime.strptime(computed_at, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - computed > max_age:
                return None
        return value

    def updated_at(self, key: str) -> str | None:
        entry = self.db.cache_get(key)
        return entry[1] if entry else None

    def set(self, key: str, value: Any, source: str = "") -> None:
        self.db.cache_set(key, value, source)

    def clear_prefix(self, prefix: str) -> None:
        self.db.cache_delete_prefix(prefix)
