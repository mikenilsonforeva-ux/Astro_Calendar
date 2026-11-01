"""Математика карты неба: проекция и преобразования систем координат (без Skyfield и Qt).

Проекция — стереографическая (сохраняет форму созвездий). Экранные координаты: sx вправо,
sy вверх, при этом восток слева (карта «смотрим на небо»), как на обычных планисферах.
Для горизонтальной системы lon = азимут (от севера через восток), lat = высота;
для экваториальной lon = прямое восхождение, lat = склонение; все углы в градусах.
"""
from __future__ import annotations

import numpy as np

OBLIQUITY_J2000_DEG = 23.4392911
# Северный полюс Галактики и долгота северного полюса мира в галактической системе (J2000).
_NGP_RA, _NGP_DEC, _L_NCP = np.radians(192.85948), np.radians(27.12825), np.radians(122.93192)


def stereo_project(lon, lat, lon0: float, lat0: float):
    """(sx, sy, valid): проекция в «радиусах» стереографической плоскости (r = 2·tan(θ/2))."""
    lon, lat = np.radians(np.asarray(lon, float)), np.radians(np.asarray(lat, float))
    l0, p0 = np.radians(lon0), np.radians(lat0)
    dl = lon - l0
    cos_c = np.sin(p0) * np.sin(lat) + np.cos(p0) * np.cos(lat) * np.cos(dl)
    valid = cos_c > -0.999
    k = 2.0 / (1.0 + np.where(valid, cos_c, 0.0))
    x = k * np.cos(lat) * np.sin(dl)
    y = k * (np.cos(p0) * np.sin(lat) - np.sin(p0) * np.cos(lat) * np.cos(dl))
    return -x, y, valid


def stereo_unproject(sx: float, sy: float, lon0: float, lat0: float) -> tuple[float, float]:
    """Обратная проекция: точка экрана (в тех же единицах) -> (lon, lat) в градусах."""
    x, y = -sx, sy
    l0, p0 = np.radians(lon0), np.radians(lat0)
    r = float(np.hypot(x, y))
    if r < 1e-12:
        return lon0 % 360.0, lat0
    c = 2.0 * np.arctan(r / 2.0)
    lat = np.arcsin(np.clip(np.cos(c) * np.sin(p0) + y * np.sin(c) * np.cos(p0) / r, -1.0, 1.0))
    lon = l0 + np.arctan2(x * np.sin(c), r * np.cos(p0) * np.cos(c) - y * np.sin(p0) * np.sin(c))
    return float(np.degrees(lon) % 360.0), float(np.degrees(lat))


def angular_distance(lon1, lat1, lon2, lat2):
    """Угловое расстояние между точками (градусы), векторизовано."""
    a1, b1 = np.radians(np.asarray(lon1, float)), np.radians(np.asarray(lat1, float))
    a2, b2 = np.radians(np.asarray(lon2, float)), np.radians(np.asarray(lat2, float))
    value = np.sin(b1) * np.sin(b2) + np.cos(b1) * np.cos(b2) * np.cos(a1 - a2)
    return np.degrees(np.arccos(np.clip(value, -1.0, 1.0)))


def galactic_to_icrs(l_deg, b_deg) -> tuple[np.ndarray, np.ndarray]:
    """Галактические (l, b) -> экваториальные (RA, Dec) J2000, градусы."""
    l, b = np.radians(np.asarray(l_deg, float)), np.radians(np.asarray(b_deg, float))
    sin_dec = np.sin(b) * np.sin(_NGP_DEC) + np.cos(b) * np.cos(_NGP_DEC) * np.cos(_L_NCP - l)
    dec = np.arcsin(np.clip(sin_dec, -1.0, 1.0))
    y = np.cos(b) * np.sin(_L_NCP - l)
    x = np.sin(b) * np.cos(_NGP_DEC) - np.cos(b) * np.sin(_NGP_DEC) * np.cos(_L_NCP - l)
    ra = (_NGP_RA + np.arctan2(y, x)) % (2 * np.pi)
    return np.degrees(ra), np.degrees(dec)


def ecliptic_to_icrs(lon_deg, lat_deg) -> tuple[np.ndarray, np.ndarray]:
    """Эклиптические (λ, β) J2000 -> экваториальные (RA, Dec), градусы."""
    lam, beta = np.radians(np.asarray(lon_deg, float)), np.radians(np.asarray(lat_deg, float))
    eps = np.radians(OBLIQUITY_J2000_DEG)
    ra = np.arctan2(np.sin(lam) * np.cos(eps) - np.tan(beta) * np.sin(eps), np.cos(lam))
    dec = np.arcsin(np.clip(np.sin(beta) * np.cos(eps) + np.cos(beta) * np.sin(eps) * np.sin(lam), -1, 1))
    return np.degrees(ra) % 360.0, np.degrees(dec)


def galactic_plane_points(n: int = 181) -> tuple[np.ndarray, np.ndarray]:
    return galactic_to_icrs(np.linspace(0.0, 360.0, n), np.zeros(n))


def ecliptic_points(n: int = 181) -> tuple[np.ndarray, np.ndarray]:
    return ecliptic_to_icrs(np.linspace(0.0, 360.0, n), np.zeros(n))


def split_runs(valid: np.ndarray, sx: np.ndarray, sy: np.ndarray, max_jump: float) -> list[slice]:
    """Разбивает ломаную на непрерывные куски: по невидимым точкам и «прыжкам» через край проекции."""
    runs, start, n = [], None, len(valid)
    for i in range(n):
        ok = bool(valid[i])
        if ok and i > 0 and start is not None and np.hypot(sx[i] - sx[i - 1], sy[i] - sy[i - 1]) > max_jump:
            runs.append(slice(start, i))
            start = i
        elif ok and start is None:
            start = i
        elif not ok and start is not None:
            runs.append(slice(start, i))
            start = None
    if start is not None:
        runs.append(slice(start, n))
    return [r for r in runs if r.stop - r.start >= 2]


def star_limit_magnitude(fov_deg: float) -> float:
    """Предельная звёздная величина отображаемых звёзд в зависимости от поля зрения."""
    t = (170.0 - max(15.0, min(170.0, fov_deg))) / (170.0 - 15.0)
    return 3.8 + 3.0 * t     # 3.8ᵐ при полном небе … 6.8ᵐ при сильном увеличении


def star_radius_px(mag: np.ndarray) -> np.ndarray:
    return np.maximum(0.7, 0.6 + (6.8 - np.asarray(mag, float)) * 0.55)
