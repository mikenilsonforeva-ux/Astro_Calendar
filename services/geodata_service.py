"""Контуры материков для карты Земли: Natural Earth (общественное достояние), скачиваются один раз."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import config
from api.http_client import ApiError, HttpClient
from astronomy import earthmap
from database.db_manager import DatabaseManager

log = logging.getLogger(__name__)

URLS = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_coastline.geojson",
        "https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@master/geojson/ne_110m_coastline.geojson")
FILE_NAME = "ne_110m_coastline.geojson"
ATTRIBUTION = "Береговая линия: Natural Earth (общественное достояние), масштаб 1:110 млн."


class GeoDataService:
    def __init__(self, db: DatabaseManager | None = None, directory: Path | None = None):
        self.db = db
        self.directory = Path(directory) if directory else config.DATA_DIR / "geo"
        self._lines: list[np.ndarray] | None = None

    @property
    def path(self) -> Path:
        return self.directory / FILE_NAME

    def is_available(self) -> bool:
        return self.path.is_file()

    def load(self) -> list[np.ndarray]:
        if self._lines is None:
            if not self.is_available():
                raise FileNotFoundError("Контуры материков не загружены.")
            self._lines = earthmap.parse_geojson_lines(self.path.read_text(encoding="utf-8"))
        return self._lines

    def download(self, client: HttpClient | None = None) -> int:
        started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        client = client or HttpClient()
        last_error: Exception | None = None
        try:
            for url in URLS:
                try:
                    text = client.get_text(url)
                    lines = earthmap.parse_geojson_lines(text)
                    break
                except (ApiError, ValueError) as exc:
                    last_error = exc
                    log.warning("Береговая линия: %s недоступен: %s", url, exc)
            else:
                raise ApiError(f"Не удалось скачать контуры материков: {last_error}")
            self.directory.mkdir(parents=True, exist_ok=True)
            self.path.write_text(text, encoding="utf-8")
            self._lines = lines
        except (ApiError, OSError) as exc:
            if self.db:
                self.db.log_update("geodata", "error", str(exc), started)
            raise
        if self.db:
            self.db.log_update("geodata", "ok", f"Natural Earth: {len(lines)} линий", started)
        return len(lines)
