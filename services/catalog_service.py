"""Каталог небесных объектов: загрузка OpenNGC, хранение в SQLite, поиск и фильтры."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import config
from api import catalog_api
from api.http_client import ApiError
from astronomy.catalog_names import MESSIER_RU
from astronomy.constellations_ru import constellation_ru
from database.db_manager import DatabaseManager

log = logging.getLogger(__name__)

SORTS = {"magnitude": "по блеску", "designation": "по обозначению", "size": "по размеру"}


@dataclass
class CatalogStatus:
    count: int
    last_update: str | None


class CatalogService:
    def __init__(self, db: DatabaseManager, directory: Path | None = None):
        self.db = db
        self.directory = Path(directory) if directory else config.DATA_DIR / "catalogs"

    # ---- загрузка ---------------------------------------------------------------
    def status(self) -> CatalogStatus:
        return CatalogStatus(self.db.count_objects(), self.db.last_successful_update("catalog"))

    def import_texts(self, texts: list[str]) -> int:
        objects = catalog_api.merge_files(texts)
        for obj in objects:
            if obj["messier"] in MESSIER_RU:
                obj["name_ru"] = MESSIER_RU[obj["messier"]]
        return self.db.replace_objects(catalog_api.SOURCE_NAME, objects)

    def import_files(self, paths: list[Path]) -> int:
        return self.import_texts([Path(p).read_text(encoding="utf-8", errors="replace") for p in paths])

    def download(self, progress: Callable[[str], None] | None = None) -> int:
        started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        try:
            paths = catalog_api.download_files(self.directory, progress)
            count = self.import_files(paths)
        except (ApiError, OSError) as exc:
            self.db.log_update("catalog", "error", str(exc), started)
            raise
        self.db.log_update("catalog", "ok", f"OpenNGC: {count} объектов", started)
        return count

    def import_local_if_present(self) -> int:
        """Импорт ранее скачанных файлов (например, после очистки БД). 0, если файлов нет."""
        main = self.directory / catalog_api.FILES[0]
        if not main.is_file():
            return 0
        paths = [p for p in (self.directory / n for n in catalog_api.FILES) if p.is_file()]
        return self.import_files(paths)

    # ---- поиск -------------------------------------------------------------------
    def constellations(self) -> list[tuple[str, str]]:
        """[(аббревиатура, русское название)] для имеющихся в каталоге созвездий."""
        used = {o["constellation"] for o in self.db.list_objects() if o["constellation"]}
        return sorted(((abbr, constellation_ru(abbr)) for abbr in used), key=lambda x: x[1])

    def search(self, query: str = "", types: list[str] | None = None, constellation: str | None = None,
               messier_only: bool = False, max_magnitude: float | None = None,
               sort: str = "magnitude", limit: int = 500) -> list[dict]:
        rows = self.db.list_objects(types, constellation, messier_only, max_magnitude)
        needle = " ".join(query.casefold().split())
        if needle:
            compact = needle.replace(" ", "")

            def matches(o: dict) -> bool:
                haystack = [o["catalog_id"].casefold(), (o["name"] or "").casefold(),
                            (o["name_ru"] or "").casefold()]
                if o["messier"]:
                    haystack.append(f"m{o['messier']}")
                    haystack.append(f"m {o['messier']}")
                return any(needle in h or compact == h.replace(" ", "") for h in haystack)

            rows = [o for o in rows if matches(o)]
        if sort == "designation":
            rows.sort(key=lambda o: (o["catalog"] or "", _designation_number(o["catalog_id"]), o["catalog_id"]))
        elif sort == "size":
            rows.sort(key=lambda o: -(o["size_arcmin"] or 0.0))
        else:
            rows.sort(key=lambda o: (o["magnitude"] is None, o["magnitude"] or 0.0))
        return rows[:limit]


def _designation_number(catalog_id: str) -> int:
    digits = "".join(ch for ch in catalog_id.split(" ")[-1] if ch.isdigit())
    return int(digits) if digits else 0


def display_designation(o: dict) -> str:
    return f"M {o['messier']} / {o['catalog_id']}" if o.get("messier") else o["catalog_id"]


def object_links(o: dict) -> list[tuple[str, str]]:
    """Ссылки на внешние сведения об объекте (SIMBAD, Aladin)."""
    ident = f"M {o['messier']}" if o.get("messier") else o["catalog_id"]
    from urllib.parse import quote
    return [
        ("SIMBAD", "https://simbad.cds.unistra.fr/simbad/sim-id?Ident=" + quote(ident)),
        ("Aladin Lite (снимки неба)",
         f"https://aladin.cds.unistra.fr/AladinLite/?target={o['ra_deg']:.5f}%20{o['dec_deg']:+.5f}&fov=1"),
    ]
