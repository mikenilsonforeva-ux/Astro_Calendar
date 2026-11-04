"""Единый HTTP-клиент: тайм-ауты, повторные попытки, понятные ошибки.

Все сетевые запросы приложения должны идти через этот модуль (см. ТЗ, раздел 16).
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable

import requests

log = logging.getLogger(__name__)

USER_AGENT = "AstronomicalCalendar/0.1 (desktop app; contact: see README)"
RETRY_STATUSES = {429, 500, 502, 503, 504}


class ApiError(Exception):
    """Ошибка получения внешних данных (сеть, формат ответа, статус HTTP)."""


class HttpClient:
    def __init__(self, connect_timeout: float = 5.0, read_timeout: float = 20.0,
                 retries: int = 3, backoff: float = 1.0,
                 session: requests.Session | None = None):
        self.timeout = (connect_timeout, read_timeout)
        self.retries = max(1, retries)
        self.backoff = backoff
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def _request(self, url: str, params: dict | None, stream: bool = False,
                 timeout: tuple[float, float] | None = None,
                 headers: dict | None = None) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=timeout or self.timeout,
                                        stream=stream, headers=headers)
                if resp.status_code in RETRY_STATUSES:
                    last_error = ApiError(f"Сервер ответил кодом {resp.status_code}")
                elif resp.status_code >= 400:
                    raise ApiError(f"Сервер {url} ответил кодом {resp.status_code}")
                else:
                    return resp
            except ApiError:
                raise
            except requests.RequestException as exc:
                last_error = exc
            log.warning("Запрос %s: попытка %d/%d не удалась: %s", url, attempt, self.retries, last_error)
            if attempt < self.retries:
                time.sleep(self.backoff * attempt)
        raise ApiError(
            f"Не удалось получить данные с {url}. Проверьте подключение к интернету. ({last_error})"
        )

    def get_json(self, url: str, params: dict | None = None) -> Any:
        resp = self._request(url, params)
        try:
            return resp.json()
        except ValueError as exc:
            raise ApiError(f"Сервер {url} вернул не JSON.") from exc

    def get_text(self, url: str, params: dict | None = None,
                 timeout: tuple[float, float] | None = None) -> str:
        resp = self._request(url, params, timeout=timeout)
        return resp.text

    def download(self, url: str, dest: Path, progress: Callable[[int, int], None] | None = None,
                 min_size: int = 1) -> Path:
        """Скачивает файл во временный *.part и переименовывает после проверки размера."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_suffix(dest.suffix + ".part")
        # Без сжатия: Content-Length тогда равен размеру файла (при gzip он описывает сжатые данные).
        resp = self._request(url, None, stream=True, timeout=(self.timeout[0], 60),
                             headers={"Accept-Encoding": "identity"})
        total = int(resp.headers.get("Content-Length") or 0)
        if resp.headers.get("Content-Encoding", "identity").lower() not in ("", "identity"):
            total = 0       # сервер всё равно сжал ответ — размер сверить нельзя
        done = 0
        try:
            with open(part, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=256 * 1024):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
        except requests.RequestException as exc:
            part.unlink(missing_ok=True)
            raise ApiError(f"Загрузка прервана: {exc}") from exc
        if done < min_size or (total and done != total):
            part.unlink(missing_ok=True)
            raise ApiError("Файл скачан не полностью. Повторите попытку.")
        part.replace(dest)
        return dest
