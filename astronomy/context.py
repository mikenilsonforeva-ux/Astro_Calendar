"""Контекст расчётов: шкала времени, эфемериды JPL и место наблюдателя (Skyfield).

Все астрономические функции принимают AstroContext первым аргументом, поэтому
интерфейс не знает ничего о Skyfield.

Модель и допущения:
* эфемериды — JPL DE440s (или DE421), положения тел «apparent» (с учётом
  светового времени, аберрации и отклонения света);
* наблюдатель — геодезические координаты WGS84 с высотой над уровнем моря;
* время — UTC; шкала времени и поправки ΔT берутся из встроенных в Skyfield таблиц;
* высота над горизонтом в таблицах «текущего положения» приведена с учётом
  стандартной рефракции (10 °C, 1010 мбар), восходы/заходы — по стандартным
  горизонтам (см. visibility.py).
"""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from astronomy.time_utils import ensure_utc, get_timezone, validate_coordinates

EPHEMERIS_SOURCE = "Skyfield + эфемериды JPL"


class EphemerisUnavailable(RuntimeError):
    """Файл эфемерид не найден или не может быть прочитан."""


_lock = threading.Lock()
_kernels: dict[str, object] = {}
_timescale = None
_constellation_fn = None


def _loader(directory: Path):
    from skyfield.api import Loader
    return Loader(str(directory), verbose=False)


def get_timescale(directory: Path):
    global _timescale
    with _lock:
        if _timescale is None:
            _timescale = _loader(directory).timescale(builtin=True)
        return _timescale


def load_kernel(path: Path):
    path = Path(path)
    if not path.is_file():
        raise EphemerisUnavailable(
            "Файл эфемерид не найден. Откройте раздел «Обновление данных» и скачайте его "
            "(нужен интернет, один раз)."
        )
    key = str(path.resolve())
    with _lock:
        if key not in _kernels:
            try:
                _kernels[key] = _loader(path.parent)(path.name)
            except Exception as exc:  # повреждённый файл и т. п.
                raise EphemerisUnavailable(f"Не удалось открыть файл эфемерид {path.name}: {exc}") from exc
        return _kernels[key]


def get_constellation_function():
    global _constellation_fn
    with _lock:
        if _constellation_fn is None:
            from skyfield.api import load_constellation_map
            _constellation_fn = load_constellation_map()
        return _constellation_fn


class AstroContext:
    def __init__(self, ts, eph, latitude: float, longitude: float, elevation_m: float,
                 timezone_name: str, place_name: str = "", ephemeris_name: str = ""):
        from skyfield.api import wgs84
        validate_coordinates(latitude, longitude, elevation_m)
        self.ts = ts
        self.eph = eph
        self.latitude = latitude
        self.longitude = longitude
        self.elevation_m = elevation_m
        self.tz: ZoneInfo = get_timezone(timezone_name)
        self.place_name = place_name
        self.ephemeris_name = ephemeris_name
        self.topos = wgs84.latlon(latitude, longitude, elevation_m=elevation_m)
        self.earth = eph["earth"]
        self.observer = self.earth + self.topos

    @classmethod
    def create(cls, latitude: float, longitude: float, elevation_m: float, timezone_name: str,
               ephemeris_path: Path, place_name: str = "") -> "AstroContext":
        path = Path(ephemeris_path)
        eph = load_kernel(path)
        ts = get_timescale(path.parent)
        return cls(ts, eph, latitude, longitude, elevation_m, timezone_name,
                   place_name=place_name, ephemeris_name=path.name)

    # ---- время ---------------------------------------------------------------
    def t(self, when: datetime):
        """datetime (aware) -> Time Skyfield."""
        return self.ts.from_datetime(ensure_utc(when))

    def ts_utc(self, year: int, month: int = 1, day: int = 1, hour: int = 0):
        return self.ts.utc(year, month, day, hour)

    @staticmethod
    def dt(t) -> datetime:
        """Time Skyfield (скаляр) -> aware datetime в UTC."""
        return t.utc_datetime()

    def dt_list(self, times) -> list[datetime]:
        return [times[i].utc_datetime() for i in range(len(times))]

    def local(self, when_utc: datetime) -> datetime:
        return ensure_utc(when_utc).astimezone(self.tz)

    @property
    def constellation_at(self):
        return get_constellation_function()
