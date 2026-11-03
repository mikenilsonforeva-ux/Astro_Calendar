"""Пролёты искусственных спутников над местом наблюдения (SGP4 через Skyfield).

Видимость глазом: спутник освещён Солнцем, а у наблюдателя Солнце ниже −6° (гражданские
сумерки и темнее). Пролёт в тени Земли или при светлом небе обозначается как «не виден».
Яркость не оценивается — в данных TLE её нет.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

from astronomy.context import AstroContext
from astronomy.coordinates import compass_point
from astronomy.time_utils import ensure_utc

MIN_ALTITUDE = 10.0
TLE_STALE_DAYS = 10
SUN_LIMIT = -6.0


@dataclass
class SatPass:
    name: str
    rise: datetime
    rise_az: float
    culminate: datetime
    max_alt: float
    max_az: float
    set: datetime
    set_az: float
    sunlit_at_max: bool
    sun_alt_at_max: float

    @property
    def visible(self) -> bool:
        return self.sunlit_at_max and self.sun_alt_at_max < SUN_LIMIT

    @property
    def duration_s(self) -> float:
        return (self.set - self.rise).total_seconds()

    @property
    def visibility_text(self) -> str:
        if self.visible:
            return "виден"
        if not self.sunlit_at_max:
            return "в тени Земли"
        return "светлое небо"


def make_satellite(ctx: AstroContext, name: str, line1: str, line2: str):
    from skyfield.api import EarthSatellite
    return EarthSatellite(line1, line2, name, ctx.ts)


def tle_age_days(sat, when_utc: datetime) -> float:
    """Возраст элементов орбиты на заданный момент (суток); чем больше, тем хуже точность."""
    epoch = sat.epoch.utc_datetime()
    return (ensure_utc(when_utc) - epoch).total_seconds() / 86400.0


def compute_passes(ctx: AstroContext, sat, start_utc: datetime, days: float = 5.0,
                   min_altitude: float = MIN_ALTITUDE) -> list[SatPass]:
    """Пролёты с высотой не ниже min_altitude, отсортированные по времени."""
    start_utc = ensure_utc(start_utc)
    t0, t1 = ctx.t(start_utc), ctx.t(start_utc + timedelta(days=days))
    times, events = sat.find_events(ctx.topos, t0, t1, altitude_degrees=min_altitude)
    passes: list[SatPass] = []
    current: dict[int, object] = {}
    for t, ev in zip(times, events):
        current[int(ev)] = t
        if int(ev) == 2 and {0, 1} <= set(current):
            passes.append(_build_pass(ctx, sat, current[0], current[1], current[2]))
            current = {}
        elif int(ev) == 0:
            current = {0: t}
    return passes


def _altaz(ctx: AstroContext, sat, t) -> tuple[float, float]:
    alt, az, _ = (sat - ctx.topos).at(t).altaz()
    return float(alt.degrees), float(az.degrees)


def _build_pass(ctx: AstroContext, sat, t_rise, t_max, t_set) -> SatPass:
    _, rise_az = _altaz(ctx, sat, t_rise)
    max_alt, max_az = _altaz(ctx, sat, t_max)
    _, set_az = _altaz(ctx, sat, t_set)
    sunlit = bool(sat.at(t_max).is_sunlit(ctx.eph))
    sun_alt, _, _ = ctx.observer.at(t_max).observe(ctx.eph["sun"]).apparent().altaz()
    return SatPass(sat.name, ctx.dt(t_rise), rise_az, ctx.dt(t_max), max_alt, max_az, ctx.dt(t_set), set_az,
                   sunlit, float(sun_alt.degrees))


def current_position(ctx: AstroContext, sat, when_utc: datetime) -> dict:
    """Положение спутника сейчас: подспутниковая точка, высота орбиты, азимут/высота у наблюдателя."""
    from skyfield.api import wgs84
    t = ctx.t(when_utc)
    geo = sat.at(t)
    sub = wgs84.subpoint(geo)
    alt, az = _altaz(ctx, sat, t)
    speed = float(np.linalg.norm(geo.velocity.km_per_s))
    return {"latitude": float(sub.latitude.degrees), "longitude": float(sub.longitude.degrees),
            "height_km": float(sub.elevation.km), "alt": alt, "az": az, "speed_kms": speed,
            "sunlit": bool(geo.is_sunlit(ctx.eph))}


def ground_track(ctx: AstroContext, sat, when_utc: datetime, back_min: float = 45.0,
                 forward_min: float = 135.0, step_s: float = 30.0) -> dict:
    """Наземная трасса: подспутниковые точки за прошлые back_min и будущие forward_min минут."""
    from skyfield.api import wgs84
    now = ctx.t(when_utc)
    offsets = np.arange(-back_min * 60.0, forward_min * 60.0 + step_s, step_s) / 86400.0
    times = ctx.ts.tt_jd(now.tt + offsets)
    sub = wgs84.subpoint(sat.at(times))
    lat, lon = np.asarray(sub.latitude.degrees), np.asarray(sub.longitude.degrees)
    past = offsets <= 0
    return {"past_lat": lat[past], "past_lon": lon[past], "future_lat": lat[~past],
            "future_lon": lon[~past]}


def subsolar_point(ctx: AstroContext, when_utc: datetime) -> tuple[float, float]:
    """Подсолнечная точка (широта, долгота): над ней Солнце в зените."""
    t = ctx.t(when_utc)
    ra, dec, _ = ctx.eph["earth"].at(t).observe(ctx.eph["sun"]).apparent().radec(epoch="date")
    lon = (float(ra.hours) - float(t.gast)) * 15.0
    return float(dec.degrees), float((lon + 180.0) % 360.0 - 180.0)


def describe_pass(p: SatPass, tz) -> list[str]:
    fmt = "%d.%m %H:%M:%S"
    return [p.name, p.rise.astimezone(tz).strftime(fmt), f"{p.rise_az:.0f}° {compass_point(p.rise_az)}",
            p.culminate.astimezone(tz).strftime("%H:%M:%S"), f"{p.max_alt:.0f}°",
            f"{p.max_az:.0f}° {compass_point(p.max_az)}", p.set.astimezone(tz).strftime("%H:%M:%S"),
            f"{p.set_az:.0f}° {compass_point(p.set_az)}", f"{p.duration_s / 60:.1f} мин", p.visibility_text]
