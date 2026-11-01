"""Метеорные потоки: таблица основных ежегодных потоков и расчёт условий наблюдения.

Данные — округлённые значения из календаря Международной метеорной организации (IMO).
Дата максимума и ZHR меняются от года к году (особенно у Тауридов и Леонид), поэтому
значения ориентировочные; время максимума не указывается — событие «на весь день».
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from astronomy.event_types import CAT_METEOR, AstroEvent


@dataclass(frozen=True)
class MeteorShower:
    code: str
    name: str
    start: tuple[int, int]      # (месяц, день) начала активности
    end: tuple[int, int]        # (месяц, день) окончания активности
    peak: tuple[int, int]       # (месяц, день) максимума
    zhr: int
    ra_hours: float             # прямое восхождение радианта
    dec_deg: float              # склонение радианта
    constellation: str


SHOWERS = [
    MeteorShower("QUA", "Квадрантиды", (12, 28), (1, 12), (1, 4), 110, 15.33, 49.5, "Волопас"),
    MeteorShower("LYR", "Лириды", (4, 14), (4, 30), (4, 22), 18, 18.07, 34.0, "Лира"),
    MeteorShower("ETA", "Эта-Аквариды", (4, 19), (5, 28), (5, 6), 50, 22.53, -1.0, "Водолей"),
    MeteorShower("PER", "Персеиды", (7, 17), (8, 24), (8, 12), 100, 3.20, 58.0, "Персей"),
    MeteorShower("ORI", "Ориониды", (10, 2), (11, 7), (10, 21), 20, 6.33, 16.0, "Орион"),
    MeteorShower("TAU", "Южные Тауриды", (9, 28), (12, 2), (11, 5), 5, 3.50, 14.0, "Телец"),
    MeteorShower("LEO", "Леониды", (11, 6), (11, 30), (11, 17), 15, 10.13, 22.0, "Лев"),
    MeteorShower("GEM", "Геминиды", (12, 4), (12, 20), (12, 14), 150, 7.47, 33.0, "Близнецы"),
    MeteorShower("URS", "Урсиды", (12, 17), (12, 26), (12, 22), 10, 14.60, 76.0, "Малая Медведица"),
]


def peak_date(shower: MeteorShower, year: int) -> date:
    return date(year, *shower.peak)


def activity_period(shower: MeteorShower, year: int) -> tuple[date, date]:
    """Период активности потока, связанный с максимумом указанного года."""
    peak = peak_date(shower, year)
    start = date(year, *shower.start)
    end = date(year, *shower.end)
    if start > peak:        # поток начинается в предыдущем году (Квадрантиды)
        start = date(year - 1, *shower.start)
    if end < peak:          # заканчивается в следующем году
        end = date(year + 1, *shower.end)
    return start, end


def moon_influence(illumination: float) -> str:
    if illumination < 0.25:
        return "Луна почти не мешает"
    if illumination < 0.60:
        return "Луна умеренно мешает"
    return "яркая Луна сильно мешает"


def shower_events(year: int) -> list[AstroEvent]:
    """События «максимум потока» для года (без привязки к месту наблюдения)."""
    events = []
    for s in SHOWERS:
        start, end = activity_period(s, year)
        peak = peak_date(s, year)
        events.append(AstroEvent(
            category=CAT_METEOR, body=s.code, title=f"Максимум метеорного потока: {s.name}",
            description=(f"Активность с {start:%d.%m.%Y} по {end:%d.%m.%Y}. ZHR ≈ {s.zhr}. "
                         f"Радиант в созвездии «{s.constellation}» "
                         f"(α ≈ {s.ra_hours:.2f}ч, δ ≈ {s.dec_deg:+.0f}°). "
                         "Дата и ZHR ориентировочные (календарь IMO)."),
            utc_time=datetime(peak.year, peak.month, peak.day, 12, 0, tzinfo=timezone.utc),
            params={"all_day": True, "zhr": s.zhr, "code": s.code,
                    "ra_hours": s.ra_hours, "dec_deg": s.dec_deg,
                    "start": start.isoformat(), "end": end.isoformat(),
                    "peak_date": peak.isoformat()},
            source="IMO Meteor Shower Calendar (округлённые значения)",
        ))
    return events


def radiant_altitude(ctx, shower_params: dict, local_day: date, local_hour: int = 3) -> float:
    """Высота радианта в заданный местный час выбранной даты."""
    from skyfield.api import Star
    star = Star(ra_hours=shower_params["ra_hours"], dec_degrees=shower_params["dec_deg"])
    moment = datetime(local_day.year, local_day.month, local_day.day, local_hour, 0, tzinfo=ctx.tz)
    t = ctx.t(moment)
    alt, _, _ = ctx.observer.at(t).observe(star).apparent().altaz()
    return float(alt.degrees)


def peak_night_moon_illumination(ctx, peak: date) -> float:
    from astronomy import moon
    moment = datetime(peak.year, peak.month, peak.day, 2, 0, tzinfo=ctx.tz)
    return moon.illumination_at(ctx, moment.astimezone(timezone.utc))


def local_visibility_text(ctx, event: AstroEvent) -> str:
    peak = date.fromisoformat(event.params["peak_date"])
    # Ночь максимума: радиант оцениваем около 03:00 местного времени.
    alt = radiant_altitude(ctx, event.params, peak, 3)
    illum = peak_night_moon_illumination(ctx, peak)
    radiant = (f"радиант в 03:00 над горизонтом (высота {alt:.0f}°)" if alt > 0
               else f"радиант в 03:00 под горизонтом ({alt:.0f}°) — поток виден слабо")
    return f"{radiant}; освещённость Луны ≈ {illum * 100:.0f}% ({moon_influence(illum)})."
