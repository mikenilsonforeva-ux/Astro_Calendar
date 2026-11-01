"""Форматирование угловых величин и направлений."""
from __future__ import annotations

_COMPASS = ["С", "ССВ", "СВ", "ВСВ", "В", "ВЮВ", "ЮВ", "ЮЮВ",
            "Ю", "ЮЮЗ", "ЮЗ", "ЗЮЗ", "З", "ЗСЗ", "СЗ", "ССЗ"]


def compass_point(azimuth_deg: float) -> str:
    """Название румба (С, СВ, В, …) по азимуту от севера по часовой стрелке."""
    index = int((azimuth_deg % 360.0) / 22.5 + 0.5) % 16
    return _COMPASS[index]


def format_hms(hours: float) -> str:
    """Часы -> «12ч 34м 56.7с» (для прямого восхождения)."""
    hours = hours % 24.0
    h = int(hours)
    m_f = (hours - h) * 60.0
    m = int(m_f)
    s = (m_f - m) * 60.0
    if s >= 59.95:
        s = 0.0
        m += 1
    if m == 60:
        m = 0
        h = (h + 1) % 24
    return f"{h:02d}ч {m:02d}м {s:04.1f}с"


def format_dms(degrees: float, signed: bool = True) -> str:
    """Градусы -> «+12° 34′ 56″»."""
    sign = "-" if degrees < 0 else ("+" if signed else "")
    value = abs(degrees)
    d = int(value)
    m_f = (value - d) * 60.0
    m = int(m_f)
    s = int(round((m_f - m) * 60.0))
    if s == 60:
        s = 0
        m += 1
    if m == 60:
        m = 0
        d += 1
    return f"{sign}{d}° {m:02d}′ {s:02d}″"


def format_lat_lon(latitude: float, longitude: float) -> str:
    ns = "с. ш." if latitude >= 0 else "ю. ш."
    ew = "в. д." if longitude >= 0 else "з. д."
    return f"{abs(latitude):.4f}° {ns}, {abs(longitude):.4f}° {ew}"


def normalize_degrees(value: float) -> float:
    return value % 360.0
