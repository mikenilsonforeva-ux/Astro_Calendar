"""CelesTrak: элементы орбит спутников в формате TLE (https://celestrak.org/).

Используется GP-интерфейс: gp.php?GROUP=<группа>&FORMAT=tle. Данные обновляются несколько
раз в сутки; слишком частые запросы CelesTrak блокирует, поэтому приложение кэширует TLE.
"""
from __future__ import annotations

from dataclasses import dataclass

from api.http_client import ApiError, HttpClient

GP_URL = "https://celestrak.org/NORAD/elements/gp.php"
ISS_CATNR = 25544
GROUPS = {"stations": "Космические станции (МКС, Тяньгун)", "visual": "Яркие спутники (100 ярчайших)"}
ATTRIBUTION = "Орбитальные элементы: CelesTrak (https://celestrak.org). Расчёт орбит — модель SGP4."


@dataclass
class Tle:
    name: str
    line1: str
    line2: str

    @property
    def catnr(self) -> int:
        return int(self.line1[2:7])


def checksum_ok(line: str) -> bool:
    """Контрольная сумма TLE-строки: сумма цифр и по 1 за каждый «-» по модулю 10."""
    if len(line) < 69 or not line[68].isdigit():
        return False
    total = sum(int(c) if c.isdigit() else (1 if c == "-" else 0) for c in line[:68])
    return total % 10 == int(line[68])


def parse_tle(text: str) -> list[Tle]:
    """Разбирает трёхстрочный TLE (имя + две строки). Некорректные записи пропускаются."""
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    result: list[Tle] = []
    i = 0
    while i + 2 < len(lines):
        name, l1, l2 = lines[i].strip(), lines[i + 1], lines[i + 2]
        if l1.startswith("1 ") and l2.startswith("2 ") and checksum_ok(l1) and checksum_ok(l2):
            result.append(Tle(name, l1[:69], l2[:69]))
            i += 3
        else:
            i += 1
    return result


def fetch_group(group: str, client: HttpClient | None = None) -> list[Tle]:
    client = client or HttpClient()
    text = client.get_text(GP_URL, {"GROUP": group, "FORMAT": "tle"})
    tles = parse_tle(text)
    if not tles:
        raise ApiError(f"CelesTrak не вернул корректных TLE для группы «{group}»: {text[:120]!r}")
    return tles
