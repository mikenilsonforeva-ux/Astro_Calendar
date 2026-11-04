"""Звёздный каталог Hipparcos: разбор, хранение, имена ярких звёзд и линии астеризмов.

Файл hip_main.dat (CDS, каталог I/239) — строки с полями, разделёнными «|»:
[1] номер HIP, [5] Vmag, [8] RA (°, ICRS J2000), [9] Dec (°), [11] параллакс (мс дуги),
[12] μα* (мс дуги/год), [13] μδ (мс дуги/год).

Имена звёзд подбираются по координатам и блеску (а не по номерам HIP), поэтому ошибка в
справочных данных приводит к отсутствию подписи, а не к неверной.
"""
from __future__ import annotations

import gzip
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from astronomy.skymap import angular_distance

MAG_LIMIT = 7.0


@dataclass
class StarCatalog:
    hip: np.ndarray
    ra: np.ndarray            # градусы
    dec: np.ndarray           # градусы
    mag: np.ndarray
    parallax: np.ndarray      # мс дуги
    pm_ra: np.ndarray         # мс дуги/год (с учётом cos δ)
    pm_dec: np.ndarray

    def __len__(self) -> int:
        return len(self.hip)


def _float(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def parse_hip_main(lines: Iterable[str], mag_limit: float = MAG_LIMIT) -> StarCatalog:
    rows = []
    for line in lines:
        f = line.split("|")
        if len(f) < 14:
            continue
        try:
            hip = int(f[1])
        except ValueError:
            continue
        mag, ra, dec = _float(f[5]), _float(f[8]), _float(f[9])
        if mag is None or ra is None or dec is None or mag > mag_limit:
            continue
        if not (0.0 <= ra < 360.0 and -90.0 <= dec <= 90.0):
            continue
        rows.append((hip, ra, dec, mag, _float(f[11]) or 0.0, _float(f[12]) or 0.0, _float(f[13]) or 0.0))
    if len(rows) < 5000:
        raise ValueError("Каталог Hipparcos распознан неверно: слишком мало звёзд "
                         f"({len(rows)}). Возможно, изменился формат файла.")
    a = np.array(rows, dtype=float)
    if a[:, 3].min() > -1.0:
        raise ValueError("Каталог Hipparcos распознан неверно: нет самой яркой звезды (Сириус).")
    return StarCatalog(a[:, 0].astype(int), a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5], a[:, 6])


_VIZIER_ALIASES = {
    "hip": ("HIP",), "mag": ("Vmag",), "ra": ("RAICRS", "RAdeg", "_RAJ2000", "RA_ICRS"),
    "dec": ("DEICRS", "DEdeg", "_DEJ2000", "DE_ICRS"), "plx": ("Plx",), "pmra": ("pmRA",), "pmde": ("pmDE",)}


def parse_vizier_tsv(text: str, mag_limit: float = MAG_LIMIT) -> StarCatalog:
    """Разбор ответа VizieR (asu-tsv) для каталога I/239/hip_main.

    Строки с «#» — комментарии; первая строка без «#» — названия столбцов, далее строка единиц и
    строка из «---», затем данные, разделённые табуляцией. Названия столбцов ищутся по списку
    допустимых вариантов; если нужных нет — ValueError.
    """
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    if len(lines) < 4:
        raise ValueError("Ответ VizieR не содержит данных.")
    header = [h.strip() for h in lines[0].split("\t")]
    index = {}
    for key, names in _VIZIER_ALIASES.items():
        found = next((header.index(n) for n in names if n in header), None)
        if found is None and key in ("hip", "mag", "ra", "dec"):
            raise ValueError(f"В ответе VizieR нет столбца {names[0]} (есть: {', '.join(header[:12])}).")
        index[key] = found
    rows = []
    for line in lines[1:]:
        f = line.split("\t")
        if len(f) < len(header):
            continue
        try:
            hip = int(f[index["hip"]])
        except ValueError:
            continue                    # строка единиц, разделитель «---» и т. п.
        mag, ra, dec = _float(f[index["mag"]]), _float(f[index["ra"]]), _float(f[index["dec"]])
        if mag is None or ra is None or dec is None or mag > mag_limit:
            continue
        if not (0.0 <= ra < 360.0 and -90.0 <= dec <= 90.0):
            continue

        def opt(key):
            return (_float(f[index[key]]) or 0.0) if index[key] is not None else 0.0
        rows.append((hip, ra, dec, mag, opt("plx"), opt("pmra"), opt("pmde")))
    if len(rows) < 5000:
        raise ValueError(f"Каталог VizieR распознан неверно: слишком мало звёзд ({len(rows)}).")
    a = np.array(rows, dtype=float)
    if a[:, 3].min() > -1.0:
        raise ValueError("Каталог VizieR распознан неверно: нет самой яркой звезды (Сириус).")
    return StarCatalog(a[:, 0].astype(int), a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5], a[:, 6])


def parse_hip_main_file(path: Path, mag_limit: float = MAG_LIMIT) -> StarCatalog:
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="ascii", errors="replace") as fh:
        return parse_hip_main(fh, mag_limit)


def save_catalog(cat: StarCatalog, path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, hip=cat.hip, ra=cat.ra, dec=cat.dec, mag=cat.mag,
                        parallax=cat.parallax, pm_ra=cat.pm_ra, pm_dec=cat.pm_dec)


def load_catalog(path: Path) -> StarCatalog:
    with np.load(path) as z:
        return StarCatalog(z["hip"], z["ra"], z["dec"], z["mag"], z["parallax"], z["pm_ra"], z["pm_dec"])


# Название, RA (ч), Dec (°), V — округлённые справочные значения для сопоставления.
NAMED_STARS = [
    ("Сириус", 6.752, -16.716, -1.46), ("Канопус", 6.399, -52.696, -0.74),
    ("Арктур", 14.261, 19.182, -0.05), ("Ригель Кентавра", 14.660, -60.835, -0.01),
    ("Вега", 18.616, 38.784, 0.03), ("Капелла", 5.278, 45.998, 0.08),
    ("Ригель", 5.242, -8.202, 0.13), ("Процион", 7.655, 5.225, 0.34),
    ("Бетельгейзе", 5.919, 7.407, 0.5), ("Ахернар", 1.629, -57.237, 0.46),
    ("Хадар", 14.064, -60.373, 0.61), ("Альтаир", 19.846, 8.868, 0.77),
    ("Акрукс", 12.443, -63.099, 0.77), ("Альдебаран", 4.599, 16.509, 0.85),
    ("Антарес", 16.490, -26.432, 1.06), ("Спика", 13.420, -11.161, 0.98),
    ("Поллукс", 7.755, 28.026, 1.14), ("Фомальгаут", 22.961, -29.622, 1.16),
    ("Денеб", 20.690, 45.280, 1.25), ("Регул", 10.140, 11.967, 1.35),
    ("Кастор", 7.577, 31.888, 1.58), ("Беллатрикс", 5.419, 6.350, 1.64),
    ("Альнилам", 5.604, -1.202, 1.69), ("Альнитак", 5.679, -1.943, 1.74),
    ("Минтака", 5.533, -0.299, 2.23), ("Саиф", 5.796, -9.670, 2.06),
    ("Дубхе", 11.062, 61.751, 1.79), ("Мерак", 11.031, 56.382, 2.37),
    ("Фекда", 11.897, 53.695, 2.44), ("Мегрец", 12.257, 57.033, 3.31),
    ("Алиот", 12.900, 55.960, 1.77), ("Мицар", 13.399, 54.925, 2.04),
    ("Алькаид", 13.792, 49.313, 1.86), ("Полярная", 2.530, 89.264, 1.98),
    ("Мирфак", 3.405, 49.861, 1.79), ("Алголь", 3.136, 40.956, 2.1),
    ("Альфард", 9.460, -8.659, 1.98), ("Денебола", 11.818, 14.572, 2.14),
    ("Альфекка", 15.578, 26.715, 2.23), ("Рас-Альхаге", 17.582, 12.560, 2.08),
    ("Кохаб", 14.845, 74.156, 2.08), ("Маркаб", 23.079, 15.205, 2.49),
    ("Шеат", 23.063, 28.083, 2.42), ("Хамаль", 2.120, 23.462, 2.0),
    ("Садр", 20.370, 40.257, 2.23), ("Эльнат", 5.438, 28.608, 1.65),
    ("Адхара", 6.977, -28.972, 1.5), ("Шаула", 17.560, -37.104, 1.62),
    ("Везен", 7.140, -26.393, 1.84), ("Мимоза", 12.795, -59.689, 1.25),
    ("Гакрукс", 12.519, -57.113, 1.6), ("Альхена", 6.629, 16.399, 1.93),
    ("Шедар", 0.675, 56.537, 2.24), ("Дифда", 0.726, -17.987, 2.04),
    ("Нунки", 18.921, -26.297, 2.05), ("Альферац", 0.139, 29.091, 2.06),
    ("Эниф", 21.736, 9.875, 2.39), ("Менкар", 3.038, 4.090, 2.5),
    ("Каф", 0.153, 59.150, 2.27), ("γ Кассиопеи", 0.945, 60.717, 2.47),
    ("Рукбах", 1.430, 60.235, 2.68), ("Сегин", 1.907, 63.670, 3.37),
    ("Альбирео", 19.512, 27.960, 3.18), ("ε Лебедя", 20.770, 33.970, 2.46),
    ("δ Лебедя", 19.750, 45.131, 2.87), ("Имай", 12.252, -58.749, 2.80),
    ("Альгениб", 0.220, 15.184, 2.83),
]

# Цепочки линий астеризмов (названия из NAMED_STARS). Упрощённые рисунки, не границы созвездий.
ASTERISMS = {
    "Орион": [["Беллатрикс", "Бетельгейзе", "Альнитак", "Альнилам", "Минтака", "Беллатрикс"],
              ["Альнитак", "Саиф"], ["Минтака", "Ригель"]],
    "Большая Медведица": [["Дубхе", "Мерак", "Фекда", "Мегрец", "Дубхе"],
                          ["Мегрец", "Алиот", "Мицар", "Алькаид"]],
    "Кассиопея": [["Каф", "Шедар", "γ Кассиопеи", "Рукбах", "Сегин"]],
    "Лебедь": [["Денеб", "Садр", "Альбирео"], ["ε Лебедя", "Садр", "δ Лебедя"]],
    "Летний треугольник": [["Вега", "Денеб", "Альтаир", "Вега"]],
    "Южный Крест": [["Акрукс", "Гакрукс"], ["Мимоза", "Имай"]],
    "Пегас (квадрат)": [["Маркаб", "Шеат", "Альферац", "Альгениб", "Маркаб"]],
}

MATCH_RADIUS_DEG = 0.6
MATCH_MAG_TOLERANCE = 0.9


def match_named_stars(cat: StarCatalog) -> dict[str, int]:
    """Название -> индекс звезды в каталоге (только уверенные совпадения)."""
    result: dict[str, int] = {}
    used: set[int] = set()
    for name, ra_h, dec, v in NAMED_STARS:
        sep = angular_distance(cat.ra, cat.dec, ra_h * 15.0, dec)
        candidates = np.where((sep <= MATCH_RADIUS_DEG) & (np.abs(cat.mag - v) <= MATCH_MAG_TOLERANCE))[0]
        if not len(candidates):
            continue
        best = int(candidates[np.argmin(sep[candidates])])
        if best in used:
            continue
        used.add(best)
        result[name] = best
    return result


def asterism_segments(names: dict[str, int]) -> list[tuple[str, int, int]]:
    """Отрезки линий (название астеризма, индекс звезды A, индекс звезды B) для найденных звёзд."""
    segments = []
    for label, chains in ASTERISMS.items():
        for chain in chains:
            for a, b in zip(chain, chain[1:]):
                if a in names and b in names:
                    segments.append((label, names[a], names[b]))
    return segments
