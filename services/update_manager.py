"""Обновление данных: загрузка эфемерид, пересчёт событий, история обновлений."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import config
from api import jpl_api
from api.http_client import ApiError
from database.db_manager import DatabaseManager

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


class UpdateManager:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def ephemeris_status(self) -> dict:
        path = config.find_ephemeris_file()
        wanted = self.db.get_setting("ephemeris_file", "de440s.bsp")
        info = jpl_api.EPHEMERIS_INFO.get(path.name if path else wanted, {})
        return {
            "available": path is not None,
            "path": str(path) if path else "",
            "name": path.name if path else wanted,
            "years": info.get("years", ""),
            "size_mb": info.get("size_mb", 0),
            "last_update": self.db.last_successful_update("ephemeris"),
        }

    def download_ephemeris(self, progress: Callable[[int, int], None] | None = None) -> Path:
        filename = self.db.get_setting("ephemeris_file", "de440s.bsp")
        started = _now()
        try:
            path = jpl_api.download_ephemeris(filename, config.EPHEMERIS_DIR, progress)
        except (ApiError, ValueError, OSError) as exc:
            self.db.log_update("ephemeris", "error", str(exc), started)
            raise
        self.db.log_update("ephemeris", "ok", f"Загружен {filename}", started)
        return path

    def clear_event_cache(self) -> None:
        """Сбрасывает рассчитанные события; они пересчитаются при следующем открытии."""
        self.db.cache_delete_prefix("events:")
        self.db.log_update("events", "ok", "Кэш событий сброшен", _now())
