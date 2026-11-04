"""Снимок неба для карты: положения всех рисуемых объектов на заданный момент.

Тяжёлые вычисления (Skyfield) выполняются здесь один раз при смене момента или места;
масштабирование и перемещение карты только пересчитывают проекцию готовых массивов.

Координаты звёзд и объектов — ICRS (J2000), собственные движения Hipparcos учитываются.
Высота и азимут — геометрические, без рефракции. Планеты, Солнце и Луна — видимые положения.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from astronomy import skymap
from astronomy.constellations_ru import constellation_ru
from astronomy.context import AstroContext
from astronomy.precession import date_to_j2000, horizon_to_equatorial_of_date
from astronomy.stars import StarCatalog, asterism_segments, match_named_stars

PLANET_COLORS = {"mercury": "#b0b0b0", "venus": "#fff3c0", "mars": "#ff7050", "jupiter": "#ffd9a0",
                 "saturn": "#e8d090", "uranus": "#a0e8f0", "neptune": "#7090ff"}


@dataclass
class SkyBody:
    key: str
    name: str
    kind: str                # "sun" | "moon" | "planet"
    ra: float                # J2000, градусы
    dec: float
    alt: float
    az: float
    mag: float | None
    detail: str = ""
    phase_angle: float | None = None   # для Луны: 0° новолуние … 180° полнолуние


@dataclass
class Curve:
    ra: np.ndarray
    dec: np.ndarray
    alt: np.ndarray
    az: np.ndarray


@dataclass
class SkySnapshot:
    when_utc: datetime
    latitude: float
    longitude: float
    sun_alt: float
    zenith_ra: float
    zenith_dec: float
    star_ra: np.ndarray
    star_dec: np.ndarray
    star_mag: np.ndarray
    star_alt: np.ndarray
    star_az: np.ndarray
    star_hip: np.ndarray
    star_names: dict[str, int]
    segments: list[tuple[str, int, int]]
    const_labels: list[tuple[str, float, float, float, float]]   # название, ra, dec, alt, az
    milky_way: Curve
    ecliptic: Curve
    horizon_ra: np.ndarray
    horizon_dec: np.ndarray
    cardinals: list[tuple[str, float, float]]                   # подпись, ra, dec  (в J2000)
    bodies: list[SkyBody] = field(default_factory=list)
    deep_sky: list[dict] = field(default_factory=list)          # + alt, az
    star_parallax: np.ndarray | None = None
    star_pm_ra: np.ndarray | None = None
    star_pm_dec: np.ndarray | None = None


def _altaz(ctx: AstroContext, t, ra_deg, dec_deg, cat: StarCatalog | None = None):
    from skyfield.api import Star
    ra_deg, dec_deg = np.atleast_1d(ra_deg).astype(float), np.atleast_1d(dec_deg).astype(float)
    if cat is not None:
        star = Star(ra_hours=ra_deg / 15.0, dec_degrees=dec_deg,
                    ra_mas_per_year=cat.pm_ra, dec_mas_per_year=cat.pm_dec,
                    parallax_mas=np.maximum(cat.parallax, 0.1))
    else:
        star = Star(ra_hours=ra_deg / 15.0, dec_degrees=dec_deg)
    alt, az, _ = ctx.observer.at(t).observe(star).apparent().altaz()
    return np.asarray(alt.degrees), np.asarray(az.degrees)


def _curve(ctx, t, ra, dec) -> Curve:
    alt, az = _altaz(ctx, t, ra, dec)
    return Curve(np.asarray(ra), np.asarray(dec), alt, az)


def _bodies(ctx: AstroContext, t, when_utc: datetime) -> list[SkyBody]:
    from astronomy import moon, planets
    from skyfield import almanac
    result = []
    at = ctx.observer.at(t)

    def position(body):
        app = at.observe(body).apparent()
        alt, az, _ = app.altaz()
        ra, dec, _ = app.radec()
        return float(ra.hours) * 15.0, float(dec.degrees), float(alt.degrees), float(az.degrees)

    ra, dec, alt, az = position(ctx.eph["sun"])
    result.append(SkyBody("sun", "Солнце", "sun", ra, dec, alt, az, -26.7, "звезда, спектральный класс G2V"))
    ra, dec, alt, az = position(ctx.eph["moon"])
    phase = float(almanac.moon_phase(ctx.eph, t).degrees)
    illum = moon.illumination_from_phase(phase)
    result.append(SkyBody("moon", "Луна", "moon", ra, dec, alt, az, None,
                          f"{moon.phase_name(phase)}, освещено {illum * 100:.0f}%", phase_angle=phase))
    for info in planets.all_info(ctx, when_utc, with_rise_set=False):
        eph_name = planets.PLANET_BY_KEY[info.key][2]
        ra, dec, alt, az = position(ctx.eph[eph_name])
        result.append(SkyBody(info.key, info.name, "planet", ra, dec, alt, az, info.magnitude,
                              f"{info.constellation}, {info.distance_au:.2f} а. е., "
                              f"элонгация {info.elongation:.0f}°"))
    return result


def build_snapshot(ctx: AstroContext, when_utc: datetime, cat: StarCatalog,
                   constellation_centers: dict[str, tuple[float, float]] | None = None,
                   deep_sky: list[dict] | None = None) -> SkySnapshot:
    t = ctx.t(when_utc)
    star_alt, star_az = _altaz(ctx, t, cat.ra, cat.dec, cat)
    names = match_named_stars(cat)
    bodies = _bodies(ctx, t, when_utc)

    centuries = float((t.tt - 2451545.0) / 36525.0)
    lst = (float(t.gast) * 15.0 + ctx.longitude) % 360.0
    zenith_ra, zenith_dec = date_to_j2000(lst, ctx.latitude, centuries)

    az_line = np.linspace(0.0, 360.0, 181)
    h_ra, h_dec = horizon_to_equatorial_of_date(np.zeros_like(az_line), az_line, ctx.latitude, lst)
    h_ra, h_dec = date_to_j2000(h_ra, h_dec, centuries)
    cardinals = []
    for label, az in (("С", 0.0), ("В", 90.0), ("Ю", 180.0), ("З", 270.0)):
        r, d = horizon_to_equatorial_of_date(0.0, az, ctx.latitude, lst)
        r, d = date_to_j2000(r, d, centuries)
        cardinals.append((label, float(r), float(d)))

    labels = []
    if constellation_centers:
        abbrs = list(constellation_centers)
        ras = np.array([constellation_centers[a][0] for a in abbrs])
        decs = np.array([constellation_centers[a][1] for a in abbrs])
        alts, azs = _altaz(ctx, t, ras, decs)
        labels = [(constellation_ru(a), float(r), float(d), float(al), float(az))
                  for a, r, d, al, az in zip(abbrs, ras, decs, alts, azs)]

    objects = []
    if deep_sky:
        ras = np.array([o["ra_deg"] for o in deep_sky])
        decs = np.array([o["dec_deg"] for o in deep_sky])
        alts, azs = _altaz(ctx, t, ras, decs)
        for o, al, az in zip(deep_sky, alts, azs):
            objects.append({**o, "alt": float(al), "az": float(az)})

    return SkySnapshot(
        when_utc=when_utc, latitude=ctx.latitude, longitude=ctx.longitude,
        sun_alt=next(b.alt for b in bodies if b.key == "sun"),
        zenith_ra=float(zenith_ra), zenith_dec=float(zenith_dec),
        star_ra=cat.ra, star_dec=cat.dec, star_mag=cat.mag, star_alt=star_alt, star_az=star_az,
        star_hip=cat.hip, star_names=names, segments=asterism_segments(names),
        const_labels=labels,
        milky_way=_curve(ctx, t, *skymap.galactic_plane_points(181)),
        ecliptic=_curve(ctx, t, *skymap.ecliptic_points(181)),
        horizon_ra=np.asarray(h_ra), horizon_dec=np.asarray(h_dec), cardinals=cardinals,
        bodies=bodies, deep_sky=objects,
        star_parallax=cat.parallax, star_pm_ra=cat.pm_ra, star_pm_dec=cat.pm_dec)
