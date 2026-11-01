"""Индекс пригодности ночи для наблюдений (0–100) — ОЦЕНКА ПРИЛОЖЕНИЯ.

Это не физическая величина и не прогноз астрономического «seeing»/прозрачности.
Метеорологическая видимость (visibility) ≠ астрономическая прозрачность атмосферы;
турбулентность и прозрачность в индексе не учитываются, пока нет достоверного источника.

Вклад факторов (веса в сумме 100):
  облачность 55, Луна 15, влажность 10, ветер 10, метеорологическая видимость 10, давление 0
  (давление только показывается). Недостающие данные исключаются, остальные веса пересчитываются.
Дополнительно:
  * осадки ≥ 0.1 мм/ч ограничивают итог сверху значением 15;
  * если задан объект, итог умножается на коэффициент высоты (0 на горизонте, 1 от 40° и выше);
  * индекс считается только для тёмного времени (Солнце ниже −12°), иначе None.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from api.weather_api import HourlyWeather

WEIGHTS = {"cloud": 55.0, "moon": 15.0, "humidity": 10.0, "wind": 10.0, "visibility": 10.0}
DARK_SUN_ALTITUDE = -12.0

DISCLAIMER = ("Индекс — оценка приложения по прогнозу Open-Meteo, а не точный прогноз. "
              "Метеорологическая видимость не равна астрономической прозрачности атмосферы; "
              "турбулентность (seeing) и прозрачность не учитываются.")


def _linear(value: float, good: float, bad: float) -> float:
    """1.0 при value == good, 0.0 при value == bad, линейно между ними."""
    if good == bad:
        return 1.0
    t = (value - bad) / (good - bad)
    return max(0.0, min(1.0, t))


@dataclass
class NightScore:
    score: int | None
    label: str
    parts: dict[str, float]      # доля максимума по каждому фактору (0..1)
    note: str = ""


def label_for(score: int | None) -> str:
    if score is None:
        return "не ночь"
    if score >= 80:
        return "отлично"
    if score >= 60:
        return "хорошо"
    if score >= 40:
        return "средне"
    if score >= 20:
        return "плохо"
    return "непригодно"


def altitude_factor(altitude_deg: float | None) -> float:
    if altitude_deg is None:
        return 1.0
    if altitude_deg <= 0:
        return 0.0
    return min(1.0, math.sin(math.radians(altitude_deg)) / math.sin(math.radians(40.0)))


def night_score(w: HourlyWeather, sun_altitude: float, moon_altitude: float,
                moon_illumination: float, target_altitude: float | None = None) -> NightScore:
    if sun_altitude > DARK_SUN_ALTITUDE:
        return NightScore(None, label_for(None), {}, "Солнце выше −12°: небо недостаточно тёмное.")

    parts: dict[str, float] = {}
    if w.cloud_cover_pct is not None:
        parts["cloud"] = 1.0 - max(0.0, min(100.0, w.cloud_cover_pct)) / 100.0
    if w.humidity_pct is not None:
        parts["humidity"] = _linear(w.humidity_pct, 70.0, 100.0)
    if w.wind_kmh is not None:
        parts["wind"] = _linear(w.wind_kmh, 10.0, 40.0)
    if w.visibility_m is not None:
        parts["visibility"] = _linear(w.visibility_m / 1000.0, 20.0, 5.0)
    moon_up = max(0.0, min(1.0, moon_altitude / 30.0))
    parts["moon"] = 1.0 - max(0.0, min(1.0, moon_illumination)) * moon_up

    weight_sum = sum(WEIGHTS[k] for k in parts)
    raw = sum(WEIGHTS[k] * v for k, v in parts.items()) / weight_sum * 100.0

    notes = []
    if w.precipitation_mm is not None and w.precipitation_mm >= 0.1:
        raw = min(raw, 15.0)
        notes.append("осадки")
    if "cloud" not in parts:
        notes.append("нет данных об облачности — оценка ненадёжна")
    raw *= altitude_factor(target_altitude)
    if target_altitude is not None and target_altitude <= 0:
        notes.append("объект под горизонтом")
    score = int(round(max(0.0, min(100.0, raw))))
    return NightScore(score, label_for(score), parts, ", ".join(notes))
