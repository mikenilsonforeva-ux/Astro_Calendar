"""Проверка вычислительного ядра без интерфейса.

Запуск:  python scripts/check_core.py
Печатает положение Солнца, Луны и планет для Москвы на текущий момент.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from astronomy import moon, planets, sun  # noqa: E402
from astronomy.context import AstroContext  # noqa: E402


def main() -> int:
    path = config.find_ephemeris_file()
    if path is None:
        print("Файл эфемерид не найден. Запустите приложение и скачайте его в разделе "
              "«Обновление данных» либо положите de440s.bsp в resources/ephemeris/.")
        return 1
    ctx = AstroContext.create(55.7558, 37.6173, 150, "Europe/Moscow", path, "Москва")
    now = datetime.now(timezone.utc)
    s = sun.position(ctx, now)
    print(f"Солнце: высота {s.altitude:+.2f}°, азимут {s.azimuth:.2f}°, EoT {s.equation_of_time_min:+.2f} мин")
    day = sun.day_info(ctx, ctx.local(now).date())
    print(f"Восход {day.sunrise}, заход {day.sunset}")
    m = moon.info(ctx, now)
    print(f"Луна: {m.phase_name}, {m.illumination * 100:.1f}%, возраст {m.age_days:.1f} сут, {m.distance_km:.0f} км")
    for p in planets.all_info(ctx, now, with_rise_set=False):
        print(f"{p.name:9s} {p.constellation:12s} высота {p.altitude:+6.1f}°  блеск {p.magnitude:+.1f}  элонг. {p.elongation:.1f}°")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
