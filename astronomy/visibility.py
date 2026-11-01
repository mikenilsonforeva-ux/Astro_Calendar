"""Видимость: восходы/заходы, высота тел и текстовые оценки для выбранного места.

Горизонты для восхода/захода (геометрическая высота центра диска):
* Солнце: −0.8333° (рефракция 34′ + радиус диска 16′);
* Луна: −0.8333° (топоцентрическая параллакс-поправка учитывается Skyfield);
* планеты: −0.5667° (только рефракция, диск пренебрежимо мал).
Эти значения — стандартные условия (без учёта рельефа, местной погоды и высоты места).
"""
from __future__ import annotations

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
