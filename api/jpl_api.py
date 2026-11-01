"""Загрузка файлов эфемерид JPL (SPICE-ядра DE) с серверов NAIF.

Файлы .bsp — это те же эфемериды JPL, которые использует Skyfield. После загрузки
все расчёты выполняются локально, без интернета.

Запросы к JPL Horizons (контрольные сверки) запланированы на этап 4 — см. README.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from api.http_client import HttpClient

NAIF_BASE = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/"

# Описание: покрытие по датам и приблизительный размер (для сообщений пользователю).
EPHEMERIS_INFO = {
    "de440s.bsp": {"years": "1849–2150", "size_mb": 32},
    "de421.bsp": {"years": "1900–2050", "size_mb": 17},
}


def download_ephemeris(filename: str, dest_dir: Path,
                       progress: Callable[[int, int], None] | None = None,
                       client: HttpClient | None = None) -> Path:
    if filename not in EPHEMERIS_INFO:
        raise ValueError(f"Неизвестный файл эфемерид: {filename}")
    client = client or HttpClient(read_timeout=30)
    return client.download(NAIF_BASE + filename, Path(dest_dir) / filename,
                           progress=progress, min_size=5_000_000)
