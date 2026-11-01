"""Планеты: положение, физические параметры и события (противостояния, соединения, элонгации).

Модель и ограничения:
* координаты — геоцентрические «apparent» из эфемерид JPL (Skyfield);
* видимая звёздная величина — приближённые формулы Astronomical Almanac
  (зависят от расстояний и фазового угла). Для Сатурна не учтено влияние колец,
  поэтому ошибка может достигать ~1 звёздной величины; для остальных — порядка 0.1–0.3;
* соединения и противостояния определяются по эклиптической долготе относительно Солнца;
* ретроградные периоды — по знаку скорости изменения эклиптической долготы (моменты стояний);
  сближения планет между собой и с Луной пока не реализованы.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from skyfield.searchlib import find_discrete, find_maxima

from astronomy.constellations_ru import constellation_ru
from astronomy.context import EPHEMERIS_SOURCE, AstroContext
from astronomy.event_types import CAT_PLANET, AstroEvent
from astronomy.visibility import HORIZON_PLANET, rise_set_times, sky_state

# key, русское название, имя в эфемеридах, экваториальный радиус (км), внутренняя ли планета
PLANETS = [
    ("mercury", "Меркурий", "mercury barycenter", 2439.7, True),
    ("venus", "Венера", "venus barycenter", 6051.8, True),
    ("mars", "Марс", "mars barycenter", 3396.2, False),
    ("jupiter", "Юпитер", "jupiter barycenter", 71492.0, False),
    ("saturn", "Сатурн", "saturn barycenter", 60268.0, False),
    ("uranus", "Уран", "uranus barycenter", 25559.0, False),
    ("neptune", "Нептун", "neptune barycenter", 24764.0, False),
]
PLANET_BY_KEY = {p[0]: p for p in PLANETS}
AU_KM = 149_597_870.7


@dataclass
class PlanetInfo:
    key: str
    name: str
    ra_hours: float
    dec_deg: float
    ecl_lon: float
    ecl_lat: float
    altitude: float
    azimuth: float
    distance_au: float
    magnitude: float
    angular_diameter_arcsec: float
    phase_angle: float | None
    illumination: float | None
    elongation: float
    elongation_side: str
    constellation: str
    sun_distance_au: float
    state: str = ""
    rise: datetime | None = None
    set: datetime | None = None


def apparent_magnitude(key: str, r_au: float, d_au: float, phase_angle_deg: float) -> float:
    """Приближённая видимая звёздная величина (формулы Astronomical Almanac)."""
    i = phase_angle_deg
    log_term = 5.0 * math.log10(r_au * d_au)
    if key == "mercury":
        return -0.42 + log_term + 0.0380 * i - 0.000273 * i ** 2 + 0.000002 * i ** 3
    if key == "venus":
        return -4.40 + log_term + 0.0009 * i + 0.000239 * i ** 2 - 0.00000065 * i ** 3
    if key == "mars":
        return -1.52 + log_term + 0.016 * i
    if key == "jupiter":
        return -9.40 + log_term + 0.005 * i
    if key == "saturn":
        return -8.88 + log_term + 0.044 * i   # без поправки на кольца
    if key == "uranus":
        return -7.19 + log_term
    if key == "neptune":
        return -6.87 + log_term
    raise KeyError(key)


def _phase_geometry(ctx: AstroContext, body, t) -> tuple[float, float, float]:
    """(фазовый угол в градусах, расстояние Солнце–планета, расстояние Земля–планета в а. е.)."""
    p = body.at(t).position.au
    e = ctx.eph["earth"].at(t).position.au
    s = ctx.eph["sun"].at(t).position.au
    to_sun, to_earth = s - p, e - p
    r = float(np.linalg.norm(to_sun))
    d = float(np.linalg.norm(to_earth))
    cos_i = float(np.dot(to_sun, to_earth) / (r * d))
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_i)))), r, d


def info(ctx: AstroContext, key: str, when_utc: datetime, with_rise_set: bool = True) -> PlanetInfo:
    _, name, eph_name, radius_km, _ = PLANET_BY_KEY[key]
    body = ctx.eph[eph_name]
    t = ctx.t(when_utc)
    at = ctx.observer.at(t)
    apparent = at.observe(body).apparent()
    alt, az, dist = apparent.altaz(temperature_C=10.0, pressure_mbar=1010.0)
    ra, dec, _ = apparent.radec(epoch="date")
    ecl_lat, ecl_lon, _ = apparent.ecliptic_latlon()
    sun_app = at.observe(ctx.eph["sun"]).apparent()
    sun_alt = float(sun_app.altaz(temperature_C=10.0, pressure_mbar=1010.0)[0].degrees)
    elong = float(sun_app.separation_from(apparent).degrees)
    sun_lat, sun_lon, _ = sun_app.ecliptic_latlon()
    side = "восточная (вечерняя)" if (float(ecl_lon.degrees) - float(sun_lon.degrees)) % 360.0 < 180.0 \
        else "западная (утренняя)"
    phase, r_au, d_au = _phase_geometry(ctx, body, t)
    illumination = (1.0 + math.cos(math.radians(phase))) / 2.0
    distance_km = float(dist.au) * AU_KM
    result = PlanetInfo(
        key=key, name=name,
        ra_hours=float(ra.hours), dec_deg=float(dec.degrees),
        ecl_lon=float(ecl_lon.degrees), ecl_lat=float(ecl_lat.degrees),
        altitude=float(alt.degrees), azimuth=float(az.degrees),
        distance_au=float(dist.au),
        magnitude=apparent_magnitude(key, r_au, d_au, phase),
        angular_diameter_arcsec=2.0 * math.degrees(math.asin(radius_km / distance_km)) * 3600.0,
        phase_angle=phase,
        illumination=illumination if key in ("mercury", "venus", "mars") else None,
        elongation=elong, elongation_side=side,
        constellation=constellation_ru(ctx.constellation_at(apparent)),
        sun_distance_au=r_au,
        state=sky_state(sun_alt, float(alt.degrees), elong),
    )
    if with_rise_set:
        result.rise, result.set = rise_set_times(
            ctx, body, ctx.local(when_utc).date(), HORIZON_PLANET)
    return result


def all_info(ctx: AstroContext, when_utc: datetime, with_rise_set: bool = True) -> list[PlanetInfo]:
    return [info(ctx, p[0], when_utc, with_rise_set) for p in PLANETS]


# ---------------------------------------------------------------------------
# События
# ---------------------------------------------------------------------------
def _ecliptic_longitudes(ctx: AstroContext, body, t):
    at = ctx.eph["earth"].at(t)
    _, sun_lon, _ = at.observe(ctx.eph["sun"]).apparent().ecliptic_latlon()
    _, body_lon, _ = at.observe(body).apparent().ecliptic_latlon()
    return sun_lon.degrees, body_lon.degrees


def _side_function(ctx: AstroContext, body, step_days: float):
    """0, пока планета в 0°–180° к востоку от Солнца; 1 — в 180°–360°.

    Переход 0→1 — противостояние (долгота планеты − долгота Солнца = 180°),
    переход 1→0 — соединение с Солнцем (разность 0°/360°).
    """
    def f(t):
        sun_lon, body_lon = _ecliptic_longitudes(ctx, body, t)
        return (((body_lon - sun_lon) % 360.0) // 180.0).astype(int)

    f.step_days = step_days
    return f


def _elongation_function(ctx: AstroContext, body, step_days: float):
    earth, sun = ctx.eph["earth"], ctx.eph["sun"]

    def f(t):
        at = earth.at(t)
        return at.observe(sun).apparent().separation_from(at.observe(body).apparent()).degrees

    f.step_days = step_days
    return f


def _retrograde_function(ctx: AstroContext, body):
    """1, пока эклиптическая долгота планеты убывает (ретроградное движение), иначе 0."""
    earth = ctx.eph["earth"]

    def longitude(t):
        _, lon, _ = earth.at(t).observe(body).apparent().ecliptic_latlon()
        return lon.degrees

    def f(t):
        diff = longitude(ctx.ts.tt_jd(t.tt + 0.5)) - longitude(ctx.ts.tt_jd(t.tt - 0.5))
        return (((diff + 180.0) % 360.0 - 180.0) < 0).astype(int)

    f.step_days = 2.0
    return f


@dataclass
class MotionSeries:
    key: str
    name: str
    times: list                 # aware datetime (UTC)
    longitude: np.ndarray       # эклиптическая долгота, непрерывная (без скачков 360°→0), градусы
    elongation: np.ndarray      # угловое расстояние от Солнца, градусы
    retrograde: np.ndarray      # bool: движение попятное


def motion_series(ctx: AstroContext, key: str, start_utc: datetime, days: int,
                  step_days: float = 2.0) -> MotionSeries:
    """Ряд положений планеты для графиков движения (геоцентрические видимые координаты)."""
    from datetime import timedelta
    _, name, eph_name, _, _ = PLANET_BY_KEY[key]
    body = ctx.eph[eph_name]
    count = int(days / step_days) + 1
    moments = [start_utc + timedelta(days=step_days * i) for i in range(count)]
    times = ctx.ts.from_datetimes(moments)
    at = ctx.eph["earth"].at(times)
    app = at.observe(body).apparent()
    _, lon, _ = app.ecliptic_latlon()
    elong = at.observe(ctx.eph["sun"]).apparent().separation_from(app).degrees
    unwrapped = np.degrees(np.unwrap(np.radians(np.asarray(lon.degrees))))
    retro = np.concatenate([np.diff(unwrapped) < 0, [False]])
    if len(retro) > 1:
        retro[-1] = retro[-2]
    return MotionSeries(key, name, moments, unwrapped, np.asarray(elong), retro)


def planet_events(ctx: AstroContext, t0, t1) -> list[AstroEvent]:
    events: list[AstroEvent] = []
    for key, name, eph_name, _, inner in PLANETS:
        body = ctx.eph[eph_name]
        step = 5.0 if inner else (15.0 if key in ("mars", "jupiter", "saturn") else 30.0)
        times, sides = find_discrete(t0, t1, _side_function(ctx, body, step))
        for i in range(len(times)):
            t = times[i]
            moment = t.utc_datetime()
            if int(sides[i]) == 1 and not inner:
                _, r_au, d_au = _phase_geometry(ctx, body, t)
                events.append(AstroEvent(
                    category=CAT_PLANET, body=key, title=f"Противостояние: {name}",
                    description=(f"{name} находится в противоположной от Солнца части неба и видна "
                                 f"почти всю ночь. Расстояние до Земли {d_au:.3f} а. е., "
                                 f"блеск около {apparent_magnitude(key, r_au, d_au, 0.0):+.1f}ᵐ."),
                    utc_time=moment, params={"kind": "opposition", "distance_au": round(d_au, 4)},
                    source=EPHEMERIS_SOURCE))
            elif int(sides[i]) == 0:
                _, _, d_au = _phase_geometry(ctx, body, t)
                sun_dist = float(ctx.eph["earth"].at(t).observe(ctx.eph["sun"]).distance().au)
                kind = ""
                if inner:
                    kind = "верхнее " if d_au > sun_dist else "нижнее "
                events.append(AstroEvent(
                    category=CAT_PLANET, body=key, title=(f"{kind}соединение с Солнцем: {name}")[0].upper() + (f"{kind}соединение с Солнцем: {name}")[1:],
                    description=(f"{name} проходит на небе рядом с Солнцем и не наблюдается "
                                 f"(по эклиптической долготе). Расстояние до Земли {d_au:.3f} а. е."),
                    utc_time=moment, params={"kind": "conjunction", "distance_au": round(d_au, 4)},
                    source=EPHEMERIS_SOURCE))
        times, state = find_discrete(t0, t1, _retrograde_function(ctx, body))
        for i in range(len(times)):
            starts = int(state[i]) == 1
            events.append(AstroEvent(
                category=CAT_PLANET, body=key,
                title=f"{'Начало' if starts else 'Конец'} попятного движения: {name}",
                description=(f"Момент стояния: {name} " + (
                    "останавливается на фоне звёзд и начинает двигаться с востока на запад (ретроградно)."
                    if starts else "останавливается и возобновляет прямое движение с запада на восток.")),
                utc_time=times[i].utc_datetime(),
                params={"kind": "retrograde_start" if starts else "retrograde_end"},
                source=EPHEMERIS_SOURCE))
        if inner:
            f = _elongation_function(ctx, body, step_days=5.0 if key == "mercury" else 10.0)
            tm, values = find_maxima(t0, t1, f)
            for i in range(len(tm)):
                sun_lon, body_lon = _ecliptic_longitudes(ctx, body, tm[i])
                east = float((body_lon - sun_lon) % 360.0) < 180.0
                side = "восточная (вечерняя видимость)" if east else "западная (утренняя видимость)"
                events.append(AstroEvent(
                    category=CAT_PLANET, body=key,
                    title=f"Наибольшая {'восточная' if east else 'западная'} элонгация: {name}",
                    description=f"Угловое удаление от Солнца {float(values[i]):.1f}° — {side}.",
                    utc_time=tm[i].utc_datetime(),
                    params={"kind": "greatest_elongation", "elongation_deg": round(float(values[i]), 2),
                            "east": east},
                    source=EPHEMERIS_SOURCE))
    return sorted(events, key=lambda e: e.utc_time)
