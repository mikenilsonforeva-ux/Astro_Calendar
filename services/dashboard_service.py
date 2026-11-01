"""Данные для главной страницы (вычисления отдельно от интерфейса)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from astronomy import moon, planets, sun
from astronomy.context import AstroContext
from astronomy.event_types import AstroEvent
from services.event_manager import EventManager


@dataclass
class Dashboard:
    now_utc: datetime
    moon: moon.MoonInfo
    sun_day: sun.SunDay
    sun_pos: sun.SunPosition
    planets: list[planets.PlanetInfo]
    events: list[AstroEvent] = field(default_factory=list)


def build_dashboard(ctx: AstroContext, events: EventManager, now_utc: datetime | None = None,
                    horizon_days: int = 60, max_events: int = 8) -> Dashboard:
    now_utc = now_utc or datetime.now(timezone.utc)
    upcoming = events.get_events(ctx, now_utc, now_utc + timedelta(days=horizon_days))
    return Dashboard(
        now_utc=now_utc,
        moon=moon.info(ctx, now_utc),
        sun_day=sun.day_info(ctx, ctx.local(now_utc).date()),
        sun_pos=sun.position(ctx, now_utc),
        planets=planets.all_info(ctx, now_utc, with_rise_set=False),
        events=upcoming[:max_events],
    )
