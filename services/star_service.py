"""Звёздные данные для карты неба: загрузка Hipparcos, локальный кэш, центры созвездий."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np

import config
from api.http_client import ApiError, HttpClient
from astronomy import stars
from astronomy.context import AstroContext
from database.db_manager import DatabaseManager

log = logging.getLogger(__name__)

FALLBACK_URLS = ("https://cdsarc.cds.unistra.fr/ftp/cats/I/239/hip_main.dat.gz",
                 "https://cdsarc.u-strasbg.fr/ftp/cats/I/239/hip_main.dat.gz")
VIZIER_QUERY = {"-source": "I/239/hip_main", "-out.all": "1", "-out.max": "unlimited",
                "Vmag": f"<{stars.MAG_LIMIT + 0.1}"}
VIZIER_URLS = ("https://vizier.cfa.harvard.edu/viz-bin/asu-tsv", "https://vizier.cds.unistra.fr/viz-bin/asu-tsv")
VIZIER_TIMEOUT = (15, 300)     # VizieR готовит выборку долго: ждём ответ до 5 минут
LOCAL_NAMES = ("hip_main.dat.gz", "hip_main.dat")
ATTRIBUTION = ("Звёзды: каталог Hipparcos (ESA 1997, CDS I/239), звёзды до 7ᵐ. "
               "Млечный Путь и рисунки созвездий — схематичные.")


def _hipparcos_urls() -> list[str]:
    urls = []
    try:                      # адрес, который использует установленная версия Skyfield
        from skyfield.data import hipparcos
        urls.append(hipparcos.URL)
    except Exception:
        pass
    return urls + [u for u in FALLBACK_URLS if u not in urls]


class StarService:
    def __init__(self, db: DatabaseManager, directory: Path | None = None):
        self.db = db
        self.directory = Path(directory) if directory else config.DATA_DIR / "stars"
        self._catalog: stars.StarCatalog | None = None

    @property
    def catalog_path(self) -> Path:
        return self.directory / "hipparcos_mag7.npz"

    @property
    def centers_path(self) -> Path:
        return self.directory / "constellation_centers.json"

    def is_available(self) -> bool:
        return self.catalog_path.is_file()

    def load(self) -> stars.StarCatalog:
        if self._catalog is None:
            if not self.is_available():
                raise FileNotFoundError("Звёздный каталог не загружен.")
            self._catalog = stars.load_catalog(self.catalog_path)
        return self._catalog

    # ---- загрузка --------------------------------------------------------------------
    def download(self, progress: Callable[[str], None] | None = None,
                 client: HttpClient | None = None) -> int:
        started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        client = client or HttpClient(connect_timeout=15, read_timeout=60, retries=2)
        raw = self.directory / "hip_main.dat.gz"
        self._last_error = None
        try:
            cat = self._from_local_file()
            if cat is None:
                cat = self._from_archive(client, raw, progress)
            if cat is None:
                cat = self._from_vizier(client, progress)
            if cat is None:
                raise ApiError(f"Не удалось скачать каталог Hipparcos: {self._last_error}. "
                               f"Можно скачать файл вручную и положить его в {self.directory} "
                               "(hip_main.dat.gz) либо выбрать кнопкой «Импортировать файл».")
            stars.save_catalog(cat, self.catalog_path)
            self._catalog = cat
        except (ApiError, OSError) as exc:
            self.db.log_update("stars", "error", str(exc), started)
            raise
        self.db.log_update("stars", "ok", f"Hipparcos: {len(cat)} звёзд до {stars.MAG_LIMIT}ᵐ", started)
        return len(cat)

    _last_error: Exception | None = None

    def _from_local_file(self):
        """Файл, который пользователь положил в папку каталога вручную."""
        for name in LOCAL_NAMES:
            path = self.directory / name
            if path.is_file():
                try:
                    return stars.parse_hip_main_file(path)
                except (ValueError, OSError) as exc:
                    raise ApiError(f"Файл {path.name} не удалось разобрать: {exc}") from exc
        return None

    def _from_archive(self, client, raw: Path, progress):
        """Полный каталог Hipparcos (≈ 50 МБ) с серверов CDS."""
        for url in _hipparcos_urls():
            try:
                if progress:
                    progress("Загрузка каталога Hipparcos (≈ 50 МБ)…")
                client.download(url, raw, min_size=10_000_000)
            except ApiError as exc:
                self._last_error = exc
                log.warning("Hipparcos: %s недоступен: %s", url, exc)
                continue
            try:
                return stars.parse_hip_main_file(raw)
            except ValueError as exc:
                raise ApiError(str(exc)) from exc
            finally:
                raw.unlink(missing_ok=True)       # исходный файл больше не нужен
        return None

    def _from_vizier(self, client, progress):
        """Запасной путь: запрос к VizieR только на звёзды ярче 7ᵐ (около 1 МБ)."""
        for url in VIZIER_URLS:
            try:
                if progress:
                    progress("Запрос звёзд ярче 7ᵐ из VizieR…")
                text = client.get_text(url, VIZIER_QUERY, timeout=VIZIER_TIMEOUT)
                return stars.parse_vizier_tsv(text)
            except (ApiError, ValueError) as exc:
                self._last_error = exc
                log.warning("VizieR %s: %s", url, exc)
        return None

    def import_file(self, path: str | Path) -> int:
        """Импорт файла hip_main.dat / hip_main.dat.gz, скачанного пользователем вручную."""
        started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        try:
            cat = stars.parse_hip_main_file(Path(path))
            stars.save_catalog(cat, self.catalog_path)
        except (ValueError, OSError) as exc:
            self.db.log_update("stars", "error", str(exc), started)
            raise ApiError(f"Не удалось импортировать файл: {exc}") from exc
        self._catalog = cat
        self.db.log_update("stars", "ok", f"Hipparcos (импорт файла): {len(cat)} звёзд", started)
        return len(cat)

    # ---- центры созвездий ------------------------------------------------------------------
    def constellation_centers(self, ctx: AstroContext) -> dict[str, tuple[float, float]]:
        """Аббревиатура -> (RA, Dec) J2000 условного центра созвездия (кэшируется на диске)."""
        if self.centers_path.is_file():
            try:
                data = json.loads(self.centers_path.read_text(encoding="utf-8"))
                return {k: (v[0], v[1]) for k, v in data.items()}
            except (ValueError, OSError):
                pass
        centers = compute_constellation_centers(ctx)
        try:
            self.centers_path.parent.mkdir(parents=True, exist_ok=True)
            self.centers_path.write_text(json.dumps(centers), encoding="utf-8")
        except OSError:
            log.warning("Не удалось сохранить центры созвездий")
        return centers


def compute_constellation_centers(ctx: AstroContext, step_deg: float = 3.0) -> dict[str, tuple[float, float]]:
    """Центр созвездия — среднее направление точек сетки, попавших в его границы (карта Skyfield)."""
    from skyfield.positionlib import position_of_radec
    ra = np.arange(0.0, 360.0, step_deg) + step_deg / 2
    dec = np.arange(-90.0 + step_deg / 2, 90.0, step_deg)
    grid_ra, grid_dec = np.meshgrid(ra, dec)
    flat_ra, flat_dec = grid_ra.ravel(), grid_dec.ravel()
    lookup = ctx.constellation_at
    try:
        abbr = np.asarray(lookup(position_of_radec(flat_ra / 15.0, flat_dec))).ravel()
        if len(abbr) != len(flat_ra):
            raise ValueError("не векторизовано")
    except Exception:
        abbr = np.array([lookup(position_of_radec(r / 15.0, d)) for r, d in zip(flat_ra, flat_dec)])
    r, d = np.radians(flat_ra), np.radians(flat_dec)
    vec = np.stack([np.cos(d) * np.cos(r), np.cos(d) * np.sin(r), np.sin(d)], axis=1)
    centers = {}
    for name in np.unique(abbr):
        mean = vec[abbr == name].mean(axis=0)
        norm = np.linalg.norm(mean)
        if norm < 1e-6:
            continue
        mean /= norm
        centers[str(name)] = (float(np.degrees(np.arctan2(mean[1], mean[0])) % 360.0),
                              float(np.degrees(np.arcsin(mean[2]))))
    return centers
