"""Общее состояние приложения: БД, текущее место, контекст расчётов."""
from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, Signal

import config
from astronomy.context import AstroContext, EphemerisUnavailable
from database.db_manager import DatabaseManager
from database.models import Location
from services.event_manager import EventManager
from services.update_manager import UpdateManager

log = logging.getLogger(__name__)


class AppState(QObject):
    location_changed = Signal()
    theme_changed = Signal(str)
    data_updated = Signal()      # скачаны эфемериды / сброшен кэш

    def __init__(self, db: DatabaseManager):
        super().__init__()
        self.db = db
        self.events = EventManager(db)
        self.updates = UpdateManager(db)
        self._ctx: AstroContext | None = None
        self._ctx_key: tuple | None = None
        self._lock = threading.Lock()
        self._ensure_default_location()

    def _ensure_default_location(self) -> None:
        if self.db.get_default_location() is None:
            d = config.load_default_settings()["default_location"]
            self.db.add_location(Location(
                name=d["name"], latitude=d["latitude"], longitude=d["longitude"],
                elevation_m=d["elevation_m"], timezone=d["timezone"], is_default=True))

    @property
    def location(self) -> Location:
        loc = self.db.get_default_location()
        assert loc is not None
        return loc

    @property
    def theme(self) -> str:
        return self.db.get_setting("theme", config.load_default_settings()["theme"])

    def context(self) -> AstroContext:
        """Контекст расчётов для текущего места. Можно вызывать из рабочего потока.

        Бросает EphemerisUnavailable, если файл эфемерид ещё не скачан.
        """
        path = config.find_ephemeris_file()
        if path is None:
            raise EphemerisUnavailable(
                "Файл эфемерид не найден. Откройте раздел «Обновление данных» и скачайте его "
                "(нужен интернет, один раз). После этого программа работает без интернета.")
        loc = self.location
        key = (loc.id, loc.latitude, loc.longitude, loc.elevation_m, loc.timezone, str(path))
        with self._lock:
            if self._ctx is None or self._ctx_key != key:
                self._ctx = AstroContext.create(
                    loc.latitude, loc.longitude, loc.elevation_m, loc.timezone,
                    path, place_name=loc.name)
                self._ctx_key = key
            return self._ctx

    def notify_location_changed(self) -> None:
        self.location_changed.emit()

    def notify_data_updated(self) -> None:
        self._ctx = None
        self._ctx_key = None
        self.data_updated.emit()
