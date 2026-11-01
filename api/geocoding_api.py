"""Поиск координат населённого пункта через Open-Meteo Geocoding API.

Документация: https://open-meteo.com/en/docs/geocoding-api
"""
from __future__ import annotations

from dataclasses import dataclass

from api.http_client import ApiError, HttpClient

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


@dataclass
class GeoResult:
    name: str
    country: str
    admin: str
    latitude: float
    longitude: float
    elevation_m: float
    timezone: str

    @property
    def label(self) -> str:
        parts = [self.name]
        if self.admin and self.admin != self.name:
            parts.append(self.admin)
        if self.country:
            parts.append(self.country)
        return ", ".join(parts)


def parse_results(payload: dict) -> list[GeoResult]:
    """Разбирает ответ API, пропуская записи с некорректными данными."""
    results = []
    for item in payload.get("results") or []:
        try:
            lat = float(item["latitude"])
            lon = float(item["longitude"])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            results.append(GeoResult(
                name=str(item.get("name", "")),
                country=str(item.get("country", "")),
                admin=str(item.get("admin1", "")),
                latitude=lat,
                longitude=lon,
                elevation_m=float(item.get("elevation") or 0.0),
                timezone=str(item.get("timezone", "UTC")),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return results


def search_places(name: str, count: int = 8, language: str = "ru",
                  client: HttpClient | None = None) -> list[GeoResult]:
    name = name.strip()
    if len(name) < 2:
        raise ApiError("Введите не менее двух символов названия.")
    client = client or HttpClient()
    payload = client.get_json(
        GEOCODING_URL, {"name": name, "count": count, "language": language, "format": "json"}
    )
    if not isinstance(payload, dict):
        raise ApiError("Неожиданный формат ответа геокодера.")
    return parse_results(payload)
