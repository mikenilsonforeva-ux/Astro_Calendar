"""Затмения.

Реализовано: лунные затмения (модуль skyfield.eclipselib) — тип и момент максимума.
НЕ реализовано в этой версии: солнечные затмения, времена контактов (полутеневая/
частная/полная фазы) и величина затмения. Приложение прямо сообщает об этом
пользователю и не выдаёт приближённые данные за точные.
"""
from __future__ import annotations

from datetime import datetime

from astronomy.context import EPHEMERIS_SOURCE, AstroContext
from astronomy.event_types import CAT_ECLIPSE, AstroEvent

LUNAR_KINDS = {
    0: ("Полутеневое лунное затмение", "penumbral",
        "Луна проходит только через полутень Земли; затмение трудно заметить невооружённым глазом."),
    1: ("Частное лунное затмение", "partial",
        "Часть диска Луны погружается в полную тень Земли."),
    2: ("Полное лунное затмение", "total",
        "Луна целиком входит в тень Земли и приобретает красноватый оттенок."),
}

NOT_IMPLEMENTED_NOTE = (
    "Солнечные затмения, времена контактов и величина затмений в этой версии не рассчитываются. "
    "Данные появятся после подключения проверенных источников (NASA GSFC / USNO) — этап 4."
)


def lunar_eclipse_events(ctx: AstroContext, t0, t1) -> list[AstroEvent]:
    try:
        from skyfield import eclipselib
    except ImportError:  # очень старая версия Skyfield
        return []
    times, kinds, _details = eclipselib.lunar_eclipses(t0, t1, ctx.eph)
    events = []
    for i in range(len(times)):
        title, kind, description = LUNAR_KINDS[int(kinds[i])]
        events.append(AstroEvent(
            category=CAT_ECLIPSE, body="moon", title=title, description=description,
            utc_time=times[i].utc_datetime(), params={"kind": kind, "time_is": "maximum"},
            source=EPHEMERIS_SOURCE,
        ))
    return events


def lunar_eclipse_visibility(ctx: AstroContext, when_utc: datetime) -> str:
    """Можно ли наблюдать момент максимума затмения из выбранного места."""
    from astronomy.visibility import altitude_azimuth
    alt, _ = altitude_azimuth(ctx, ctx.eph["moon"], when_utc)
    if alt > 0:
        return (f"В момент максимума Луна над горизонтом (высота {alt:.0f}°): затмение можно "
                "наблюдать (при ясном небе). Видимость остальных фаз не рассчитывалась.")
    return (f"В момент максимума Луна под горизонтом (высота {alt:.0f}°): из выбранного места "
            "максимум не виден. Часть фаз может быть доступна — их расчёт пока не реализован.")
