"""Луна: положение, фаза, возраст, восход/заход, фазы и апсиды."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from skyfield import almanac
from skyfield.searchlib import find_maxima, find_minima

from astronomy.context import EPHEMERIS_SOURCE, AstroContext
from astronomy.event_types import CAT_APSIDES, CAT_MOON_PHASE, AstroEvent
from astronomy.visibility import HORIZON_SUN_MOON, rise_set_times

MOON_RADIUS_KM = 1737.4

PHASE_TITLES = [
    ("Новолуние", "Луна между Землёй и Солнцем, обращена к Земле неосвещённой стороной."),
    ("Первая четверть", "Освещена правая (в северном полушарии) половина диска."),
    ("Полнолуние", "Луна напротив Солнца, диск освещён полностью."),
    ("Последняя четверть", "Освещена левая (в северном полушарии) половина диска."),
]


@dataclass
class MoonInfo:
    when_utc: datetime
    phase_angle: float          # 0° новолуние, 90° первая четверть, 180° полнолуние
    illumination: float         # доля освещённого диска 0..1
    age_days: float
    phase_name: str
    altitude: float
    azimuth: float
    ra_hours: float
    dec_deg: float
    distance_km: float
    angular_diameter_arcmin: float
    rise: datetime | None = None
    set: datetime | None = None


def phase_name(phase_angle: float) -> str:
    names = ["Новолуние", "Растущий серп", "Первая четверть", "Растущая Луна",
             "Полнолуние", "Убывающая Луна", "Последняя четверть", "Убывающий серп"]
    return names[int(((phase_angle % 360.0) + 22.5) // 45.0) % 8]


def illumination_from_phase(phase_angle_deg: float) -> float:
    return (1.0 - math.cos(math.radians(phase_angle_deg))) / 2.0


def phase_angle_at(ctx: AstroContext, when_utc: datetime) -> float:
    return float(almanac.moon_phase(ctx.eph, ctx.t(when_utc)).degrees)


def illumination_at(ctx: AstroContext, when_utc: datetime) -> float:
    return illumination_from_phase(phase_angle_at(ctx, when_utc))


def age_days(ctx: AstroContext, when_utc: datetime) -> float:
    """Возраст Луны — время, прошедшее с последнего новолуния."""
    t = ctx.t(when_utc)
    t0 = ctx.t(when_utc - timedelta(days=31))
    times, kinds = almanac.find_discrete(t0, t, almanac.moon_phases(ctx.eph))
    new_moons = [times[i] for i in range(len(kinds)) if kinds[i] == 0]
    if not new_moons:
        return float("nan")
    return float(t.tt - new_moons[-1].tt)


def info(ctx: AstroContext, when_utc: datetime, with_rise_set: bool = True) -> MoonInfo:
    t = ctx.t(when_utc)
    moon = ctx.eph["moon"]
    apparent = ctx.observer.at(t).observe(moon).apparent()
    alt, az, _ = apparent.altaz(temperature_C=10.0, pressure_mbar=1010.0)
    ra, dec, dist = apparent.radec(epoch="date")
    distance_km = float(dist.km)
    angular = 2.0 * math.degrees(math.asin(MOON_RADIUS_KM / distance_km)) * 60.0
    phase = float(almanac.moon_phase(ctx.eph, t).degrees)
    result = MoonInfo(
        when_utc=when_utc, phase_angle=phase, illumination=illumination_from_phase(phase),
        age_days=age_days(ctx, when_utc), phase_name=phase_name(phase),
        altitude=float(alt.degrees), azimuth=float(az.degrees),
        ra_hours=float(ra.hours), dec_deg=float(dec.degrees),
        distance_km=distance_km, angular_diameter_arcmin=angular,
    )
    if with_rise_set:
        result.rise, result.set = rise_set_times(
            ctx, moon, ctx.local(when_utc).date(), HORIZON_SUN_MOON)
    return result


def phase_events(ctx: AstroContext, t0, t1) -> list[AstroEvent]:
    times, kinds = almanac.find_discrete(t0, t1, almanac.moon_phases(ctx.eph))
    events = []
    for i in range(len(times)):
        title, description = PHASE_TITLES[int(kinds[i])]
        moment = times[i].utc_datetime()
        events.append(AstroEvent(
            category=CAT_MOON_PHASE, body="moon", title=title, description=description,
            utc_time=moment, params={"kind": int(kinds[i])}, source=EPHEMERIS_SOURCE,
        ))
    return events


def _distance_function(ctx: AstroContext):
    earth, moon = ctx.eph["earth"], ctx.eph["moon"]

    def distance_km(t):
        return earth.at(t).observe(moon).distance().km

    distance_km.step_days = 1.0
    return distance_km


def apsis_events(ctx: AstroContext, t0, t1) -> list[AstroEvent]:
    """Перигей и апогей Луны (по геоцентрическому расстоянию между центрами)."""
    f = _distance_function(ctx)
    events = []
    for finder, title, word in ((find_minima, "Перигей Луны", "ближайшая"),
                                (find_maxima, "Апогей Луны", "наибольшая")):
        times, values = finder(t0, t1, f)
        for i in range(len(times)):
            km = float(values[i])
            events.append(AstroEvent(
                category=CAT_APSIDES, body="moon", title=title,
                description=f"Расстояние до Луны {word} за месяц: {km:,.0f} км.".replace(",", " "),
                utc_time=times[i].utc_datetime(),
                params={"distance_km": round(km), "kind": "perigee" if word == "ближайшая" else "apogee"},
                source=EPHEMERIS_SOURCE,
            ))
    return events


def month_phase_table(ctx: AstroContext, year: int, month: int) -> list[AstroEvent]:
    first = date(year, month, 1)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    t0 = ctx.ts.utc(first.year, first.month, first.day)
    t1 = ctx.ts.utc(nxt.year, nxt.month, nxt.day)
    return phase_events(ctx, t0, t1)
