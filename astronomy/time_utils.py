"""Работа со временем: часовые пояса, границы местных суток, валидация координат."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

UTC = timezone.utc


def get_timezone(name: str) -> ZoneInfo:
    """Возвращает ZoneInfo или ValueError с понятным сообщением."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise ValueError(
            f"Неизвестный часовой пояс «{name}». Пример: Europe/Moscow. "
            "На Windows должен быть установлен пакет tzdata (pip install tzdata)."
        ) from exc


def list_timezones() -> list[str]:
    return sorted(available_timezones())


def validate_coordinates(latitude: float, longitude: float, elevation_m: float = 0.0) -> None:
    """Проверяет координаты наблюдателя. Бросает ValueError при ошибке."""
    for label, value in (("Широта", latitude), ("Долгота", longitude), ("Высота", elevation_m)):
        if value is None or value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"{label}: некорректное число.")
    if not -90.0 <= latitude <= 90.0:
        raise ValueError("Широта должна быть в диапазоне от −90° до +90°.")
    if not -180.0 <= longitude <= 180.0:
        raise ValueError("Долгота должна быть в диапазоне от −180° до +180°.")
    if not -500.0 <= elevation_m <= 9000.0:
        raise ValueError("Высота над уровнем моря должна быть от −500 до 9000 м.")


def ensure_utc(dt: datetime) -> datetime:
    """Приводит aware-datetime к UTC. Наивное время считается ошибкой."""
    if dt.tzinfo is None:
        raise ValueError("Ожидалось время с часовым поясом (aware datetime).")
    return dt.astimezone(UTC)


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_local(dt_utc: datetime, tz: ZoneInfo) -> datetime:
    return ensure_utc(dt_utc).astimezone(tz)


def local_day_bounds_utc(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Начало и конец (исключительно) местных суток в UTC.

    Корректно работает в дни перехода на летнее/зимнее время: сутки могут
    длиться 23 или 25 часов.
    """
    start = datetime.combine(day, time(0, 0), tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time(0, 0), tzinfo=tz)
    return start.astimezone(UTC), end.astimezone(UTC)


def local_range_bounds_utc(first: date, last: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """UTC-границы диапазона местных дат [first, last] включительно."""
    return local_day_bounds_utc(first, tz)[0], local_day_bounds_utc(last, tz)[1]


def format_dt(dt: datetime, with_seconds: bool = False) -> str:
    return dt.strftime("%d.%m.%Y %H:%M:%S" if with_seconds else "%d.%m.%Y %H:%M")


def format_time(dt: datetime | None, with_seconds: bool = False) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%H:%M:%S" if with_seconds else "%H:%M")


def format_duration(td: timedelta | None) -> str:
    if td is None:
        return "—"
    total = int(round(td.total_seconds()))
    hours, rem = divmod(total, 3600)
    minutes = rem // 60
    return f"{hours} ч {minutes:02d} мин"
