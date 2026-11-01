"""NOAA SWPC: геомагнитный индекс Kp и солнечные вспышки (https://services.swpc.noaa.gov/).

Форматы JSON у SWPC менялись (список списков с заголовком ↔ список объектов), поэтому разбор
терпим к обоим вариантам и пропускает некорректные записи. Если структура не распознана —
бросается ApiError, а приложение показывает сообщение вместо неверных данных.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from api.http_client import ApiError, HttpClient

BASE = "https://services.swpc.noaa.gov"
KP_HISTORY_URL = BASE + "/products/noaa-planetary-k-index.json"
KP_FORECAST_URL = BASE + "/products/noaa-planetary-k-index-forecast.json"
FLARES_URL = BASE + "/json/goes/primary/xray-flares-7-day.json"


@dataclass
class KpPoint:
    time_utc: datetime
    kp: float
    observed: bool = True
    noaa_scale: str = ""


@dataclass
class Flare:
    begin_utc: datetime | None
    max_utc: datetime | None
    max_class: str


def _records(payload) -> list[dict]:
    """Приводит оба варианта формата к списку словарей."""
    if not isinstance(payload, list):
        raise ApiError("Неожиданный формат данных NOAA SWPC.")
    if payload and isinstance(payload[0], list):
        header = [str(h) for h in payload[0]]
        return [dict(zip(header, row)) for row in payload[1:] if isinstance(row, list)]
    return [r for r in payload if isinstance(r, dict)]


def parse_time(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace("T", " ").rstrip("Z")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def parse_kp(payload) -> list[KpPoint]:
    points = []
    for rec in _records(payload):
        moment = parse_time(rec.get("time_tag"))
        kp = _float(rec.get("Kp", rec.get("kp")))
        if moment is None or kp is None or not 0.0 <= kp <= 9.0:
            continue
        observed = str(rec.get("observed", "observed")).lower() in ("observed", "true", "1")
        points.append(KpPoint(moment, kp, observed, str(rec.get("noaa_scale") or "")))
    if not points:
        raise ApiError("NOAA SWPC не вернул данных Kp в ожидаемом формате.")
    return sorted(points, key=lambda p: p.time_utc)


def parse_flares(payload) -> list[Flare]:
    flares = []
    for rec in _records(payload):
        cls = str(rec.get("max_class") or "").strip()
        if not cls:
            continue
        flares.append(Flare(parse_time(rec.get("begin_time")), parse_time(rec.get("max_time")), cls))
    return sorted(flares, key=lambda f: f.max_utc or datetime.min.replace(tzinfo=timezone.utc))


def fetch_kp_history(client: HttpClient | None = None) -> list[KpPoint]:
    return parse_kp((client or HttpClient()).get_json(KP_HISTORY_URL))


def fetch_kp_forecast(client: HttpClient | None = None) -> list[KpPoint]:
    return parse_kp((client or HttpClient()).get_json(KP_FORECAST_URL))


def fetch_flares(client: HttpClient | None = None) -> list[Flare]:
    return parse_flares((client or HttpClient()).get_json(FLARES_URL))
