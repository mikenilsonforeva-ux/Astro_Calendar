"""Спутники: TLE из CelesTrak с кэшем в SQLite и офлайн-режимом."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from api import celestrak_api
from api.http_client import ApiError
from database.db_manager import DatabaseManager
from services.cache_manager import CacheManager

SOURCE = "CelesTrak"
MAX_AGE = timedelta(hours=12)       # CelesTrak просит не опрашивать чаще нескольких раз в сутки


@dataclass
class TleSet:
    group: str
    tles: list[celestrak_api.Tle]
    updated_at: str | None
    from_cache: bool
    warnings: list[str] = field(default_factory=list)


class SatelliteService:
    def __init__(self, db: DatabaseManager, client=None):
        self.db = db
        self.cache = CacheManager(db)
        self.client = client

    @staticmethod
    def _key(group: str) -> str:
        return f"tle:{group}"

    def cached(self, group: str) -> TleSet | None:
        value = self.cache.get(self._key(group))
        if not value:
            return None
        return TleSet(group, [celestrak_api.Tle(*row) for row in value], self.cache.updated_at(self._key(group)), True)

    def load(self, group: str, force: bool = False) -> TleSet:
        """Свежие TLE; при ошибке сети — последние сохранённые (с предупреждением)."""
        if not force:
            fresh = self.cache.get(self._key(group), MAX_AGE)
            if fresh:
                return TleSet(group, [celestrak_api.Tle(*r) for r in fresh],
                              self.cache.updated_at(self._key(group)), True)
        try:
            tles = celestrak_api.fetch_group(group, self.client)
        except ApiError as exc:
            old = self.cached(group)
            if old is None:
                raise
            old.warnings.append(f"Не удалось обновить данные ({exc}). Показаны сохранённые ранее.")
            return old
        self.cache.set(self._key(group), [[t.name, t.line1, t.line2] for t in tles], SOURCE)
        return TleSet(group, tles, self.cache.updated_at(self._key(group)), False)
