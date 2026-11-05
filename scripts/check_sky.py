"""Диагностика карты звёздного неба без запуска окна приложения.

Запуск:  QT_QPA_PLATFORM=offscreen python scripts/check_sky.py [ЧЧ:ММ по Москве, по умолчанию сейчас]
Строит снимок неба для Москвы на реальных данных (эфемериды, каталог звёзд), рисует карту
в файл sky_check.png и печатает: сколько звёзд и объектов попало в снимок и на рисунок, цвета
пикселей и ошибки слоёв. Пришлите вывод и картинку, если карта выглядит неправильно.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import config  # noqa: E402
from astronomy.context import AstroContext  # noqa: E402
from astronomy.sky_snapshot import build_snapshot  # noqa: E402
from database.db_manager import DatabaseManager  # noqa: E402
from services.star_service import StarService  # noqa: E402
from ui.sky_widget import SkyMapWidget  # noqa: E402


def main() -> int:
    path = config.find_ephemeris_file()
    if path is None:
        print("НЕТ файла эфемерид (de440s.bsp) — карту построить нельзя.")
        return 1
    db = DatabaseManager(config.DB_PATH)
    stars = StarService(db)
    print("Каталог звёзд:", "есть" if stars.is_available() else "НЕТ (скачайте или импортируйте hip_main.dat.gz)")
    if not stars.is_available():
        return 1
    ctx = AstroContext.create(55.7558, 37.6173, 150, "Europe/Moscow", path, "Москва")
    when = datetime.now(timezone.utc)
    if len(sys.argv) > 1:
        hh, mm = (int(x) for x in sys.argv[1].split(":"))
        local = ctx.local(when).replace(hour=hh, minute=mm, second=0, microsecond=0)
        when = local.astimezone(timezone.utc)
    cat = stars.load()
    print(f"Каталог: {len(cat)} звёзд, блеск {cat.mag.min():.2f}…{cat.mag.max():.2f}, "
          f"RA {cat.ra.min():.1f}…{cat.ra.max():.1f}, Dec {cat.dec.min():.1f}…{cat.dec.max():.1f}")
    deep = [o for o in db.list_objects(max_magnitude=9.0) if o.get("ra_deg") is not None]
    snap = build_snapshot(ctx, when, cat, stars.constellation_centers(ctx), deep)
    print(f"Момент: {ctx.local(when):%d.%m.%Y %H:%M}, Солнце {snap.sun_alt:+.1f}°")
    above = int((snap.star_alt > 0).sum())
    print(f"Звёзд в снимке: {len(snap.star_mag)}, над горизонтом: {above}, ярче 3.8ᵐ над горизонтом: "
          f"{int(((snap.star_alt > 0) & (snap.star_mag <= 3.8)).sum())}")
    print("Тела:", [(b.name, round(b.alt, 1)) for b in snap.bodies])
    print("Объектов каталога:", len(snap.deep_sky), "; фигур созвездий:", len(snap.segments),
          "; подписей созвездий:", len(snap.const_labels))

    app = QApplication.instance() or QApplication([])
    for mode in ("horizontal", "equatorial"):
        widget = SkyMapWidget()
        widget.resize(800, 800)
        widget.set_snapshot(snap)
        widget.set_mode(mode)
        image = widget.grab().toImage()
        out = Path(f"sky_check_{mode}.png")
        image.save(str(out))
        w, h = image.width(), image.height()
        samples = {"центр": image.pixelColor(w // 2, h // 2), "угол": image.pixelColor(5, 5),
                   "у края круга": image.pixelColor(w // 2, 30)}
        colors = ", ".join(f"{k}=({c.red()},{c.green()},{c.blue()})" for k, c in samples.items())
        pixels = np.frombuffer(image.constBits(), dtype=np.uint8).reshape(h, w, 4)[:, :, :3]
        white = float((pixels.min(axis=2) > 235).mean()) * 100
        print(f"[{mode}] картинка {out} ({w}×{h}); цвета: {colors}; почти белых пикселей: {white:.1f}%; "
              f"объектов для клика: {len(widget._hits)}; слои с ошибкой: {sorted(widget._failed_layers) or 'нет'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
