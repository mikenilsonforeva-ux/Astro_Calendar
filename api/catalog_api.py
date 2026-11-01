"""Каталог небесных объектов OpenNGC (NGC, IC и дополнения: объекты Мессье и др.).

Источник: https://github.com/mattiaverga/OpenNGC (лицензия CC-BY-SA 4.0 — при показе данных
необходима ссылка на источник). Файлы CSV разделены «;», столбцы разбираются по названиям,
а не по номерам; если нужных столбцов нет, бросается ApiError с понятным сообщением.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Callable

from api.http_client import ApiError, HttpClient

BASE = "https://raw.githubusercontent.com/mattiaverga/OpenNGC/master/database_files/"
FILES = ("NGC.csv", "addendum.csv")
SOURCE_NAME = "OpenNGC"
ATTRIBUTION = "Каталог: OpenNGC (M. Verga), CC-BY-SA 4.0"

# Типы OpenNGC -> (ключ, русское название). Дубликаты и несуществующие объекты не импортируются.
TYPES = {
    "*": ("star", "Звезда"), "**": ("double_star", "Двойная звезда"),
    "*Ass": ("asterism", "Звёздная ассоциация"), "OCl": ("open_cluster", "Рассеянное скопление"),
    "GCl": ("globular_cluster", "Шаровое скопление"), "Cl+N": ("cluster_nebula", "Скопление с туманностью"),
    "G": ("galaxy", "Галактика"), "GPair": ("galaxy_group", "Пара галактик"),
    "GTrpl": ("galaxy_group", "Тройка галактик"), "GGroup": ("galaxy_group", "Группа галактик"),
    "PN": ("planetary_nebula", "Планетарная туманность"), "HII": ("emission_nebula", "Область H II"),
    "DrkN": ("dark_nebula", "Тёмная туманность"), "EmN": ("emission_nebula", "Эмиссионная туманность"),
    "Neb": ("nebula", "Туманность"), "RfN": ("reflection_nebula", "Отражательная туманность"),
    "SNR": ("supernova_remnant", "Остаток сверхновой"), "Nova": ("nova", "Новая звезда"),
    "Other": ("other", "Другое"),
}
TYPE_NAMES_RU = {key: ru for key, ru in TYPES.values()}
SKIPPED_TYPES = {"Dup", "NonEx"}
REQUIRED = ("Name", "Type", "RA", "Dec")

_NAME = re.compile(r"^(NGC|IC)\s*0*(\d+)([A-Za-z]*)$")


def normalize_name(raw: str) -> tuple[str, str]:
    """'NGC0224' -> ('NGC 224', 'NGC'); прочие обозначения возвращаются как есть."""
    raw = raw.strip()
    m = _NAME.match(raw)
    if m:
        return f"{m.group(1)} {m.group(2)}{m.group(3)}", m.group(1)
    return raw, re.sub(r"[\d\s].*$", "", raw) or "Другой"


def parse_ra(value: str) -> float | None:
    """'00:42:44.33' (часы) -> градусы."""
    try:
        h, m, s = (float(x) for x in value.strip().split(":"))
    except ValueError:
        return None
    if not (0 <= h < 24 and 0 <= m < 60 and 0 <= s < 60):
        return None
    return (h + m / 60.0 + s / 3600.0) * 15.0


def parse_dec(value: str) -> float | None:
    """'+41:16:07.5' -> градусы."""
    text = value.strip()
    if not text:
        return None
    sign = -1.0 if text.startswith("-") else 1.0
    try:
        d, m, s = (float(x) for x in text.lstrip("+-").split(":"))
    except ValueError:
        return None
    if not (0 <= d <= 90 and 0 <= m < 60 and 0 <= s < 60):
        return None
    return sign * (d + m / 60.0 + s / 3600.0)


def _num(value: str | None) -> float | None:
    try:
        number = float((value or "").strip())
    except ValueError:
        return None
    return number if number == number else None


def parse_openngc(text: str) -> list[dict]:
    """Разбирает CSV OpenNGC в список словарей для таблицы celestial_objects."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")), delimiter=";")
    missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
    if missing:
        raise ApiError(f"Формат каталога не распознан: нет столбцов {', '.join(missing)}.")
    objects = []
    for row in reader:
        type_code = (row.get("Type") or "").strip()
        if type_code in SKIPPED_TYPES or type_code not in TYPES:
            continue
        ra, dec = parse_ra(row.get("RA") or ""), parse_dec(row.get("Dec") or "")
        if ra is None or dec is None:
            continue
        catalog_id, catalog = normalize_name(row.get("Name") or "")
        if not catalog_id:
            continue
        messier = None
        m_col = (row.get("M") or "").strip()
        if m_col.isdigit():
            messier = int(m_col)
        magnitude = _num(row.get("V-Mag"))
        if magnitude is None:
            magnitude = _num(row.get("B-Mag"))
        common = [n.strip() for n in (row.get("Common names") or "").split(",") if n.strip()]
        objects.append({
            "catalog_id": catalog_id, "catalog": catalog, "name": common[0] if common else "",
            "object_type": TYPES[type_code][0], "ra_deg": ra, "dec_deg": dec,
            "magnitude": magnitude, "size_arcmin": _num(row.get("MajAx")),
            "size_minor_arcmin": _num(row.get("MinAx")),
            "constellation": (row.get("Const") or "").strip() or None,
            "distance_ly": None, "description": None, "image_url": None,
            "source": SOURCE_NAME, "messier": messier,
        })
    if not objects:
        raise ApiError("В каталоге не найдено ни одного объекта.")
    return objects


def merge_files(texts: list[str]) -> list[dict]:
    """Объединяет файлы (NGC.csv + addendum.csv); при совпадении обозначения побеждает первый."""
    merged: dict[str, dict] = {}
    for text in texts:
        for obj in parse_openngc(text):
            merged.setdefault(obj["catalog_id"], obj)
    return list(merged.values())


def download_files(dest_dir: Path, progress: Callable[[str], None] | None = None,
                   client: HttpClient | None = None) -> list[Path]:
    client = client or HttpClient(read_timeout=60)
    paths = []
    for name in FILES:
        if progress:
            progress(f"Загрузка {name}…")
        try:
            paths.append(client.download(BASE + name, Path(dest_dir) / name, min_size=1000))
        except ApiError:
            if name == FILES[0]:        # основной файл обязателен, дополнения — нет
                raise
    return paths
