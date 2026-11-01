"""Прецессия (IAU 1976, формулы Меуса гл. 21) — перевод координат даты в J2000.

Нутация (≈17″) не учитывается: для рисунка карты неба погрешность < 0.005°.
Используется только для линии горизонта и сторон света в экваториальном режиме карты.
"""
from __future__ import annotations

import numpy as np

ARCSEC = np.radians(1.0 / 3600.0)


def _rot_z(a: float) -> np.ndarray:
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])


def _rot_y(a: float) -> np.ndarray:
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0.0, -s], [0.0, 1.0, 0.0], [s, 0.0, c]])


def precession_matrix(t_centuries: float) -> np.ndarray:
    """Матрица J2000 -> средний экватор и равноденствие даты (T — юлианские столетия от J2000)."""
    t = t_centuries
    zeta = (2306.2181 * t + 0.30188 * t ** 2 + 0.017998 * t ** 3) * ARCSEC
    z = (2306.2181 * t + 1.09468 * t ** 2 + 0.018203 * t ** 3) * ARCSEC
    theta = (2004.3109 * t - 0.42665 * t ** 2 - 0.041833 * t ** 3) * ARCSEC
    return _rot_z(-z) @ _rot_y(theta) @ _rot_z(-zeta)


def _to_vec(ra_deg, dec_deg) -> np.ndarray:
    ra, dec = np.radians(np.asarray(ra_deg, float)), np.radians(np.asarray(dec_deg, float))
    return np.array([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)])


def _from_vec(v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    ra = np.degrees(np.arctan2(v[1], v[0])) % 360.0
    dec = np.degrees(np.arcsin(np.clip(v[2], -1.0, 1.0)))
    return ra, dec


def j2000_to_date(ra_deg, dec_deg, t_centuries: float):
    return _from_vec(precession_matrix(t_centuries) @ _to_vec(ra_deg, dec_deg))


def date_to_j2000(ra_deg, dec_deg, t_centuries: float):
    return _from_vec(precession_matrix(t_centuries).T @ _to_vec(ra_deg, dec_deg))


def horizon_to_equatorial_of_date(alt_deg, az_deg, latitude_deg: float, lst_deg: float):
    """Горизонтальные (высота, азимут от севера через восток) -> (RA, Dec) даты для местного звёздного времени."""
    alt, az, lat = np.radians(np.asarray(alt_deg, float)), np.radians(np.asarray(az_deg, float)), np.radians(latitude_deg)
    sin_dec = np.sin(alt) * np.sin(lat) + np.cos(alt) * np.cos(lat) * np.cos(az)
    dec = np.arcsin(np.clip(sin_dec, -1.0, 1.0))
    hour_angle = np.arctan2(-np.sin(az) * np.cos(alt),
                            np.sin(alt) * np.cos(lat) - np.cos(alt) * np.sin(lat) * np.cos(az))
    ra = (lst_deg - np.degrees(hour_angle)) % 360.0
    return ra, np.degrees(dec)
