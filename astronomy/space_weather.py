"""Космическая погода: шкала геомагнитных бурь и грубая оценка шансов полярного сияния.

Оценка сияния — упрощённая модель приложения, а НЕ прогноз NOAA: положение границы овала
берётся как приблизительная геомагнитная широта 66.5° − 2°·Kp, а геомагнитная широта
считается по диполю с полюсом (80.65° с. ш., 72.68° з. д.). Реальная картина зависит от
времени суток, облачности, Bz межпланетного поля и других факторов.
"""
from __future__ import annotations

import math

POLE_LAT, POLE_LON = 80.65, -72.68


def storm_scale(kp: float) -> str:
    """Шкала NOAA G1–G5 по Kp (округление вниз до целого, как в шкале)."""
    level = int(math.floor(kp + 1e-9))
    if level < 5:
        return "бури нет (спокойно/слабая активность)" if level < 4 else "возмущённо (ниже G1)"
    return f"G{level - 4}: " + {1: "слабая буря", 2: "умеренная буря", 3: "сильная буря",
                                4: "очень сильная буря", 5: "экстремальная буря"}[min(level - 4, 5)]


def geomagnetic_latitude(lat: float, lon: float) -> float:
    p, l = math.radians(lat), math.radians(lon)
    pp, pl = math.radians(POLE_LAT), math.radians(POLE_LON)
    value = math.sin(p) * math.sin(pp) + math.cos(p) * math.cos(pp) * math.cos(l - pl)
    return math.degrees(math.asin(max(-1.0, min(1.0, value))))


def aurora_boundary(kp: float) -> float:
    """Приблизительная экваториальная граница овала (геомагн. широта, °)."""
    return 66.5 - 2.0 * kp


def aurora_assessment(lat: float, lon: float, kp: float) -> tuple[str, str]:
    """(категория, пояснение) для места наблюдения при заданном Kp."""
    glat = abs(geomagnetic_latitude(lat, lon))
    margin = glat - aurora_boundary(kp)
    if margin >= 6:
        verdict = "высокая"
        text = "место заметно севернее границы овала — сияние вероятно, если небо ясное и тёмное"
    elif margin >= 0:
        verdict = "средняя"
        text = "место у границы овала — сияние возможно у северного горизонта"
    elif margin >= -4:
        verdict = "низкая"
        text = "сияние возможно лишь при усилении бури; смотрите на север"
    else:
        verdict = "очень низкая"
        text = "место далеко от овала при текущем Kp"
    return verdict, (f"геомагнитная широта ≈ {glat:.0f}°, граница при Kp {kp:.1f} ≈ "
                     f"{aurora_boundary(kp):.0f}°: {text}. Оценка приложения, не прогноз NOAA.")
