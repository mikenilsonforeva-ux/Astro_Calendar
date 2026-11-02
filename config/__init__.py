"""Пути, каталоги данных и загрузка настроек по умолчанию.

При запуске из исходников все данные лежат в папке проекта.
В собранном EXE (PyInstaller) пользовательские данные (БД, логи, эфемериды)
хранятся в %APPDATA%\\AstronomicalCalendar, потому что папка с программой
может быть недоступна для записи.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_NAME = "AstronomicalCalendar"
APP_TITLE = "Астрономический календарь"
APP_VERSION = "0.5.0"

FROZEN = bool(getattr(sys, "frozen", False))
SOURCE_DIR = Path(__file__).resolve().parent.parent
# Папка с ресурсами, упакованными в программу (для EXE это sys._MEIPASS).
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", SOURCE_DIR))


def _data_dir() -> Path:
    if FROZEN:
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home()
        return base / APP_NAME
    return SOURCE_DIR


DATA_DIR = _data_dir()
DB_PATH = DATA_DIR / "data" / "astro.db"
LOG_DIR = DATA_DIR / "logs"
EPHEMERIS_DIR = DATA_DIR / "resources" / "ephemeris" if FROZEN else SOURCE_DIR / "resources" / "ephemeris"
BUNDLED_EPHEMERIS_DIR = BUNDLE_DIR / "resources" / "ephemeris"
DEFAULT_SETTINGS_FILE = BUNDLE_DIR / "config" / "settings.json"

# Файлы эфемерид в порядке предпочтения.
EPHEMERIS_FILES = ("de440s.bsp", "de421.bsp")


def ensure_dirs() -> None:
    for d in (DB_PATH.parent, LOG_DIR, EPHEMERIS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_default_settings() -> dict:
    with open(DEFAULT_SETTINGS_FILE, "r", encoding="utf-8") as fh:
        return json.load(fh)


def find_ephemeris_file() -> Path | None:
    """Возвращает путь к первому найденному файлу эфемерид либо None."""
    for directory in (EPHEMERIS_DIR, BUNDLED_EPHEMERIS_DIR):
        for name in EPHEMERIS_FILES:
            candidate = directory / name
            if candidate.is_file() and candidate.stat().st_size > 1_000_000:
                return candidate
    return None
