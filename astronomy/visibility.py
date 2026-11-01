"""Видимость: восходы/заходы, высота тел и текстовые оценки для выбранного места.

Горизонты для восхода/захода (геометрическая высота центра диска):
* Солнце: −0.8333° (рефракция 34′ + радиус диска 16′);
* Луна: −0.8333° (топоцентрическая параллакс-поправка учитывается Skyfield);
* планеты: −0.5667° (только рефракция, диск пренебрежимо мал).
Эти значения — стандартные условия (без учёта рельефа, местной погоды и высоты места).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from skyfield import almanac

from astronomy.context import AstroContext
from astronomy.time_utils import local_day_bounds_utc

HORIZON_SUN_MOON = -0.8333
HORIZON_PLANET = -0.5667


def rise_set_times(ctx: AstroContext, target, day: date,
                   horizon_deg: float) -> tuple[datetime | None, datetime | None]:
    """Первые восход и заход тела в течение местных суток (местное время) или None."""
    start_utc, end_utc = local_day_bounds_utc(day, ctx.tz)
    t0, t1 = ctx.t(start_utc), ctx.t(end_utc)
    f = almanac.risings_and_settings(ctx.eph, target, ctx.topos, horizon_deg)
    times, events = almanac.find_discrete(t0, t1, f)
    rise = set_ = None
    for i in range(len(times)):
        moment = ctx.local(times[i].utc_datetime())
        if events[i] == 1 and rise is None:
            rise = moment
        elif events[i] == 0 and set_ is None:
            set_ = moment
    return rise, set_


def altitude_azimuth(ctx: AstroContext, target, when_utc: datetime) -> tuple[float, float]:
    """Высота и азимут (градусы) с учётом стандартной рефракции."""
    t = ctx.t(when_utc)
    apparent = ctx.observer.at(t).observe(target).apparent()
    alt, az, _ = apparent.altaz(temperature_C=10.0, pressure_mbar=1010.0)
    return float(alt.degrees), float(az.degrees)


def sky_state(sun_alt: float, body_alt: float, elongation: float | None = None) -> str:
    """Короткая текстовая оценка видимости тела для главной страницы."""
    if body_alt <= 0:
        return "под горизонтом"
    if sun_alt > -0.833:
        return "над горизонтом, но днём (небо светлое)"
    if sun_alt > -6:
        return "над горизонтом, гражданские сумерки"
    if elongation is not None and elongation < 12:
        return "над горизонтом, но очень близко к Солнцу"
    if body_alt < 5:
        return "низко над горизонтом"
    return "видна на тёмном небе" if sun_alt < -12 else "видна в сумерках"


# ---------------------------------------------------------------------------
# Неподвижные объекты (звёзды, объекты глубокого космоса)
# ---------------------------------------------------------------------------
@dataclass
class FixedObjectInfo:
    altitude: float
    azimuth: float
    max_altitude: float            # высота в верхней кульминации (без рефракции)
    circumpolar: bool              # никогда не заходит
    never_rises: bool
    rise: datetime | None = None
    transit: datetime | None = None
    set: datetime | None = None


def fixed_object_info(ctx: AstroContext, ra_deg: float, dec_deg: float, when_utc: datetime,
                      with_times: bool = True) -> FixedObjectInfo:
    """Положение объекта с неподвижными координатами (J2000) для выбранного места.

    Собственные движения и прецессия до эпохи даты Skyfield учитывает сам; для объектов
    глубокого космоса собственное движение не задаётся (пренебрежимо мало).
    """
    from skyfield.api import Star
    star = Star(ra_hours=ra_deg / 15.0, dec_degrees=dec_deg)
    alt, az = altitude_azimuth(ctx, star, when_utc)
    lat = ctx.latitude
    max_alt = 90.0 - abs(lat - dec_deg)
    if lat >= 0:
        circumpolar, never = dec_deg >= 90.0 - lat, dec_deg <= lat - 90.0
    else:
        circumpolar, never = dec_deg <= -90.0 - lat, dec_deg >= 90.0 + lat
    info = FixedObjectInfo(alt, az, max_alt, circumpolar, never)
    if with_times:
        day = ctx.local(when_utc).date()
        start_utc, end_utc = local_day_bounds_utc(day, ctx.tz)
        t0, t1 = ctx.t(start_utc), ctx.t(end_utc)
        if not circumpolar and not never:
            info.rise, info.set = rise_set_times(ctx, star, day, HORIZON_PLANET)
        transit = almanac.meridian_transits(ctx.eph, star, ctx.topos)
        tt, ty = almanac.find_discrete(t0, t1, transit)
        for i in range(len(tt)):
            if ty[i] == 1:
                info.transit = ctx.local(tt[i].utc_datetime())
                break
    return info
