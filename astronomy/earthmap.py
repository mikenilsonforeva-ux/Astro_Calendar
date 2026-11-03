"""Геометрия карты Земли: терминатор, зона радиовидимости спутника, разбиение линий по линии перемены дат.

Чистая математика на numpy (без Skyfield и Qt), поэтому полностью проверяется тестами.
Земля считается шаром радиусом 6371 км — для карты в масштабе всего мира этого достаточно.
"""
from __future__ import annotations

import json

import numpy as np

EARTH_RADIUS_KM = 6371.0


def normalize_lon(lon):
    """Долгота в диапазон [-180, 180)."""
    return (np.asarray(lon, float) + 180.0) % 360.0 - 180.0


def terminator_latitudes(lons, sun_lat: float, sun_lon: float) -> np.ndarray:
    """Широта границы дня и ночи для каждой долготы при подсолнечной точке (sun_lat, sun_lon)."""
    dec = float(sun_lat)
    if abs(dec) < 0.01:
        dec = 0.01 if dec >= 0 else -0.01
    h = np.radians(np.asarray(lons, float) - sun_lon)
    return np.degrees(np.arctan(-np.cos(h) / np.tan(np.radians(dec))))


def night_polygon(sun_lat: float, sun_lon: float, n: int = 361) -> tuple[np.ndarray, np.ndarray]:
    """Многоугольник ночной стороны (lon, lat) в пределах карты -180…180: терминатор + полюс."""
    lons = np.linspace(-180.0, 180.0, n)
    lats = terminator_latitudes(lons, sun_lat, sun_lon)
    pole = -90.0 if sun_lat >= 0 else 90.0
    poly_lon = np.concatenate([lons, [180.0, -180.0]])
    poly_lat = np.concatenate([lats, [pole, pole]])
    return poly_lon, poly_lat


def footprint(lat: float, lon: float, height_km: float, n: int = 120) -> tuple[np.ndarray, np.ndarray]:
    """Окружность видимости спутника (горизонт при нулевой высоте над горизонтом наблюдателя)."""
    rho = np.arccos(EARTH_RADIUS_KM / (EARTH_RADIUS_KM + max(height_km, 1.0)))
    phi1, lam1 = np.radians(lat), np.radians(lon)
    bearing = np.linspace(0.0, 2.0 * np.pi, n)
    phi2 = np.arcsin(np.sin(phi1) * np.cos(rho) + np.cos(phi1) * np.sin(rho) * np.cos(bearing))
    lam2 = lam1 + np.arctan2(np.sin(bearing) * np.sin(rho) * np.cos(phi1),
                             np.cos(rho) - np.sin(phi1) * np.sin(phi2))
    return normalize_lon(np.degrees(lam2)), np.degrees(phi2)


def footprint_radius_km(height_km: float) -> float:
    """Расстояние по поверхности от подспутниковой точки до горизонта спутника."""
    return EARTH_RADIUS_KM * float(np.arccos(EARTH_RADIUS_KM / (EARTH_RADIUS_KM + max(height_km, 1.0))))


def split_dateline(lons, lats, jump: float = 180.0) -> list[tuple[np.ndarray, np.ndarray]]:
    """Режет ломаную там, где долгота «перескакивает» через линию перемены дат."""
    lons, lats = np.asarray(lons, float), np.asarray(lats, float)
    if len(lons) < 2:
        return []
    breaks = np.where(np.abs(np.diff(lons)) > jump)[0] + 1
    return [(a, b) for a, b in zip(np.split(lons, breaks), np.split(lats, breaks)) if len(a) >= 2]


def parse_geojson_lines(text: str) -> list[np.ndarray]:
    """Линии берегов из GeoJSON (Natural Earth): массивы (N, 2) = долгота, широта.

    Понимаются LineString, MultiLineString, Polygon, MultiPolygon и их коллекции;
    всё остальное игнорируется. Если подходящих линий нет — ValueError.
    """
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ValueError("Файл береговой линии не является корректным JSON.") from exc
    lines: list[np.ndarray] = []

    def add(coords) -> None:
        arr = np.asarray(coords, float)
        if arr.ndim == 2 and arr.shape[0] >= 2 and arr.shape[1] >= 2:
            lines.append(arr[:, :2])

    def walk(obj) -> None:
        if not isinstance(obj, dict):
            return
        kind = obj.get("type")
        if kind == "FeatureCollection":
            for f in obj.get("features", []):
                walk(f)
        elif kind == "Feature":
            walk(obj.get("geometry"))
        elif kind == "GeometryCollection":
            for g in obj.get("geometries", []):
                walk(g)
        elif kind == "LineString":
            add(obj.get("coordinates"))
        elif kind in ("MultiLineString", "Polygon"):
            for part in obj.get("coordinates", []):
                add(part)
        elif kind == "MultiPolygon":
            for poly in obj.get("coordinates", []):
                for ring in poly:
                    add(ring)

    walk(data)
    if not lines:
        raise ValueError("В файле нет линий береговой линии.")
    return lines
