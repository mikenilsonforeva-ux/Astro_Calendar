"""Данные о солнечной и геомагнитной активности (NOAA SWPC) с кэшем и офлайн-режимом."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from api import noaa_api
from api.http_client import ApiError
from database.db_manager import DatabaseManager
from services.cache_manager import CacheManager

SOURCE = "NOAA SWPC"
MAX_AGE = timedelta(minutes=30)
FMT = "%Y-%m-%dT%H:%M:%S"


@dataclass
class SolarData:
    kp_history: list[noaa_api.KpPoint]
    kp_forecast: list[noaa_api.KpPoint]
    flares: list[noaa_api.Flare]
    updated_at: str | None
    from_cache: bool
    warnings: list[str] = field(default_factory=list)


def _dump_kp(points):
    return [[p.time_utc.strftime(FMT), p.kp, p.observed, p.noaa_scale] for p in points]


def _load_kp(rows):
    return [noaa_api.KpPoint(datetime.strptime(t, FMT).replace(tzinfo=timezone.utc), kp, obs, sc)
            for t, kp, obs, sc in rows]


def _dump_flares(flares):
    return [[f.begin_utc.strftime(FMT) if f.begin_utc else None,
             f.max_utc.strftime(FMT) if f.max_utc else None, f.max_class] for f in flares]


def _load_flares(rows):
    def parse(v):
        return datetime.strptime(v, FMT).replace(tzinfo=timezone.utc) if v else None
    return [noaa_api.Flare(parse(b), parse(m), c) for b, m, c in rows]


class SolarService:
    KEYS = ("solar:kp_history", "solar:kp_forecast", "solar:flares")

    def __init__(self, db: DatabaseManager):
        self.db = db
        self.cache = CacheManager(db)

    def get(self, force: bool = False) -> SolarData:
        """Свежие данные из сети; для каждой части при ошибке — последние сохранённые."""
        loaders = (
            ("solar:kp_history", noaa_api.fetch_kp_history, _dump_kp, _load_kp),
            ("solar:kp_forecast", noaa_api.fetch_kp_forecast, _dump_kp, _load_kp),
            ("solar:flares", noaa_api.fetch_flares, _dump_flares, _load_flares),
        )
        results, warnings, any_network = [], [], False
        for key, fetch, dump, load in loaders:
            fresh = None if force else self.cache.get(key, MAX_AGE)
            if fresh is not None:
                results.append(load(fresh))
                continue
            try:
                data = fetch()
                self.cache.set(key, dump(data), SOURCE)
                results.append(data)
                any_network = True
            except ApiError as exc:
                stale = self.cache.get(key)
                if stale is None:
                    results.append([])
                    warnings.append(f"{key.split(':')[1]}: нет данных ({exc})")
                else:
                    results.append(load(stale))
                    warnings.append(f"{key.split(':')[1]}: показаны сохранённые данные ({exc})")
        now = datetime.now(timezone.utc).strftime(FMT)
        if any_network:
            self.db.log_update("solar", "ok", "NOAA SWPC", now)
        elif warnings:
            self.db.log_update("solar", "error", "; ".join(warnings)[:300], now)
        updated = max((u for u in (self.cache.updated_at(k) for k in self.KEYS) if u), default=None)
        return SolarData(results[0], results[1], results[2], updated,
                         from_cache=not any_network, warnings=warnings)
