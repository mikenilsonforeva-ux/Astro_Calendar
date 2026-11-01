"""Простые модели данных, общие для БД и сервисов."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Location:
    name: str
    latitude: float
    longitude: float
    elevation_m: float
    timezone: str
    is_default: bool = False
    id: int | None = None
