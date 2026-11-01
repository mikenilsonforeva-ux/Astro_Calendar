"""Прогноз погоды Open-Meteo (https://open-meteo.com/en/docs).

Запрашивается почасовой прогноз; время в ответе — UTC. Значения могут быть None
(модель не дала данных) — вызывающий код обязан это учитывать.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from api.http_client import ApiError, HttpClient

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARS = ["temperature_2m", "relative_humidity_2m", "cloud_cover", "wind_speed_10m",
               "precipitation", "visibility", "pressure_msl"]


@dataclass
class HourlyWeather:
    time_utc: datetime
    temperature_c: float | None
    humidity_pct: float | None
    cloud_cover_pct: float | None
    wind_kmh: float | None
    precipitation_mm: float | None
    visibility_m: float | None
    pressure_hpa: float | None

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("time_utc")
        return d

    @classmethod
    def from_dict(cls, time_utc: datetime, d: dict) -> "HourlyWeather":
        return cls(time_utc=time_utc, **{k: d.get(k) for k in (
            "temperature_c", "humidity_pct", "cloud_cover_pct", "wind_kmh",
            "precipitation_mm", "visibility_m", "pressure_hpa")})


def _number(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def parse_forecast(payload: dict) -> list[HourlyWeather]:
    """Разбирает ответ API. Бросает ApiError, если структура не соответствует документации."""
    try:
        hourly = payload["hourly"]
        times = hourly["time"]
    except (KeyError, TypeError) as exc:
        raise ApiError("Ответ Open-Meteo имеет неожиданный формат.") from exc
    if payload.get("error"):
        raise ApiError(f"Open-Meteo: {payload.get('reason', 'ошибка запроса')}")
    columns = {name: hourly.get(name) or [None] * len(times) for name in HOURLY_VARS}
    result = []
    for i, stamp in enumerate(times):
        try:
            moment = datetime.strptime(stamp, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue

        def col(name: str):
            values = columns[name]
            return _number(values[i]) if i < len(values) else None

        result.append(HourlyWeather(
            time_utc=moment, temperature_c=col("temperature_2m"),
            humidity_pct=col("relative_humidity_2m"), cloud_cover_pct=col("cloud_cover"),
            wind_kmh=col("wind_speed_10m"), precipitation_mm=col("precipitation"),
            visibility_m=col("visibility"), pressure_hpa=col("pressure_msl")))
    if not result:
        raise ApiError("Open-Meteo не вернул ни одного часа прогноза.")
    return result


def fetch_forecast(latitude: float, longitude: float, days: int = 5,
                   client: HttpClient | None = None) -> list[HourlyWeather]:
    client = client or HttpClient()
    payload = client.get_json(FORECAST_URL, {
        "latitude": round(latitude, 4), "longitude": round(longitude, 4),
        "hourly": ",".join(HOURLY_VARS), "forecast_days": max(1, min(days, 16)),
        "timezone": "UTC", "wind_speed_unit": "kmh",
    })
    if not isinstance(payload, dict):
        raise ApiError("Ответ Open-Meteo имеет неожиданный формат.")
    return parse_forecast(payload)
