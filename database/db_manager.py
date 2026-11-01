"""SQLite: создание схемы, миграции и доступ к данным.

Версия схемы хранится в PRAGMA user_version. Чтобы изменить структуру, добавьте
новый SQL-скрипт в конец списка MIGRATIONS: при запуске он применится автоматически.
Каждое обращение открывает собственное соединение, поэтому менеджером можно
пользоваться из рабочих потоков.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from astronomy.time_utils import get_timezone, validate_coordinates
from database.models import Location

log = logging.getLogger(__name__)

SCHEMA_V1 = """
CREATE TABLE locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    elevation_m REAL NOT NULL DEFAULT 0,
    timezone TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE celestial_objects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    catalog_id TEXT NOT NULL UNIQUE,
    name TEXT,
    object_type TEXT,
    ra_deg REAL,
    dec_deg REAL,
    magnitude REAL,
    size_arcmin REAL,
    constellation TEXT,
    distance_ly REAL,
    description TEXT,
    image_url TEXT,
    source TEXT
);
CREATE TABLE astronomical_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    description TEXT,
    utc_time TEXT NOT NULL,
    params_json TEXT,
    source TEXT,
    computed_at TEXT NOT NULL,
    UNIQUE (category, body, utc_time)
);
CREATE INDEX idx_events_time ON astronomical_events (utc_time);
CREATE TABLE weather_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL,
    forecast_time TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    source TEXT,
    UNIQUE (location_id, forecast_time)
);
CREATE TABLE satellite_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    norad_id INTEGER NOT NULL UNIQUE,
    name TEXT NOT NULL,
    tle_line1 TEXT NOT NULL,
    tle_line2 TEXT NOT NULL,
    epoch TEXT,
    fetched_at TEXT NOT NULL,
    source TEXT
);
CREATE TABLE ephemeris_cache (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    source TEXT
);
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE update_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL
);
"""

# Новые миграции добавлять в конец списка.
MIGRATIONS: list[str] = [SCHEMA_V1]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


class DatabaseManager:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    # ---- соединение и миграции -------------------------------------------------
    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def schema_version(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("PRAGMA user_version").fetchone()[0])

    def migrate(self) -> None:
        with self.connect() as conn:
            current = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if current > len(MIGRATIONS):
                raise RuntimeError(
                    f"База данных создана более новой версией программы (схема {current})."
                )
            for index in range(current, len(MIGRATIONS)):
                log.info("Применяю миграцию БД %d", index + 1)
                conn.executescript(MIGRATIONS[index])
                conn.execute(f"PRAGMA user_version = {index + 1}")

    # ---- настройки -----------------------------------------------------------
    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return default

    def set_setting(self, key: str, value: Any) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value, ensure_ascii=False)),
            )

    # ---- места наблюдения ----------------------------------------------------
    @staticmethod
    def _row_to_location(row: sqlite3.Row) -> Location:
        return Location(
            id=row["id"], name=row["name"], latitude=row["latitude"],
            longitude=row["longitude"], elevation_m=row["elevation_m"],
            timezone=row["timezone"], is_default=bool(row["is_default"]),
        )

    def list_locations(self) -> list[Location]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM locations ORDER BY name COLLATE NOCASE").fetchall()
        return [self._row_to_location(r) for r in rows]

    def get_location(self, location_id: int) -> Location | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM locations WHERE id = ?", (location_id,)).fetchone()
        return self._row_to_location(row) if row else None

    def get_default_location(self) -> Location | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM locations ORDER BY is_default DESC, id LIMIT 1"
            ).fetchone()
        return self._row_to_location(row) if row else None

    @staticmethod
    def _validate_location(loc: Location) -> None:
        if not loc.name or not loc.name.strip():
            raise ValueError("Укажите название места.")
        validate_coordinates(loc.latitude, loc.longitude, loc.elevation_m)
        get_timezone(loc.timezone)

    def add_location(self, loc: Location) -> int:
        self._validate_location(loc)
        with self.connect() as conn:
            has_any = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0] > 0
            make_default = loc.is_default or not has_any
            if make_default:
                conn.execute("UPDATE locations SET is_default = 0")
            cur = conn.execute(
                "INSERT INTO locations (name, latitude, longitude, elevation_m, timezone, "
                "is_default, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (loc.name.strip(), loc.latitude, loc.longitude, loc.elevation_m,
                 loc.timezone, int(make_default), _now_iso()),
            )
            return int(cur.lastrowid)

    def update_location(self, loc: Location) -> None:
        if loc.id is None:
            raise ValueError("У места нет идентификатора.")
        self._validate_location(loc)
        with self.connect() as conn:
            conn.execute(
                "UPDATE locations SET name=?, latitude=?, longitude=?, elevation_m=?, timezone=? "
                "WHERE id=?",
                (loc.name.strip(), loc.latitude, loc.longitude, loc.elevation_m, loc.timezone, loc.id),
            )

    def set_default_location(self, location_id: int) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE locations SET is_default = 0")
            conn.execute("UPDATE locations SET is_default = 1 WHERE id = ?", (location_id,))

    def delete_location(self, location_id: int) -> None:
        with self.connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
            if total <= 1:
                raise ValueError("Нельзя удалить последнее место наблюдения.")
            was_default = conn.execute(
                "SELECT is_default FROM locations WHERE id = ?", (location_id,)
            ).fetchone()
            conn.execute("DELETE FROM locations WHERE id = ?", (location_id,))
            if was_default and was_default["is_default"]:
                conn.execute(
                    "UPDATE locations SET is_default = 1 WHERE id = (SELECT MIN(id) FROM locations)"
                )

    # ---- астрономические события ---------------------------------------------
    def replace_events(self, start_iso: str, end_iso: str, events: list[dict]) -> None:
        """Заменяет события диапазона [start_iso, end_iso) новым списком."""
        now = _now_iso()
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM astronomical_events WHERE utc_time >= ? AND utc_time < ?",
                (start_iso, end_iso),
            )
            conn.executemany(
                "INSERT OR REPLACE INTO astronomical_events "
                "(category, body, title, description, utc_time, params_json, source, computed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (e["category"], e.get("body", ""), e["title"], e.get("description", ""),
                     e["utc_time"], json.dumps(e.get("params", {}), ensure_ascii=False),
                     e.get("source", ""), now)
                    for e in events
                ],
            )

    def query_events(self, start_iso: str, end_iso: str,
                     categories: list[str] | None = None) -> list[dict]:
        sql = "SELECT * FROM astronomical_events WHERE utc_time >= ? AND utc_time < ?"
        args: list[Any] = [start_iso, end_iso]
        if categories is not None:
            if not categories:
                return []
            sql += f" AND category IN ({','.join('?' * len(categories))})"
            args.extend(categories)
        sql += " ORDER BY utc_time, id"
        with self.connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["params"] = json.loads(d.pop("params_json") or "{}")
            result.append(d)
        return result

    # ---- кэш -----------------------------------------------------------------
    def cache_get(self, key: str) -> tuple[Any, str] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value_json, computed_at FROM ephemeris_cache WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["value_json"]), row["computed_at"]

    def cache_set(self, key: str, value: Any, source: str = "") -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO ephemeris_cache (key, value_json, computed_at, source) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET "
                "value_json = excluded.value_json, computed_at = excluded.computed_at, "
                "source = excluded.source",
                (key, json.dumps(value, ensure_ascii=False), _now_iso(), source),
            )

    def cache_delete_prefix(self, prefix: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM ephemeris_cache WHERE key LIKE ?", (prefix + "%",))

    # ---- история обновлений --------------------------------------------------
    def log_update(self, source: str, status: str, message: str,
                   started_at: str, finished_at: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO update_history (source, status, message, started_at, finished_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (source, status, message, started_at, finished_at or _now_iso()),
            )

    def list_updates(self, limit: int = 50) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM update_history ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def last_successful_update(self, source: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT finished_at FROM update_history WHERE source = ? AND status = 'ok' "
                "ORDER BY id DESC LIMIT 1", (source,)
            ).fetchone()
        return row["finished_at"] if row else None

    # ---- погода ---------------------------------------------------------------
    def save_weather(self, location_id: int, rows: list[tuple[str, dict]], source: str) -> None:
        """Сохраняет почасовой прогноз: список (время UTC ISO, словарь значений)."""
        now = _now_iso()
        with self.connect() as conn:
            conn.executemany(
                "INSERT INTO weather_data (location_id, forecast_time, payload_json, fetched_at, source) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(location_id, forecast_time) DO UPDATE SET "
                "payload_json = excluded.payload_json, fetched_at = excluded.fetched_at, "
                "source = excluded.source",
                [(location_id, t, json.dumps(p), now, source) for t, p in rows])

    def load_weather(self, location_id: int, start_iso: str) -> tuple[list[tuple[str, dict]], str | None]:
        """Сохранённый прогноз начиная с start_iso и время последней загрузки."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT forecast_time, payload_json, fetched_at FROM weather_data "
                "WHERE location_id = ? AND forecast_time >= ? ORDER BY forecast_time",
                (location_id, start_iso)).fetchall()
        fetched = max((r["fetched_at"] for r in rows), default=None)
        return [(r["forecast_time"], json.loads(r["payload_json"])) for r in rows], fetched
