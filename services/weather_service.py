"""Прогноз погоды для места наблюдения: загрузка, хранение, расчёт индекса по ночам."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from api.http_client import ApiError
from api.weather_api import HourlyWeather, fetch_forecast
from astronomy import moon, observing_index
from astronomy.context import AstroContext
from astronomy.planets import PLANET_BY_KEY
from astronomy.time_utils import ensure_utc
from database.db_manager import DatabaseManager
from database.models import Location

log = logging.getLogger(__name__)

SOURCE = "Open-Meteo"
MAX_AGE = timedelta(hours=3)


@dataclass
class HourReport:
    time_local: datetime
    weather: HourlyWeather
    sun_altitude: float
    moon_altitude: float
    moon_illumination: float
    target_altitude: float | None
    score: observing_index.NightScore


@dataclass
class NightReport:
    evening_date: date                 # местная дата вечера, когда ночь начинается
    hours: list[HourReport] = field(default_factory=list)

    @property
    def scored(self) -> list[HourReport]:
        return [h for h in self.hours if h.score.score is not None]

    @property
    def average(self) -> int | None:
        s = self.scored
        return round(sum(h.score.score for h in s) / len(s)) if s else None

    @property
    def best(self) -> HourReport | None:
        s = self.scored
        return max(s, key=lambda h: h.score.score) if s else None


@dataclass
class ForecastResult:
    hours: list[HourlyWeather]
    fetched_at: str | None
    from_cache: bool
    warning: str = ""


class WeatherService:
    def __init__(self, db: DatabaseManager):
        self.db = db

    # ---- данные ---------------------------------------------------------------
    def get_forecast(self, loc: Location, force: bool = False) -> ForecastResult:
        """Свежий прогноз из сети; при ошибке — последний сохранённый (с предупреждением)."""
        now = datetime.now(timezone.utc)
        start_iso = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:00:00")
        saved, fetched = self.db.load_weather(loc.id, start_iso)
        fresh = False
        if fetched and not force:
            age = now - datetime.strptime(fetched, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            fresh = age < MAX_AGE and len(saved) > 24
        if fresh:
            return ForecastResult(self._rows_to_hours(saved), fetched, True)
        try:
            hours = fetch_forecast(loc.latitude, loc.longitude)
        except ApiError as exc:
            if saved:
                return ForecastResult(self._rows_to_hours(saved), fetched, True,
                                      f"Нет связи с Open-Meteo, показан сохранённый прогноз: {exc}")
            raise
        self.db.save_weather(loc.id, [(h.time_utc.strftime("%Y-%m-%dT%H:%M:%S"), h.to_dict())
                                      for h in hours], SOURCE)
        self.db.log_update("weather", "ok", f"{loc.name}: {len(hours)} ч", now.strftime("%Y-%m-%dT%H:%M:%S"))
        _, fetched = self.db.load_weather(loc.id, start_iso)
        return ForecastResult([h for h in hours if h.time_utc >= now - timedelta(hours=1)], fetched, False)

    @staticmethod
    def _rows_to_hours(rows: list[tuple[str, dict]]) -> list[HourlyWeather]:
        return [HourlyWeather.from_dict(
            datetime.strptime(t, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc), p) for t, p in rows]

    # ---- индекс ---------------------------------------------------------------
    @staticmethod
    def build_report(ctx: AstroContext, hours: list[HourlyWeather],
                     target_key: str | None = None) -> list[NightReport]:
        """Индекс по часам, сгруппированный по ночам (ночь = вечер даты D → утро D+1)."""
        if not hours:
            return []
        times = ctx.ts.from_datetimes([ensure_utc(h.time_utc) for h in hours])
        at = ctx.observer.at(times)
        sun_alt = at.observe(ctx.eph["sun"]).apparent().altaz()[0].degrees
        moon_alt = at.observe(ctx.eph["moon"]).apparent().altaz()[0].degrees
        target_alt = None
        if target_key:
            body = ctx.eph[PLANET_BY_KEY[target_key][2]]
            target_alt = at.observe(body).apparent().altaz()[0].degrees
        from skyfield import almanac
        phase = almanac.moon_phase(ctx.eph, times).degrees
        illum = [moon.illumination_from_phase(float(p)) for p in phase]

        nights: dict[date, NightReport] = {}
        for i, w in enumerate(hours):
            local = w.time_utc.astimezone(ctx.tz)
            evening = local.date() if local.hour >= 12 else local.date() - timedelta(days=1)
            score = observing_index.night_score(
                w, float(sun_alt[i]), float(moon_alt[i]), illum[i],
                float(target_alt[i]) if target_alt is not None else None)
            report = nights.setdefault(evening, NightReport(evening))
            report.hours.append(HourReport(local, w, float(sun_alt[i]), float(moon_alt[i]),
                                           illum[i], float(target_alt[i]) if target_alt is not None else None,
                                           score))
        return [nights[d] for d in sorted(nights)]
