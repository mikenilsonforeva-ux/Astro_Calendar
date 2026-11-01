"""Менеджер астрономических событий: расчёт по годам, сохранение в SQLite, видимость.

Глобальные события (фазы Луны, равноденствия, …) считаются один раз на год и
хранятся в таблице astronomical_events. Видимость из выбранного места
определяется при показе (annotate_visibility) и в БД не сохраняется.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from astronomy import eclipses, meteors, moon, planets, sun
from astronomy.context import AstroContext
from astronomy.event_types import (CAT_APSIDES, CAT_ECLIPSE, CAT_METEOR, CAT_MOON_PHASE,
                                   CAT_PLANET, CAT_SEASON, AstroEvent)
from astronomy.time_utils import ensure_utc
from astronomy.visibility import altitude_azimuth
from database.db_manager import DatabaseManager
from services.cache_manager import CacheManager

log = logging.getLogger(__name__)

# Увеличивать при изменении алгоритмов: старый кэш будет пересчитан.
ALGORITHM_VERSION = 2


def _iso(dt: datetime) -> str:
    return ensure_utc(dt).strftime("%Y-%m-%dT%H:%M:%S")


class EventManager:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.cache = CacheManager(db)

    # ---- расчёт --------------------------------------------------------------
    @staticmethod
    def _cache_key(year: int) -> str:
        return f"events:v{ALGORITHM_VERSION}:{year}"

    def is_year_cached(self, year: int) -> bool:
        return self.cache.get(self._cache_key(year)) is not None

    def compute_year(self, ctx: AstroContext, year: int) -> list[AstroEvent]:
        t0, t1 = ctx.ts.utc(year, 1, 1), ctx.ts.utc(year + 1, 1, 1)
        events: list[AstroEvent] = []
        events += moon.phase_events(ctx, t0, t1)
        events += sun.season_events(ctx, t0, t1)
        events += moon.apsis_events(ctx, t0, t1)
        events += planets.planet_events(ctx, t0, t1)
        events += eclipses.lunar_eclipse_events(ctx, t0, t1)
        events += meteors.shower_events(year)
        events = [e for e in events if e.utc_time.year == year]
        events.sort(key=lambda e: (e.utc_time, e.title))
        return events

    def ensure_year(self, ctx: AstroContext, year: int, force: bool = False) -> None:
        if not force and self.is_year_cached(year):
            return
        log.info("Расчёт событий за %d год", year)
        events = self.compute_year(ctx, year)
        start = f"{year:04d}-01-01T00:00:00"
        end = f"{year + 1:04d}-01-01T00:00:00"
        self.db.replace_events(start, end, [e.to_row() for e in events])
        self.cache.set(self._cache_key(year), {"count": len(events), "ephemeris": ctx.ephemeris_name},
                       source=f"{ctx.ephemeris_name}")

    # ---- выборка -------------------------------------------------------------
    def get_events(self, ctx: AstroContext | None, start_utc: datetime, end_utc: datetime,
                   categories: list[str] | None = None) -> list[AstroEvent]:
        """События диапазона [start_utc, end_utc). Без ctx отдаются только сохранённые."""
        start_utc, end_utc = ensure_utc(start_utc), ensure_utc(end_utc)
        if ctx is not None:
            for year in range(start_utc.year, end_utc.year + 1):
                self.ensure_year(ctx, year)
        rows = self.db.query_events(_iso(start_utc), _iso(end_utc), categories)
        events = [AstroEvent.from_row(r) for r in rows]
        self.annotate_visibility(ctx, events)
        return events

    # ---- видимость из выбранного места --------------------------------------
    def annotate_visibility(self, ctx: AstroContext | None, events: list[AstroEvent]) -> None:
        for event in events:
            event.is_global = event.category != CAT_METEOR
            if ctx is None:
                event.visibility = "Видимость не рассчитана: нет файла эфемерид."
                continue
            try:
                event.visibility = self.visibility_text(ctx, event)
            except Exception as exc:  # расчёт видимости не должен ломать список
                log.warning("Видимость события %s: %s", event.title, exc)
                event.visibility = "Не удалось рассчитать видимость."

    def visibility_text(self, ctx: AstroContext, event: AstroEvent) -> str:
        when = event.utc_time
        if event.category == CAT_SEASON:
            return "Глобальное астрономическое событие; не зависит от места наблюдения."
        if event.category == CAT_METEOR:
            return meteors.local_visibility_text(ctx, event)
        if event.category == CAT_ECLIPSE:
            return ("Глобальное событие. " + eclipses.lunar_eclipse_visibility(ctx, when))
        if event.category in (CAT_MOON_PHASE, CAT_APSIDES):
            alt, _ = altitude_azimuth(ctx, ctx.eph["moon"], when)
            state = "над горизонтом" if alt > 0 else "под горизонтом"
            extra = " (новолуние: Луна не видна)" if event.params.get("kind") == 0 \
                and event.category == CAT_MOON_PHASE else ""
            return f"В этот момент Луна {state} (высота {alt:.0f}°){extra}."
        if event.category == CAT_PLANET:
            body = planets.PLANET_BY_KEY[event.body]
            planet_alt, _ = altitude_azimuth(ctx, ctx.eph[body[2]], when)
            sun_alt, _ = altitude_azimuth(ctx, ctx.eph["sun"], when)
            kind = event.params.get("kind")
            if kind == "conjunction":
                return "Планета рядом с Солнцем на небе: наблюдать нельзя."
            if kind in ("retrograde_start", "retrograde_end"):
                return "Глобальное явление: смена направления видимого движения планеты на фоне звёзд."
            state = "над горизонтом" if planet_alt > 0 else "под горизонтом"
            sky = "ночью" if sun_alt < -6 else "днём/в сумерках"
            return (f"В момент события планета {state} (высота {planet_alt:.0f}°), "
                    f"у вас {sky}. Сама планета в эти недели обычно доступна для наблюдений.")
        return ""
