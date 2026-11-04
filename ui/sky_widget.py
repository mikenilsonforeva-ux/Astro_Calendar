"""Виджет интерактивной карты неба (рисование QPainter, стереографическая проекция)."""
from __future__ import annotations

import logging
import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from astronomy import skymap
from astronomy.coordinates import compass_point, format_dms, format_hms
from astronomy.sky_snapshot import PLANET_COLORS, SkySnapshot

log = logging.getLogger(__name__)
MODES = ("horizontal", "equatorial")
DEFAULT_LAYERS = {
    "star_names": True, "asterisms": True, "constellation_names": True, "bodies": True,
    "milky_way": True, "ecliptic": True, "grid": True, "deep_sky": True, "below_horizon": False,
    "daylight_stars": True,
}
MIN_FOV, MAX_FOV = 5.0, 175.0


def sky_color(sun_alt: float) -> QColor:
    """Цвет неба по высоте Солнца: день → сумерки → ночь."""
    keys = [(-18.0, (4, 6, 16)), (-12.0, (14, 22, 52)), (-6.0, (44, 70, 130)),
            (-0.8, (96, 130, 190)), (10.0, (120, 175, 235))]
    if sun_alt <= keys[0][0]:
        return QColor(*keys[0][1])
    if sun_alt >= keys[-1][0]:
        return QColor(*keys[-1][1])
    for (a0, c0), (a1, c1) in zip(keys, keys[1:]):
        if a0 <= sun_alt <= a1:
            t = (sun_alt - a0) / (a1 - a0)
            return QColor(*(int(c0[i] + (c1[i] - c0[i]) * t) for i in range(3)))
    return QColor(*keys[0][1])


def paint_moon(painter: QPainter, cx: float, cy: float, r: float, phase_angle: float,
               mirrored: bool = False) -> None:
    """Диск Луны с освещённой частью (фазовый угол 0° — новолуние, 180° — полнолуние)."""
    painter.save()
    if mirrored:
        painter.translate(2 * cx, 0)
        painter.scale(-1, 1)
    disc = QPainterPath()
    disc.addEllipse(QPointF(cx, cy), r, r)
    painter.fillPath(disc, QColor(55, 58, 70))
    c = math.cos(math.radians(phase_angle))
    half = QPainterPath()
    if phase_angle % 360.0 < 180.0:
        half.addRect(QRectF(cx, cy - r, r, 2 * r))
    else:
        half.addRect(QRectF(cx - r, cy - r, r, 2 * r))
    lit = disc.intersected(half)
    ellipse = QPainterPath()
    ellipse.addEllipse(QPointF(cx, cy), abs(c) * r, r)
    lit = lit.subtracted(ellipse) if c > 0 else lit.united(ellipse)
    painter.fillPath(lit.intersected(disc), QColor(240, 235, 210))
    painter.restore()


class SkyMapWidget(QWidget):
    object_selected = Signal(dict)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(420, 420)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(False)
        self.snapshot: SkySnapshot | None = None
        self.mode = "horizontal"
        self.layers = dict(DEFAULT_LAYERS)
        self.lon0, self.lat0, self.fov = 0.0, 90.0, 170.0
        self._drag_from: QPointF | None = None
        self._drag_center: tuple[float, float] = (0.0, 90.0)
        self._moved = False
        self._hits: list[tuple[float, float, dict]] = []
        self.selected_key: str | None = None
        self._grid_cache: dict[str, list] = {}
        self._failed_layers: set[str] = set()

    # ---- управление ------------------------------------------------------------------
    def set_snapshot(self, snapshot: SkySnapshot, keep_view: bool = True) -> None:
        first = self.snapshot is None
        self.snapshot = snapshot
        if first or not keep_view:
            self.reset_view()
        self.update()

    def set_mode(self, mode: str) -> None:
        if mode in MODES and mode != self.mode:
            self.mode = mode
            self.reset_view()

    def set_layer(self, name: str, enabled: bool) -> None:
        self.layers[name] = enabled
        self.update()

    def reset_view(self) -> None:
        """Взгляд в зенит (для экваториальной системы — на точку неба над головой)."""
        if self.mode == "horizontal" or self.snapshot is None:
            self.lon0, self.lat0 = 0.0, 90.0
        else:
            self.lon0, self.lat0 = self.snapshot.zenith_ra, self.snapshot.zenith_dec
        self.fov = 170.0
        self.update()

    def look_at_direction(self, azimuth: float, altitude: float = 35.0, fov: float = 100.0) -> None:
        """Взгляд в сторону света (только горизонтальная система)."""
        if self.mode != "horizontal":
            self.set_mode("horizontal")
        self.lon0, self.lat0, self.fov = azimuth, altitude, fov
        self.update()

    def zoom(self, factor: float) -> None:
        self.fov = max(MIN_FOV, min(MAX_FOV, self.fov * factor))
        self.update()

    # ---- геометрия -------------------------------------------------------------------------
    def _geometry(self) -> tuple[float, float, float, float, float]:
        cx, cy = self.width() / 2.0, self.height() / 2.0
        radius = max(10.0, min(self.width(), self.height()) / 2.0 - 6.0)
        r_max = 2.0 * math.tan(math.radians(self.fov) / 4.0)
        return cx, cy, radius, radius / r_max, r_max

    def _project(self, lon, lat):
        """(px, py, видимые) для массивов долгот/широт текущей системы."""
        cx, cy, radius, scale, r_max = self._geometry()
        sx, sy, valid = skymap.stereo_project(lon, lat, self.lon0, self.lat0)
        inside = valid & (np.hypot(sx, sy) <= r_max * 1.02)
        return cx + sx * scale, cy - sy * scale, inside, sx, sy, valid

    def _coords(self, which: str):
        """Массивы (lon, lat) объектов снимка в выбранной системе координат."""
        s = self.snapshot
        horizontal = self.mode == "horizontal"
        if which == "stars":
            return (s.star_az, s.star_alt) if horizontal else (s.star_ra, s.star_dec)
        raise KeyError(which)

    # ---- рисование -------------------------------------------------------------------------
    def paintEvent(self, _event) -> None:  # noqa: N802 (имя задано Qt)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(18, 18, 22))
        if self.snapshot is None:
            painter.setPen(QColor(200, 200, 200))
            painter.drawText(self.rect(), Qt.AlignCenter, "Нет данных для карты")
            return
        cx, cy, radius, scale, r_max = self._geometry()
        clip = QPainterPath()
        clip.addEllipse(QPointF(cx, cy), radius, radius)
        painter.setClipPath(clip)
        painter.fillPath(clip, sky_color(self.snapshot.sun_alt))
        self._hits = []
        night = float(np.clip((-self.snapshot.sun_alt - 2.0) / 10.0, 0.0, 1.0))   # видимость звёзд
        if self.layers["daylight_stars"]:
            night = max(night, 0.8)      # показывать звёзды и при светлом небе (в реальности их не видно)

        if self.layers["milky_way"] and night > 0:
            self._safe("milky_way", self._draw_milky_way, painter, scale, night)
        if self.layers["grid"]:
            self._safe("grid", self._draw_grid, painter, scale, r_max)
        if self.layers["ecliptic"]:
            self._safe("ecliptic", self._draw_ecliptic, painter, r_max)
        if self.layers["asterisms"] and night > 0:
            self._safe("asterisms", self._draw_asterisms, painter, night)
        if night > 0:
            self._safe("stars", self._draw_stars, painter, night)
        if self.layers["deep_sky"] and night > 0:
            self._safe("deep_sky", self._draw_deep_sky, painter)
        if self.layers["constellation_names"] and night > 0:
            self._safe("constellation_names", self._draw_constellation_names, painter)
        self._safe("horizon", self._draw_horizon, painter, r_max)
        if self.layers["bodies"]:
            self._safe("bodies", self._draw_bodies, painter)
        painter.setClipping(False)
        painter.setPen(QPen(QColor(150, 155, 170), 1.5))
        painter.drawEllipse(QPointF(cx, cy), radius, radius)
        painter.setPen(QColor(210, 210, 220))
        painter.drawText(QPointF(10, self.height() - 10),
                         f"Поле зрения {self.fov:.0f}° · "
                         f"{'горизонтальная' if self.mode == 'horizontal' else 'экваториальная'} система")

    def _draw_ecliptic(self, painter: QPainter, r_max: float) -> None:
        c = self.snapshot.ecliptic
        lon, lat = (c.az, c.alt) if self.mode == "horizontal" else (c.ra, c.dec)
        self._draw_curve(painter, lon, lat, QPen(QColor(230, 180, 70, 150), 1.2, Qt.DashLine), r_max)

    def _safe(self, name: str, draw, *args) -> None:
        """Ошибка в одном слое не должна обрывать рисование остальных; она пишется в лог."""
        try:
            draw(*args)
        except Exception:
            if name not in self._failed_layers:
                self._failed_layers.add(name)
                log.exception("Карта неба: ошибка при рисовании слоя «%s»", name)
            painter = args[0] if args and isinstance(args[0], QPainter) else None
            if painter is not None:
                painter.setBrush(Qt.NoBrush)

    def _draw_polyline(self, painter: QPainter, px, py, mask, sx, sy, r_max: float) -> None:
        for run in skymap.split_runs(mask, px, py, max_jump=self._geometry()[2] * 0.9):
            poly = QPolygonF([QPointF(float(x), float(y)) for x, y in zip(px[run], py[run])])
            painter.drawPolyline(poly)

    def _draw_curve(self, painter, lon, lat, pen: QPen, r_max: float) -> None:
        px, py, inside, sx, sy, valid = self._project(lon, lat)
        painter.setPen(pen)
        self._draw_polyline(painter, px, py, valid & (np.hypot(sx, sy) <= r_max * 1.6), sx, sy, r_max)

    def _draw_milky_way(self, painter: QPainter, scale: float, night: float) -> None:
        c = self.snapshot.milky_way
        lon, lat = (c.az, c.alt) if self.mode == "horizontal" else (c.ra, c.dec)
        px, py, inside, sx, sy, valid = self._project(lon, lat)
        cx, cy, radius, _, r_max = self._geometry()
        mask = valid & (np.hypot(sx, sy) <= r_max * 1.6)
        for half_width_deg, alpha in ((16, 14), (10, 18), (5, 22)):
            width = max(2.0, math.radians(half_width_deg * 2) * scale)
            pen = QPen(QColor(170, 190, 230, int(alpha * night)), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen)
            self._draw_polyline(painter, px, py, mask, sx, sy, r_max)

    def _grid_lines(self) -> list[tuple[np.ndarray, np.ndarray]]:
        key = self.mode
        if key in self._grid_cache:
            return self._grid_cache[key]
        lines = []
        t = np.linspace(0.0, 360.0, 181)
        if self.mode == "horizontal":
            for alt in (15.0, 30.0, 45.0, 60.0, 75.0):
                lines.append((t, np.full_like(t, alt)))
            lat = np.linspace(0.0, 90.0, 46)
            for az in range(0, 360, 30):
                lines.append((np.full_like(lat, float(az)), lat))
        else:
            for dec in (-60.0, -30.0, 0.0, 30.0, 60.0):
                lines.append((t, np.full_like(t, dec)))
            lat = np.linspace(-89.0, 89.0, 90)
            for ra in range(0, 360, 30):
                lines.append((np.full_like(lat, float(ra)), lat))
        self._grid_cache[key] = lines
        return lines

    def _draw_grid(self, painter: QPainter, scale: float, r_max: float) -> None:
        painter.setPen(QPen(QColor(255, 255, 255, 38), 1.0))
        for lon, lat in self._grid_lines():
            px, py, inside, sx, sy, valid = self._project(lon, lat)
            self._draw_polyline(painter, px, py, valid & (np.hypot(sx, sy) <= r_max * 1.6), sx, sy, r_max)

    def _visible_stars(self, night: float):
        s = self.snapshot
        lon, lat = self._coords("stars")
        px, py, inside, *_ = self._project(lon, lat)
        limit = skymap.star_limit_magnitude(self.fov)
        mask = inside & (s.star_mag <= limit)
        if self.mode == "horizontal" and not self.layers["below_horizon"]:
            mask &= s.star_alt > -0.5
        return px, py, mask

    def _draw_stars(self, painter: QPainter, night: float) -> None:
        s = self.snapshot
        px, py, mask = self._visible_stars(night)
        idx = np.where(mask)[0]
        radii = skymap.star_radius_px(s.star_mag[idx])
        below = s.star_alt[idx] < 0
        painter.setPen(Qt.NoPen)
        for i, r, is_below in zip(idx, radii, below):
            alpha = int(255 * night * (0.35 if is_below else 1.0))
            painter.setBrush(QColor(255, 255, 255, alpha))
            painter.drawEllipse(QPointF(float(px[i]), float(py[i])), float(r), float(r))
        names = {v: k for k, v in s.star_names.items()}
        if self.layers["star_names"] and self.fov < 140:
            font = QFont(painter.font())
            font.setPointSizeF(8.5)
            painter.setFont(font)
            painter.setPen(QColor(220, 225, 240, int(220 * night)))
            for i in idx:
                if int(i) in names and s.star_mag[i] < (2.2 if self.fov > 70 else 3.5):
                    painter.drawText(QPointF(float(px[i]) + 6, float(py[i]) - 5), names[int(i)])
        for i in idx[s.star_mag[idx] < 4.5] if len(idx) else []:
            name = names.get(int(i), f"HIP {int(s.star_hip[i])}")
            info = {"key": f"star{int(s.star_hip[i])}", "type": "star", "name": name, "kind": "Звезда",
                    "mag": float(s.star_mag[i]), "alt": float(s.star_alt[i]), "az": float(s.star_az[i]),
                    "ra": float(s.star_ra[i]), "dec": float(s.star_dec[i]), "hip": int(s.star_hip[i]),
                    "detail": f"HIP {int(s.star_hip[i])}"}
            if s.star_parallax is not None:
                info.update(plx=float(s.star_parallax[i]), pm_ra=float(s.star_pm_ra[i]),
                            pm_dec=float(s.star_pm_dec[i]))
            self._hits.append((float(px[i]), float(py[i]), info))

    def _draw_asterisms(self, painter: QPainter, night: float) -> None:
        s = self.snapshot
        lon, lat = self._coords("stars")
        px, py, inside, sx, sy, valid = self._project(lon, lat)
        painter.setPen(QPen(QColor(120, 170, 255, int(120 * night)), 1.1))
        for _, a, b in s.segments:
            if not (valid[a] and valid[b]):
                continue
            if self.mode == "horizontal" and not self.layers["below_horizon"] and (s.star_alt[a] < 0 and s.star_alt[b] < 0):
                continue
            painter.drawLine(QPointF(float(px[a]), float(py[a])), QPointF(float(px[b]), float(py[b])))

    def _draw_constellation_names(self, painter: QPainter) -> None:
        s = self.snapshot
        if not s.const_labels:
            return
        font = QFont(painter.font())
        font.setPointSizeF(8.0)
        font.setItalic(True)
        painter.setFont(font)
        painter.setPen(QColor(150, 190, 255, 150))
        lon = np.array([(c[4] if self.mode == "horizontal" else c[1]) for c in s.const_labels])
        lat = np.array([(c[3] if self.mode == "horizontal" else c[2]) for c in s.const_labels])
        px, py, inside, *_ = self._project(lon, lat)
        for i, c in enumerate(s.const_labels):
            if inside[i] and not (self.mode == "horizontal" and c[3] < -3.0 and not self.layers["below_horizon"]):
                painter.drawText(QPointF(float(px[i]) - 3 * len(c[0]), float(py[i])), c[0])

    def _draw_deep_sky(self, painter: QPainter) -> None:
        objs = self.snapshot.deep_sky
        if not objs or self.fov > 120:
            return
        lon = np.array([(o["az"] if self.mode == "horizontal" else o["ra_deg"]) for o in objs])
        lat = np.array([(o["alt"] if self.mode == "horizontal" else o["dec_deg"]) for o in objs])
        px, py, inside, *_ = self._project(lon, lat)
        painter.setBrush(Qt.NoBrush)
        font = QFont(painter.font())
        font.setPointSizeF(8.0)
        painter.setFont(font)
        for i, o in enumerate(objs):
            if not inside[i] or (self.mode == "horizontal" and o["alt"] < 0 and not self.layers["below_horizon"]):
                continue
            painter.setPen(QPen(QColor(255, 140, 200, 200), 1.2))
            painter.drawEllipse(QPointF(float(px[i]), float(py[i])), 5.0, 5.0)
            label = f"M{o['messier']}" if o.get("messier") else o["catalog_id"]
            painter.drawText(QPointF(float(px[i]) + 7, float(py[i]) + 4), label)
            self._hits.append((float(px[i]), float(py[i]), {
                "key": o["catalog_id"], "type": "deepsky", "object": o,
                "name": o.get("name_ru") or o.get("name") or label, "kind": "Объект глубокого космоса", "mag": o.get("magnitude"), "alt": o["alt"], "az": o["az"],
                "ra": o["ra_deg"], "dec": o["dec_deg"], "detail": f"{label} / {o['catalog_id']}"}))

    def _draw_horizon(self, painter: QPainter, r_max: float) -> None:
        s = self.snapshot
        if self.mode == "horizontal":
            az = np.linspace(0.0, 360.0, 181)
            self._draw_curve(painter, az, np.zeros_like(az), QPen(QColor(90, 200, 120, 220), 2.0), r_max)
            cardinals = [("С", 0.0, 0.0), ("В", 90.0, 0.0), ("Ю", 180.0, 0.0), ("З", 270.0, 0.0)]
            lon = np.array([c[1] for c in cardinals])
            lat = np.array([c[2] for c in cardinals])
        else:
            self._draw_curve(painter, s.horizon_ra, s.horizon_dec, QPen(QColor(90, 200, 120, 220), 2.0), r_max)
            lon = np.array([c[1] for c in s.cardinals])
            lat = np.array([c[2] for c in s.cardinals])
            cardinals = s.cardinals
        px, py, inside, *_ = self._project(lon, lat)
        font = QFont(painter.font())
        font.setPointSizeF(12.0)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(120, 230, 150))
        for i, c in enumerate(cardinals):
            if inside[i]:
                painter.drawText(QPointF(float(px[i]) - 6, float(py[i]) - 6), c[0])

    def _draw_bodies(self, painter: QPainter) -> None:
        s = self.snapshot
        font = QFont(painter.font())
        font.setPointSizeF(9.0)
        painter.setFont(font)
        lon = np.array([(b.az if self.mode == "horizontal" else b.ra) for b in s.bodies])
        lat = np.array([(b.alt if self.mode == "horizontal" else b.dec) for b in s.bodies])
        px, py, inside, *_ = self._project(lon, lat)
        for i, b in enumerate(s.bodies):
            if not inside[i]:
                continue
            if self.mode == "horizontal" and b.alt < -1.0 and not self.layers["below_horizon"]:
                continue
            x, y = float(px[i]), float(py[i])
            if b.kind == "sun":
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 220, 90, 70))
                painter.drawEllipse(QPointF(x, y), 15.0, 15.0)
                painter.setBrush(QColor(255, 225, 100))
                painter.drawEllipse(QPointF(x, y), 8.0, 8.0)
            elif b.kind == "moon":
                paint_moon(painter, x, y, 9.0, b.phase_angle or 0.0, mirrored=s.latitude < 0)
            else:
                radius = max(3.0, 5.5 - (b.mag or 0.0) * 0.6)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(PLANET_COLORS.get(b.key, "#ffffff")))
                painter.drawEllipse(QPointF(x, y), radius, radius)
            painter.setPen(QColor(255, 245, 200))
            painter.drawText(QPointF(x + 11, y - 7), b.name)
            self._hits.append((x, y, {"key": b.key, "type": b.kind, "name": b.name, "kind": {"sun": "Солнце", "moon": "Луна"}.get(
                b.kind, "Планета"), "mag": b.mag, "alt": b.alt, "az": b.az, "ra": b.ra, "dec": b.dec,
                "detail": b.detail}))
        if self.selected_key:
            for x, y, info in self._hits:
                if info["key"] == self.selected_key:
                    painter.setBrush(Qt.NoBrush)
                    painter.setPen(QPen(QColor(255, 80, 80), 1.8))
                    painter.drawEllipse(QPointF(x, y), 13.0, 13.0)

    # ---- мышь ---------------------------------------------------------------------------------
    def wheelEvent(self, event) -> None:  # noqa: N802
        self.zoom(0.85 if event.angleDelta().y() > 0 else 1.0 / 0.85)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._drag_from = event.position()
            self._drag_center = (self.lon0, self.lat0)
            self._moved = False

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_from is None or self.snapshot is None:
            return
        dx = event.position().x() - self._drag_from.x()
        dy = event.position().y() - self._drag_from.y()
        if abs(dx) + abs(dy) > 3:
            self._moved = True
        scale = self._geometry()[3]
        self.lon0, self.lat0 = skymap.stereo_unproject(-dx / scale, dy / scale, *self._drag_center)
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton:
            return
        was_click = self._drag_from is not None and not self._moved
        self._drag_from = None
        if was_click:
            self._pick(event.position())

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.zoom(0.6)

    def _pick(self, pos: QPointF) -> None:
        best, best_d = None, 14.0
        for x, y, info in self._hits:
            d = math.hypot(x - pos.x(), y - pos.y())
            if d < best_d:
                best, best_d = info, d
        self.selected_key = best["key"] if best else None
        self.update()
        if best:
            self.object_selected.emit(dict(best))


def describe_object(info: dict) -> str:
    """HTML-описание выбранного объекта для боковой панели."""
    mag = "—" if info.get("mag") is None else f"{info['mag']:+.1f}ᵐ"
    above = info["alt"] > 0
    rows = [("Тип", info["kind"]), ("Блеск", mag),
            ("Высота / азимут", f"{info['alt']:+.1f}° / {info['az']:.0f}° ({compass_point(info['az'])})"),
            ("Прямое восхождение (J2000)", format_hms(info["ra"] / 15.0)),
            ("Склонение (J2000)", format_dms(info["dec"])),
            ("Над горизонтом", "да" if above else "нет")]
    body = "".join(f"<tr><td>{a}</td><td><b>{b}</b></td></tr>" for a, b in rows)
    detail = f"<p>{info['detail']}</p>" if info.get("detail") else ""
    return f"<h3>{info['name']}</h3><table cellspacing='3'>{body}</table>{detail}"
