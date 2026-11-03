"""Виджет карты Земли (равнопромежуточная проекция): береговая линия, день/ночь, трассы спутников."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from astronomy import earthmap

COLORS = ["#ff5252", "#40c4ff", "#ffd740", "#69f0ae", "#e040fb", "#ff9100", "#b2ff59", "#18ffff"]


@dataclass
class SatDisplay:
    name: str
    color: str
    lat: float
    lon: float
    height_km: float
    past: tuple[np.ndarray, np.ndarray] = field(default_factory=lambda: (np.array([]), np.array([])))
    future: tuple[np.ndarray, np.ndarray] = field(default_factory=lambda: (np.array([]), np.array([])))


class EarthMapWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(480, 260)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.coast: list[np.ndarray] = []
        self.sats: list[SatDisplay] = []
        self.sun: tuple[float, float] | None = None
        self.observer: tuple[float, float, str] | None = None
        self.show_footprint = True
        self.show_night = True
        self.notice = ""

    # ---- данные -----------------------------------------------------------------------------
    def set_coast(self, lines: list[np.ndarray]) -> None:
        self.coast = lines
        self.update()

    def set_state(self, sats: list[SatDisplay], sun, observer) -> None:
        self.sats, self.sun, self.observer = sats, sun, observer
        self.update()

    # ---- проекция ---------------------------------------------------------------------------
    def _rect(self) -> QRectF:
        w, h = self.width() - 12.0, self.height() - 12.0
        if w / 2.0 <= h:
            return QRectF(6.0, 6.0 + (h - w / 2.0) / 2.0, w, w / 2.0)
        return QRectF(6.0 + (w - 2.0 * h) / 2.0, 6.0, 2.0 * h, h)

    def _xy(self, rect: QRectF, lon, lat):
        x = rect.left() + (np.asarray(lon, float) + 180.0) / 360.0 * rect.width()
        y = rect.top() + (90.0 - np.asarray(lat, float)) / 180.0 * rect.height()
        return x, y

    def _polyline(self, painter: QPainter, rect: QRectF, lons, lats) -> None:
        for seg_lon, seg_lat in earthmap.split_dateline(earthmap.normalize_lon(lons), lats):
            x, y = self._xy(rect, seg_lon, seg_lat)
            painter.drawPolyline(QPolygonF([QPointF(float(a), float(b)) for a, b in zip(x, y)]))

    # ---- рисование -----------------------------------------------------------------------------
    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(18, 18, 22))
        rect = self._rect()
        painter.fillRect(rect, QColor(28, 52, 84))
        painter.save()
        painter.setClipRect(rect)

        painter.setPen(QPen(QColor(255, 255, 255, 40), 1.0))
        for lon in range(-180, 181, 30):
            x, _ = self._xy(rect, lon, 0)
            painter.drawLine(QPointF(float(x), rect.top()), QPointF(float(x), rect.bottom()))
        for lat in range(-60, 91, 30):
            _, y = self._xy(rect, 0, lat)
            painter.drawLine(QPointF(rect.left(), float(y)), QPointF(rect.right(), float(y)))
        painter.setPen(QPen(QColor(255, 255, 255, 90), 1.0, Qt.DashLine))
        _, y0 = self._xy(rect, 0, 0)
        painter.drawLine(QPointF(rect.left(), float(y0)), QPointF(rect.right(), float(y0)))

        painter.setPen(QPen(QColor(170, 200, 150), 1.1))
        for line in self.coast:
            self._polyline(painter, rect, line[:, 0], line[:, 1])

        if self.show_night and self.sun is not None:
            lon, lat = earthmap.night_polygon(self.sun[0], self.sun[1])
            x, y = self._xy(rect, lon, lat)
            path = QPainterPath()
            path.addPolygon(QPolygonF([QPointF(float(a), float(b)) for a, b in zip(x, y)]))
            painter.fillPath(path, QColor(0, 0, 20, 120))
            sx, sy = self._xy(rect, self.sun[1], self.sun[0])
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 225, 100))
            painter.drawEllipse(QPointF(float(sx), float(sy)), 6.0, 6.0)

        for sat in self.sats:
            color = QColor(sat.color)
            if self.show_footprint:
                f_lon, f_lat = earthmap.footprint(sat.lat, sat.lon, sat.height_km)
                fill = QColor(color)
                fill.setAlpha(28)
                for seg_lon, seg_lat in earthmap.split_dateline(f_lon, f_lat):
                    x, y = self._xy(rect, seg_lon, seg_lat)
                    painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 110), 1.0))
                    painter.drawPolyline(QPolygonF([QPointF(float(a), float(b)) for a, b in zip(x, y)]))
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 130), 1.4, Qt.DashLine))
            self._polyline(painter, rect, *sat.past)
            painter.setPen(QPen(color, 1.8))
            self._polyline(painter, rect, *sat.future)

        if self.observer is not None:
            ox, oy = self._xy(rect, self.observer[1], self.observer[0])
            painter.setPen(QPen(QColor(255, 255, 255), 1.6))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(float(ox), float(oy)), 5.0, 5.0)
            painter.drawLine(QPointF(float(ox) - 8, float(oy)), QPointF(float(ox) + 8, float(oy)))
            painter.drawLine(QPointF(float(ox), float(oy) - 8), QPointF(float(ox), float(oy) + 8))

        font = QFont(painter.font())
        font.setPointSizeF(9.0)
        font.setBold(True)
        painter.setFont(font)
        for sat in self.sats:
            x, y = self._xy(rect, earthmap.normalize_lon(sat.lon), sat.lat)
            color = QColor(sat.color)
            painter.setPen(QPen(QColor(0, 0, 0), 2.0))
            painter.setBrush(color)
            painter.drawEllipse(QPointF(float(x), float(y)), 5.5, 5.5)
            painter.setPen(color.lighter(130))
            painter.drawText(QPointF(float(x) + 9, float(y) - 7), sat.name)
        painter.restore()

        painter.setPen(QPen(QColor(150, 155, 170), 1.2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)
        painter.setPen(QColor(210, 210, 220))
        if self.notice:
            painter.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, self.notice)
        if self.observer is not None:
            painter.drawText(QPointF(rect.left() + 6, rect.bottom() - 6), f"⊕ {self.observer[2]}")
