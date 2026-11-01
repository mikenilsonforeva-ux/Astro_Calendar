"""Солнце: положение, восход/заход, сумерки, уравнение времени, равноденствия."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from skyfield import almanac

from astronomy.context import EPHEMERIS_SOURCE, AstroContext
from astronomy.event_types import CAT_SEASON, AstroEvent
from astronomy.time_utils import local_day_bounds_utc

AU_KM = 149_597_870.7


@dataclass
class SunPosition:
    when_utc: datetime
    altitude: float          # градусы, с рефракцией
    azimuth: float           # градусы от севера через восток
    ra_hours: float          # прямое восхождение (эпоха даты)
    dec_deg: float           # склонение (эпоха даты)
    distance_au: float
    equation_of_time_min: float

    @property
    def distance_km(self) -> float:
        return self.distance_au * AU_KM


@dataclass
class SunDay:
    day: date
    sunrise: datetime | None = None
    sunset: datetime | None = None
    solar_noon: datetime | None = None
    day_length: timedelta | None = None
    night_length: timedelta | None = None
    civil_dawn: datetime | None = None
    civil_dusk: datetime | None = None
    nautical_dawn: datetime | None = None
    nautical_dusk: datetime | None = None
    astronomical_dawn: datetime | None = None
    astronomical_dusk: datetime | None = None
    polar_state: str = ""    # "polar_day", "polar_night" или ""
    notes: list[str] = field(default_factory=list)


def equation_of_time_minutes(t, ra_hours_of_date: float) -> float:
    """Уравнение времени = истинное солнечное время − среднее, в минутах.

    Не зависит от долготы: ΔT_eq = GAST − RA_apparent(of date) − UT + 12 ч (по модулю 24 ч).
    """
    utc = t.utc
    ut_hours = utc.hour + utc.minute / 60.0 + utc.second / 3600.0
    value_h = ((float(t.gast) - ra_hours_of_date - ut_hours + 12.0 + 12.0) % 24.0) - 12.0
    return value_h * 60.0


def position(ctx: AstroContext, when_utc: datetime) -> SunPosition:
    t = ctx.t(when_utc)
    apparent = ctx.observer.at(t).observe(ctx.eph["sun"]).apparent()
    alt, az, _ = apparent.altaz(temperature_C=10.0, pressure_mbar=1010.0)
    ra, dec, dist = apparent.radec(epoch="date")
    return SunPosition(
        when_utc=when_utc,
        altitude=float(alt.degrees),
        azimuth=float(az.degrees),
        ra_hours=float(ra.hours),
        dec_deg=float(dec.degrees),
        distance_au=float(dist.au),
        equation_of_time_min=equation_of_time_minutes(t, float(ra.hours)),
    )


def day_info(ctx: AstroContext, day: date) -> SunDay:
    """Восход, закат, полдень, сумерки и длительность дня для местной даты."""
    start_utc, end_utc = local_day_bounds_utc(day, ctx.tz)
    t0, t1 = ctx.t(start_utc), ctx.t(end_utc)
    result = SunDay(day=day)

    # Уровни: 0 ночь, 1 астрономические, 2 навигационные, 3 гражданские сумерки, 4 день.
    f = almanac.dark_twilight_day(ctx.eph, ctx.topos)
    previous = int(f(t0))
    times, levels = almanac.find_discrete(t0, t1, f)
    dawn: dict[int, datetime] = {}
    dusk: dict[int, datetime] = {}
    for i in range(len(times)):
        moment = ctx.local(times[i].utc_datetime())
        level = int(levels[i])
        if level > previous:
            for lvl in range(previous + 1, level + 1):
                dawn.setdefault(lvl, moment)
        else:
            for lvl in range(previous, level, -1):
                dusk.setdefault(lvl, moment)
        previous = level
    result.astronomical_dawn, result.nautical_dawn = dawn.get(1), dawn.get(2)
    result.civil_dawn, result.sunrise = dawn.get(3), dawn.get(4)
    result.sunset, result.civil_dusk = dusk.get(4), dusk.get(3)
    result.nautical_dusk, result.astronomical_dusk = dusk.get(2), dusk.get(1)

    # Солнечный полдень — верхняя кульминация.
    transit = almanac.meridian_transits(ctx.eph, ctx.eph["sun"], ctx.topos)
    tt, ty = almanac.find_discrete(t0, t1, transit)
    for i in range(len(tt)):
        if ty[i] == 1:
            result.solar_noon = ctx.local(tt[i].utc_datetime())
            break

    # Длительность дня и ночи, полярный день/ночь.
    if result.sunrise and result.sunset:
        length = result.sunset - result.sunrise
        if length.total_seconds() < 0:
            length += timedelta(days=1)
        result.day_length = length
        result.night_length = timedelta(days=1) - length
    elif not result.sunrise and not result.sunset:
        reference = result.solar_noon or (start_utc + (end_utc - start_utc) / 2)
        if position(ctx, reference).altitude > -0.833:
            result.polar_state = "polar_day"
            result.day_length, result.night_length = timedelta(hours=24), timedelta(0)
            result.notes.append("Полярный день: Солнце не заходит.")
        else:
            result.polar_state = "polar_night"
            result.day_length, result.night_length = timedelta(0), timedelta(hours=24)
            result.notes.append("Полярная ночь: Солнце не восходит.")
    else:
        result.notes.append("В эти сутки происходит только восход или только заход Солнца.")
    return result


def altitude_series(ctx: AstroContext, day: date, step_minutes: int = 10
                    ) -> tuple[list[datetime], list[float]]:
    """Высота Солнца (геометрическая, без рефракции) в течение местных суток."""
    start_utc, end_utc = local_day_bounds_utc(day, ctx.tz)
    steps = int((end_utc - start_utc).total_seconds() // (step_minutes * 60)) + 1
    moments = [start_utc + timedelta(minutes=step_minutes * i) for i in range(steps)]
    times = ctx.ts.from_datetimes(moments)
    alt, _, _ = ctx.observer.at(times).observe(ctx.eph["sun"]).apparent().altaz()
    return [ctx.local(m) for m in moments], [float(a) for a in alt.degrees]


SEASON_TITLES = [
    ("Мартовское равноденствие", "Солнце пересекает небесный экватор с юга на север (долгота Солнца 0°)."),
    ("Июньское солнцестояние", "Наибольшее склонение Солнца к северу (долгота Солнца 90°)."),
    ("Сентябрьское равноденствие", "Солнце пересекает небесный экватор с севера на юг (долгота Солнца 180°)."),
    ("Декабрьское солнцестояние", "Наибольшее склонение Солнца к югу (долгота Солнца 270°)."),
]


def season_events(ctx: AstroContext, t0, t1) -> list[AstroEvent]:
    times, kinds = almanac.find_discrete(t0, t1, almanac.seasons(ctx.eph))
    events = []
    for i in range(len(times)):
        title, description = SEASON_TITLES[int(kinds[i])]
        events.append(AstroEvent(
            category=CAT_SEASON, body="sun", title=title, description=description,
            utc_time=times[i].utc_datetime(), params={"kind": int(kinds[i])},
            source=EPHEMERIS_SOURCE,
        ))
    return events
